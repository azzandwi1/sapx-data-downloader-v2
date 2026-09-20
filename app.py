from __future__ import annotations

import os
import socket
import sys
import threading
import uuid
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file, session

from coresys import CoresysClient, CoresysError, normalize_awbs, normalize_awb_targets
from history_export import read_awb_targets_workbook
from jobs import JobManager
from tracking_focus_export import read_reference_targets_workbook


SOURCE_ROOT = Path(__file__).resolve().parent
BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", SOURCE_ROOT))
if getattr(sys, "frozen", False):
    default_data_root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SAPX Data Downloader"
else:
    default_data_root = SOURCE_ROOT
DATA_ROOT = Path(os.environ.get("SAP_DOWNLOADER_DATA", default_data_root)).resolve()

app = Flask(
    __name__,
    template_folder=str(BUNDLE_ROOT / "templates"),
    static_folder=str(BUNDLE_ROOT / "static"),
)
app.config.update(
    SECRET_KEY=os.environ.get("SAP_DOWNLOADER_SECRET", os.urandom(32)),
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

clients: dict[str, CoresysClient] = {}
clients_lock = threading.RLock()
jobs = JobManager(DATA_ROOT / "downloads")


def available_port(preferred: int, attempts: int = 20) -> int:
    for candidate in range(preferred, preferred + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(("127.0.0.1", candidate))
            except OSError:
                continue
            return candidate
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def current_client() -> CoresysClient:
    session_id = session.get("session_id")
    with clients_lock:
        client = clients.get(session_id or "")
    if not client:
        raise CoresysError("Sesi belum aktif. Silakan login.")
    return client


@app.errorhandler(CoresysError)
def handle_coresys_error(error: CoresysError):
    return jsonify({"ok": False, "error": str(error)}), 400


@app.errorhandler(ValueError)
def handle_value_error(error: ValueError):
    return jsonify({"ok": False, "error": str(error)}), 400


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/session")
def get_session():
    try:
        client = current_client()
    except CoresysError:
        return jsonify({"authenticated": False})
    return jsonify({"authenticated": True, "username": client.username})


@app.post("/api/login")
def login():
    payload = request.get_json(force=True)
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    pin = str(payload.get("pin", "")).strip()
    if not username or not password:
        raise ValueError("Username dan password wajib diisi.")

    client = CoresysClient()
    profile = client.login(username, password, pin)
    session_id = uuid.uuid4().hex
    old_session_id = session.get("session_id")
    with clients_lock:
        if old_session_id:
            clients.pop(old_session_id, None)
        clients[session_id] = client
    session["session_id"] = session_id
    return jsonify({"ok": True, "profile": profile})


@app.post("/api/logout")
def logout():
    session_id = session.pop("session_id", None)
    with clients_lock:
        if session_id:
            clients.pop(session_id, None)
    return jsonify({"ok": True})


@app.get("/api/options/<workflow>")
def options(workflow: str):
    return jsonify({"ok": True, "options": current_client().get_options(workflow)})


@app.post("/api/tracking-history/import")
def import_tracking_history_file():
    current_client()
    upload = request.files.get("file")
    if not upload or not upload.filename:
        raise ValueError("Pilih file Excel terlebih dahulu.")
    if Path(upload.filename).suffix.lower() not in {".xlsx", ".xlsm"}:
        raise ValueError("Format file harus .xlsx atau .xlsm.")
    tracking_mode = request.form.get("mode", "milestone")
    if tracking_mode not in {"milestone", "courier_pod", "pickup_attempt"}:
        raise ValueError("Jenis data trace & tracking tidak dikenal.")
    targets = read_awb_targets_workbook(upload.stream, require_tlc=tracking_mode == "milestone")
    return jsonify({"ok": True, "targets": targets, "count": len(targets), "filename": Path(upload.filename).name})


@app.post("/api/tracking-focus/import")
def import_tracking_focus_file():
    current_client()
    upload = request.files.get("file")
    if not upload or not upload.filename:
        raise ValueError("Pilih file Excel terlebih dahulu.")
    if Path(upload.filename).suffix.lower() not in {".xlsx", ".xlsm"}:
        raise ValueError("Format file harus .xlsx atau .xlsm.")
    targets = read_reference_targets_workbook(upload.stream)
    return jsonify({"ok": True, "targets": targets, "count": len(targets), "filename": Path(upload.filename).name})


@app.get("/api/jobs")
def list_jobs():
    current_client()
    return jsonify({"ok": True, "jobs": jobs.list()})


@app.post("/api/jobs")
def create_job():
    client = current_client()
    payload = request.get_json(force=True)
    if payload.get("workflow") == "tracking_focus":
        targets = payload.get("targets")
        if not targets and payload.get("text"):
            targets = normalize_awbs(str(payload.get("text", "")))
        if not isinstance(targets, list) or not targets:
            raise ValueError("Masukkan atau unggah minimal satu nomor referensi/AWB.")
        payload["targets"] = [str(t).strip() for t in targets if str(t).strip()]
        payload["search_by"] = str(payload.get("search_by") or "a.reference_no")
    elif payload.get("workflow") == "tracking_history":
        raw_text = str(payload.get("awb_text", "")).strip()
        items = payload.get("awb_targets")
        if not items and raw_text:
            items = normalize_awb_targets(raw_text)
        elif not isinstance(items, list):
            raise ValueError("Tempel nomor AWB terlebih dahulu.")
        tracking_mode = payload.get("tracking_mode", "milestone")
        if tracking_mode not in {"milestone", "courier_pod", "pickup_attempt"}:
            raise ValueError("Jenis data trace & tracking tidak dikenal.")
        targets = [
            {"awb": str(item.get("awb", "")).strip().upper(), "tlc": str(item.get("tlc", "")).strip().upper()}
            if isinstance(item, dict) else {"awb": str(item).strip().upper(), "tlc": ""}
            for item in items if str(item.get("awb", "") if isinstance(item, dict) else item).strip()
        ]
        if not targets:
            raise ValueError("Tidak ada nomor AWB yang dapat diproses.")
        payload["awb_targets"] = targets
    elif payload.get("workflow") == "pod_awb":
        payload["awbs"] = normalize_awbs(str(payload.get("awb_text", "")))
    job = jobs.create(client, payload)
    return jsonify({"ok": True, "job": job}), 201


@app.get("/api/jobs/<job_id>")
def get_job(job_id: str):
    current_client()
    try:
        return jsonify({"ok": True, "job": jobs.public(job_id)})
    except KeyError:
        return jsonify({"ok": False, "error": "Pekerjaan tidak ditemukan."}), 404


@app.post("/api/jobs/<job_id>/cancel")
def cancel_job(job_id: str):
    current_client()
    try:
        return jsonify({"ok": True, "job": jobs.cancel(job_id)})
    except KeyError:
        return jsonify({"ok": False, "error": "Pekerjaan tidak ditemukan."}), 404


@app.get("/api/jobs/<job_id>/batches/<int:batch_index>/download")
def download(job_id: str, batch_index: int):
    current_client()
    try:
        path = jobs.file_for(job_id, batch_index)
    except (KeyError, IndexError, FileNotFoundError):
        return jsonify({"ok": False, "error": "File belum tersedia."}), 404
    return send_file(path, as_attachment=True, download_name=path.name)


@app.post("/api/jobs/<job_id>/batches/<int:batch_index>/retry")
def retry_batch(job_id: str, batch_index: int):
    client = current_client()
    try:
        job = jobs.retry_batch(job_id, batch_index, client)
        return jsonify({"ok": True, "job": job})
    except KeyError:
        return jsonify({"ok": False, "error": "Pekerjaan tidak ditemukan."}), 404
    except (IndexError, ValueError) as err:
        return jsonify({"ok": False, "error": str(err)}), 400


if __name__ == "__main__":
    configured_port = os.environ.get("PORT")
    port = int(configured_port) if configured_port else available_port(5177)
    if getattr(sys, "frozen", False):
        threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
