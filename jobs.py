from __future__ import annotations

import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

from coresys import CoresysClient, CoresysError, split_awbs, split_date_range


class JobManager:
    def __init__(self, download_root: Path) -> None:
        self.download_root = download_root
        self.jobs: dict[str, dict[str, Any]] = {}
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="coresys-download")

    def create(self, client: CoresysClient, payload: dict[str, Any]) -> dict[str, Any]:
        workflow = payload.get("workflow")
        if workflow not in {"pickup", "pickup_manual", "pod_v2", "pod_awb"}:
            raise ValueError("Workflow tidak dikenal.")

        if workflow == "pod_awb":
            awbs = payload.get("awbs") or []
            batches_data = split_awbs(awbs, int(payload.get("batch_size", 10_000)))
            batches = []
            offset = 0
            for i, batch in enumerate(batches_data):
                batches.append({
                    "index": i + 1,
                    "label": f"AWB {offset + 1:,} - {offset + len(batch):,}",
                    "awbs": batch,
                })
                offset += len(batch)
        else:
            batch_days = int(payload.get("batch_days", 7))
            if workflow == "pod_v2" and batch_days > 31:
                raise ValueError("Batch Laporan POD V2 maksimal 31 hari sesuai batas server portal.")
            date_batches = split_date_range(
                str(payload.get("date_from", "")),
                str(payload.get("date_to", "")),
                batch_days,
            )
            batches = [
                {"index": i + 1, "label": f"{item.start.isoformat()} - {item.end.isoformat()}", **item.as_dict()}
                for i, item in enumerate(date_batches)
            ]

        job_id = uuid.uuid4().hex[:12]
        job = {
            "id": job_id,
            "workflow": workflow,
            "status": "queued",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "filters": payload.get("filters") or {},
            "export": payload.get("export", ""),
            "delay_seconds": max(0, min(int(payload.get("delay_seconds", 3)), 300)),
            "poll_seconds": max(5, min(int(payload.get("poll_seconds", 10)), 120)),
            "completed": 0,
            "failed": 0,
            "cancel_requested": False,
            "batches": [
                {**batch, "status": "queued", "downloaded": 0, "total": None, "file": None, "error": None}
                for batch in batches
            ],
        }
        with self.lock:
            self.jobs[job_id] = job
        self.executor.submit(self._run, client, job_id)
        return self.public(job_id)

    def list(self) -> list[dict[str, Any]]:
        with self.lock:
            ids = sorted(self.jobs, key=lambda value: self.jobs[value]["created_at"], reverse=True)
        return [self.public(job_id) for job_id in ids]

    def public(self, job_id: str) -> dict[str, Any]:
        with self.lock:
            if job_id not in self.jobs:
                raise KeyError(job_id)
            job = self.jobs[job_id]
            public_batches = [
                {key: value for key, value in batch.items() if key != "awbs"}
                for batch in job["batches"]
            ]
            return {
                key: value
                for key, value in job.items()
                if key not in {"filters", "batches"}
            } | {"batches": public_batches, "batch_count": len(job["batches"])}

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self.lock:
            job = self.jobs[job_id]
            if job["status"] in {"queued", "running"}:
                job["cancel_requested"] = True
                self._touch(job)
        return self.public(job_id)

    def file_for(self, job_id: str, batch_index: int) -> Path:
        with self.lock:
            job = self.jobs[job_id]
            batch = job["batches"][batch_index - 1]
            if not batch.get("file"):
                raise FileNotFoundError
            path = Path(batch["file"]).resolve()
        root = self.download_root.resolve()
        if root not in path.parents or not path.is_file():
            raise FileNotFoundError
        return path

    def _touch(self, job: dict[str, Any]) -> None:
        job["updated_at"] = datetime.now().isoformat(timespec="seconds")

    def _progress(self, job_id: str, batch_index: int, downloaded: int, total: int | None) -> None:
        with self.lock:
            job = self.jobs[job_id]
            batch = job["batches"][batch_index - 1]
            batch["downloaded"] = downloaded
            batch["total"] = total
            self._touch(job)

    def _run(self, client: CoresysClient, job_id: str) -> None:
        with self.lock:
            job = self.jobs[job_id]
            job["status"] = "running"
            self._touch(job)

        for batch in job["batches"]:
            with self.lock:
                if job["cancel_requested"]:
                    job["status"] = "cancelled"
                    self._touch(job)
                    return
                batch["status"] = "running"
                self._touch(job)

            try:
                path = self._run_batch(client, job, batch)
                with self.lock:
                    batch["status"] = "complete"
                    batch["file"] = str(path)
                    job["completed"] += 1
                    self._touch(job)
            except Exception as exc:
                with self.lock:
                    batch["status"] = "failed"
                    batch["error"] = str(exc)
                    job["failed"] += 1
                    self._touch(job)

            if batch["index"] < len(job["batches"]) and job["delay_seconds"]:
                time.sleep(job["delay_seconds"])

        with self.lock:
            job["status"] = "complete" if job["failed"] == 0 else "complete_with_errors"
            self._touch(job)

    def _run_batch(self, client: CoresysClient, job: dict[str, Any], batch: dict[str, Any]) -> Path:
        job_dir = self.download_root / job["id"]
        job_dir.mkdir(parents=True, exist_ok=True)
        callback = lambda downloaded, total: self._progress(job["id"], batch["index"], downloaded, total)
        prefix = f"{batch['index']:03d}"

        if job["workflow"] == "pickup":
            url = client.pickup_url(batch["from"], batch["to"], job["filters"], job["export"])
            return client.download_direct(url, job_dir / f"{prefix}_pickup.xlsx", callback)

        if job["workflow"] == "pickup_manual":
            url = client.pickup_manual_url(batch["from"], batch["to"], job["filters"], job["export"])
            return client.download_direct(url, job_dir / f"{prefix}_pickup_manual.xlsx", callback)

        if job["workflow"] == "pod_awb":
            path = client.download_awb_batch(batch["awbs"], job_dir / f"{prefix}_pod_by_awb.xlsx", callback)
            records = self._xlsx_data_rows(path, header_rows=3)
            if records is not None:
                with self.lock:
                    batch["records"] = records
                    if records == 0:
                        batch["warning"] = "Portal mengembalikan file valid, tetapi tidak ada baris data untuk AWB pada batch ini."
                    self._touch(job)
            return path

        submitted = client.submit_pod_v2(batch["from"], batch["to"], job["filters"])
        process_id = submitted["process_id"]
        with self.lock:
            batch["process_id"] = process_id
            batch["status"] = "waiting_server"
            self._touch(job)

        deadline = time.monotonic() + 4 * 60 * 60
        while time.monotonic() < deadline:
            if job["cancel_requested"]:
                raise CoresysError("Pekerjaan dibatalkan.")
            status = client.poll_pod_v2(process_id)
            if status["state"] == "complete":
                with self.lock:
                    batch["status"] = "downloading"
                    self._touch(job)
                return client.download_direct(status["url"], job_dir / f"{prefix}_pod_v2.xlsx", callback)
            if status["state"] == "failed":
                raise CoresysError(status.get("message", "Proses POD gagal."))
            time.sleep(job["poll_seconds"])
        raise CoresysError("Waktu tunggu POD V2 melewati 4 jam.")

    @staticmethod
    def _xlsx_data_rows(path: Path, header_rows: int) -> int | None:
        try:
            with zipfile.ZipFile(path) as archive:
                sheet = archive.read("xl/worksheets/sheet1.xml")
            return max(sheet.count(b"<row") - header_rows, 0)
        except (OSError, KeyError, zipfile.BadZipFile):
            return None
