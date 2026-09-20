from __future__ import annotations

import threading
import time
import uuid
import zipfile
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import datetime
from pathlib import Path
from typing import Any

from coresys import CoresysClient, CoresysError, split_awbs, split_date_range
from history_export import export_tracking_history
from tracking_focus_export import export_tracking_focus


class JobManager:
    def __init__(
        self,
        download_root: Path,
        max_concurrent_batches: int = 3,
        max_concurrent_jobs: int = 4,
    ) -> None:
        self.download_root = download_root
        self.download_root.mkdir(parents=True, exist_ok=True)
        self.jobs: dict[str, dict[str, Any]] = {}
        self.lock = threading.RLock()
        self.job_executor = ThreadPoolExecutor(max_workers=max_concurrent_jobs, thread_name_prefix="coresys-job")
        self.batch_executor = ThreadPoolExecutor(
            max_workers=max_concurrent_batches,
            thread_name_prefix="coresys-batch",
        )

    def create(self, client: CoresysClient, payload: dict[str, Any]) -> dict[str, Any]:
        workflow = payload.get("workflow")
        if workflow not in {"pickup", "pickup_manual", "pod_v2", "pod_awb", "tracking_history", "tracking_focus"}:
            raise ValueError("Workflow tidak dikenal.")

        if workflow == "tracking_focus":
            targets = payload.get("targets") or []
            if not targets:
                raise ValueError("Masukkan minimal satu nomor untuk dilacak.")
            search_by = payload.get("search_by") or "a.reference_no"
            batches = [{
                "index": 1,
                "label": f"{len(targets):,} nomor ke satu file Excel",
                "targets": targets,
                "search_by": search_by,
                "progress_unit": "nomor",
                "processed": 0,
                "item_total": len(targets),
            }]
        elif workflow == "tracking_history":
            awb_targets = payload.get("awb_targets") or []
            if not awb_targets:
                raise ValueError("Masukkan minimal satu nomor AWB.")
            tracking_mode = payload.get("tracking_mode", "milestone")
            if tracking_mode not in {"milestone", "courier_pod", "pickup_attempt"}:
                raise ValueError("Jenis data trace & tracking tidak dikenal.")
            batches = [{
                "index": 1,
                "label": f"{len(awb_targets):,} AWB ke satu file Excel",
                "awb_targets": awb_targets,
                "progress_unit": "awb",
                "processed": 0,
                "item_total": len(awb_targets),
            }]
        elif workflow == "pod_awb":
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
        max_parallelism = 12 if workflow in {"tracking_history", "tracking_focus"} else 3
        job = {
            "id": job_id,
            "workflow": workflow,
            "status": "queued",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "filters": payload.get("filters") or {},
            "export": payload.get("export", ""),
            "delay_seconds": max(0, min(int(payload.get("delay_seconds", 30)), 300)),
            "poll_seconds": max(5, min(int(payload.get("poll_seconds", 5)), 120)),
            "parallelism": max(1, min(int(payload.get("parallelism", 1)), max_parallelism)),
            "include_summary": bool(payload.get("include_summary", True)),
            "include_history": bool(payload.get("include_history", True)),
            "tracking_mode": payload.get("tracking_mode", "milestone"),
            "search_by": payload.get("search_by", "a.reference_no"),
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
        self.job_executor.submit(self._run, client, job_id)
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
                {key: value for key, value in batch.items() if key not in {"awbs", "awb_targets"}}
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

    def retry_batch(self, job_id: str, batch_index: int, client: CoresysClient) -> dict[str, Any]:
        with self.lock:
            job = self.jobs[job_id]
            if not 1 <= batch_index <= len(job["batches"]):
                raise IndexError("Batch tidak ditemukan.")
            batch = job["batches"][batch_index - 1]
            if batch["status"] != "failed":
                raise ValueError("Hanya batch yang berstatus gagal yang dapat dicoba ulang.")

            batch["status"] = "queued"
            batch["error"] = None
            batch["warning"] = None
            batch["downloaded"] = 0
            batch["total"] = None
            batch["file"] = None
            if "processed" in batch:
                batch["processed"] = 0
            batch.pop("records", None)
            batch.pop("missing", None)
            batch.pop("request_failed", None)
            batch.pop("process_id", None)

            job["failed"] = max(0, job["failed"] - 1)
            job["cancel_requested"] = False
            job["status"] = "running"
            self._touch(job)

        self.batch_executor.submit(self._execute_retried_batch, client.fork(), job, batch)
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

    def _item_progress(self, job_id: str, batch_index: int, processed: int, total: int) -> None:
        with self.lock:
            job = self.jobs[job_id]
            batch = job["batches"][batch_index - 1]
            batch["processed"] = processed
            batch["item_total"] = total
            self._touch(job)

    def _run(self, client: CoresysClient, job_id: str) -> None:
        with self.lock:
            job = self.jobs[job_id]
            job["status"] = "running"
            self._touch(job)

        next_batch = 0
        running: dict[Future[None], dict[str, Any]] = {}

        while next_batch < len(job["batches"]) or running:
            with self.lock:
                cancelled = job["cancel_requested"]

            while not cancelled and next_batch < len(job["batches"]) and len(running) < job["parallelism"]:
                batch = job["batches"][next_batch]
                future = self.batch_executor.submit(self._execute_batch, client.fork(), job, batch)
                running[future] = batch
                next_batch += 1
                with self.lock:
                    cancelled = job["cancel_requested"]

            if running:
                done, _ = wait(running, timeout=0.5, return_when=FIRST_COMPLETED)
                for future in done:
                    running.pop(future)
                    future.result()

                with self.lock:
                    cancelled = job["cancel_requested"]
                if not cancelled and next_batch < len(job["batches"]) and job["delay_seconds"]:
                    sleep_until = time.monotonic() + job["delay_seconds"]
                    while time.monotonic() < sleep_until:
                        with self.lock:
                            if job["cancel_requested"]:
                                cancelled = True
                                break
                        time.sleep(min(0.5, max(0.0, sleep_until - time.monotonic())))
            elif cancelled:
                break

        with self.lock:
            if job["cancel_requested"]:
                for batch in job["batches"]:
                    if batch["status"] == "queued":
                        batch["status"] = "cancelled"
                job["status"] = "cancelled"
            else:
                any_active = any(
                    b["status"] in {"queued", "running", "waiting_server", "downloading"}
                    for b in job["batches"]
                )
                if not any_active:
                    job["status"] = "complete" if job["failed"] == 0 else "complete_with_errors"
            self._touch(job)

    def _execute_batch(
        self,
        client: CoresysClient,
        job: dict[str, Any],
        batch: dict[str, Any],
    ) -> None:
        with self.lock:
            if job["cancel_requested"]:
                batch["status"] = "cancelled"
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

    def _execute_retried_batch(
        self,
        client: CoresysClient,
        job: dict[str, Any],
        batch: dict[str, Any],
    ) -> None:
        self._execute_batch(client, job, batch)
        with self.lock:
            any_active = any(
                b["status"] in {"queued", "running", "waiting_server", "downloading"}
                for b in job["batches"]
            )
            if not any_active:
                job["status"] = "complete" if job["failed"] == 0 else "complete_with_errors"
            self._touch(job)

    def shutdown(self) -> None:
        self.job_executor.shutdown(wait=True, cancel_futures=True)
        self.batch_executor.shutdown(wait=True, cancel_futures=True)

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

        if job["workflow"] == "tracking_history":
            path, found, missing, request_failed = export_tracking_history(
                client,
                batch["awb_targets"],
                job_dir / f"{prefix}_tracking_history.xlsx",
                parallelism=job["parallelism"],
                delay_seconds=job["delay_seconds"],
                include_summary=job["include_summary"],
                include_history=job["include_history"],
                tracking_mode=job["tracking_mode"],
                progress=lambda processed, total: self._item_progress(
                    job["id"], batch["index"], processed, total
                ),
                cancelled=lambda: bool(job["cancel_requested"]),
            )
            with self.lock:
                batch["records"] = found
                batch["missing"] = missing
                batch["request_failed"] = request_failed
                if missing or request_failed:
                    batch["warning"] = (
                        f"{found:,} AWB ditemukan, {missing:,} tidak ditemukan, "
                        f"dan {request_failed:,} gagal diambil. Detail tersedia di sheet Ringkasan."
                    )
                self._touch(job)
            return path

        if job["workflow"] == "tracking_focus":
            targets = batch["targets"]
            search_by = batch.get("search_by") or job.get("search_by") or "a.reference_no"
            chunk_size = 200
            all_records = []
            processed_count = 0
            self._item_progress(job["id"], batch["index"], 0, len(targets))

            for i in range(0, len(targets), chunk_size):
                if job["cancel_requested"]:
                    raise CoresysError("Pekerjaan dibatalkan.")
                chunk = targets[i : i + chunk_size]
                records = client.fetch_tracking_focus_batch(chunk, search_by=search_by)
                all_records.extend(records)
                processed_count += len(chunk)
                self._item_progress(job["id"], batch["index"], processed_count, len(targets))
                if i + chunk_size < len(targets) and job.get("delay_seconds"):
                    time.sleep(job["delay_seconds"])

            out_file = job_dir / f"{prefix}_tracking_focus.xlsx"
            export_tracking_focus(all_records, targets, out_file, search_by=search_by)
            with self.lock:
                batch["records"] = len(all_records)
                self._touch(job)
            return out_file

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
