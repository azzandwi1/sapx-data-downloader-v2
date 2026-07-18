from __future__ import annotations

import os
import threading
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file, session

from coresys import CoresysClient, CoresysError, normalize_awbs
from jobs import JobManager


ROOT = Path(__file__).resolve().parent
app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SAP_DOWNLOADER_SECRET", os.urandom(32)),
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

clients: dict[str, CoresysClient] = {}
clients_lock = threading.RLock()
jobs = JobManager(ROOT / "downloads")


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


@app.get("/api/jobs")
def list_jobs():
    current_client()
    return jsonify({"ok": True, "jobs": jobs.list()})


@app.post("/api/jobs")
def create_job():
    client = current_client()
    payload = request.get_json(force=True)
    if payload.get("workflow") == "pod_awb":
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


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5177")), debug=False, threaded=True)
