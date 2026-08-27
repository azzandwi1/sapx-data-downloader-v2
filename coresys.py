from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

import requests


BASE_URL = "https://online.coresyssap.com"
REPORT_URL = "https://report-js-aws-jkt.coresyssap.com"
AWB_REPORT_URL = "https://report02-aws-jkt.coresyssap.com/report_pod/export_report_pod_by_awb/"

WORKFLOW_PAGES = {
    "pickup": f"{BASE_URL}/pickup/monitoring_list",
    "pickup_manual": f"{BASE_URL}/pickup_manual/monitoring_list",
    "pod_v2": f"{BASE_URL}/pod_report_v2/",
    "pod_awb": f"{BASE_URL}/report/pod_by_awb",
    "tracking_history": f"{BASE_URL}/tracking/focus",
}


class CoresysError(RuntimeError):
    pass


class SelectParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.selects: dict[str, list[dict[str, str]]] = {}
        self._select_id: str | None = None
        self._option: dict[str, str] | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_map = dict(attrs)
        if tag == "select":
            self._select_id = attrs_map.get("id") or attrs_map.get("name")
            if self._select_id:
                self.selects.setdefault(self._select_id, [])
        elif tag == "option" and self._select_id:
            self._option = {"value": attrs_map.get("value") or ""}
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._option is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "option" and self._select_id and self._option is not None:
            self._option["label"] = " ".join("".join(self._text).split())
            self.selects[self._select_id].append(self._option)
            self._option = None
            self._text = []
        elif tag == "select":
            self._select_id = None


class HistoryTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append("\n")

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(self._row):
                self.rows.append(self._row)
            self._row = None


def parse_tracking_history(html: str) -> list[dict[str, Any]]:
    marker = html.find(">Riwayat</h4>")
    if marker < 0:
        marker = html.find("Riwayat")
    if marker < 0:
        return []
    table = re.search(r"<table\b.*?</table>", html[marker:], re.I | re.S)
    if not table:
        return []

    parser = HistoryTableParser()
    parser.feed(table.group(0))
    records: list[dict[str, Any]] = []
    for cells in parser.rows:
        if len(cells) < 7 or cells[0] == "#":
            continue
        try:
            number = int(cells[0])
        except ValueError:
            continue
        records.append({
            "no": number,
            "process": cells[1],
            "document": cells[2],
            "reference": cells[3],
            "datetime": cells[4],
            "location": cells[5],
            "note": cells[6],
        })
    return records


@dataclass(frozen=True)
class DateBatch:
    start: date
    end: date

    def as_dict(self) -> dict[str, str]:
        return {"from": self.start.isoformat(), "to": self.end.isoformat()}


def split_date_range(start: str, end: str, batch_days: int) -> list[DateBatch]:
    start_date = datetime.strptime(start, "%Y-%m-%d").date()
    end_date = datetime.strptime(end, "%Y-%m-%d").date()
    if start_date > end_date:
        raise ValueError("Tanggal awal tidak boleh setelah tanggal akhir.")
    if not 1 <= batch_days <= 366:
        raise ValueError("Batch hari harus antara 1 dan 366.")

    result: list[DateBatch] = []
    cursor = start_date
    while cursor <= end_date:
        batch_end = min(cursor + timedelta(days=batch_days - 1), end_date)
        result.append(DateBatch(cursor, batch_end))
        cursor = batch_end + timedelta(days=1)
    return result


def normalize_awbs(raw: str) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in re.split(r"[\s,;]+", raw.upper()):
        awb = value.strip()
        if awb and awb not in seen:
            seen.add(awb)
            result.append(awb)
    return result


def normalize_awb_targets(raw: str) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, str]] = []
    for raw_line in raw.upper().splitlines():
        line = raw_line.replace("**", "").strip().strip("|").strip()
        if not line or re.fullmatch(r"[-|:\s]+", line):
            continue
        if "AWB" in line and "TLC" in line:
            continue

        columns = [value.strip() for value in re.split(r"\t+|\s{2,}|\s+\|\s+", line) if value.strip()]
        if len(columns) == 1:
            whitespace = columns[0].split()
            if len(whitespace) == 2 and re.fullmatch(r"[A-Z0-9]{2,10}", whitespace[1]):
                columns = whitespace

        if len(columns) >= 2 and re.fullmatch(r"[A-Z0-9]{2,10}", columns[1]):
            pairs = [(columns[0], columns[1])]
        else:
            pairs = [(awb, "") for awb in normalize_awbs(line)]

        for awb, tlc in pairs:
            key = (awb, tlc)
            if awb and key not in seen:
                seen.add(key)
                result.append({"awb": awb, "tlc": tlc})
    if not result:
        raise ValueError("Masukkan minimal satu nomor AWB.")
    return result


def split_awbs(awbs: list[str], size: int = 10_000) -> list[list[str]]:
    if not awbs:
        raise ValueError("Masukkan minimal satu nomor AWB.")
    if size < 1 or size > 10_000:
        raise ValueError("Ukuran batch AWB harus antara 1 dan 10.000.")
    return [awbs[i : i + size] for i in range(0, len(awbs), size)]


def format_awb_text(awbs: list[str]) -> str:
    # Browser form submission normalizes textarea line breaks to CRLF. The report
    # server relies on that exact delimiter when splitting AWB values.
    return "\r\n".join(awbs)


def safe_filename(value: str, fallback: str) -> str:
    value = value.replace("_X_", " ")
    value = re.sub(r"[^A-Za-z0-9._ -]+", "_", value).strip(" .")
    return value or fallback


class CoresysClient:
    def __init__(self, shared_context: dict[str, Any] | None = None) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 Coresys Batch Downloader/1.0",
            "Accept-Language": "id-ID,id;q=0.9,en;q=0.7",
        })
        self.username: str | None = None
        self._page_cache: dict[str, str] = {}
        self._shared_context = shared_context or {
            "lock": threading.RLock(),
            "pod_context": None,
            "history_cache": {},
        }

    def fork(self) -> "CoresysClient":
        """Create an independent HTTP pool with the same authenticated cookies."""
        self.require_login()
        client = CoresysClient(shared_context=self._shared_context)
        client.session.headers.update(self.session.headers)
        client.session.cookies.update(self.session.cookies)
        client.username = self.username
        client._page_cache = self._page_cache.copy()
        return client

    def login(self, username: str, password: str, pin: str) -> dict[str, str]:
        if not re.fullmatch(r"\d{6}", pin):
            raise CoresysError("PIN harus terdiri dari 6 angka.")

        role_response = self.session.post(
            f"{BASE_URL}/user/check_roles/",
            data={"username": username, "password": password},
            timeout=30,
        )
        role_response.raise_for_status()
        try:
            role_data = role_response.json()
        except requests.JSONDecodeError as exc:
            raise CoresysError("Portal tidak mengembalikan respons login yang valid.") from exc

        if role_data.get("status") != "yes":
            raise CoresysError("Username atau password ditolak oleh portal.")

        pin_fields = {f"pin{i + 1}": digit for i, digit in enumerate(pin)}
        verify_response = self.session.post(
            f"{BASE_URL}/user/check_auth_code/",
            data={"username": role_data.get("username", username), "secrets": "", **pin_fields},
            timeout=30,
        )
        verify_response.raise_for_status()
        try:
            verify_data = verify_response.json()
        except requests.JSONDecodeError as exc:
            raise CoresysError("Portal tidak mengembalikan respons PIN yang valid.") from exc
        if verify_data.get("status") != "yes":
            raise CoresysError("PIN ditolak oleh portal.")

        login_response = self.session.post(
            f"{BASE_URL}/user/do_login",
            data={
                "username_auth": role_data.get("username", username),
                "password_auth": role_data.get("data", ""),
                **pin_fields,
            },
            timeout=45,
        )
        login_response.raise_for_status()
        if "/home" not in login_response.url:
            raise CoresysError("Login belum menghasilkan sesi portal yang aktif.")

        self.username = username
        self._page_cache.clear()
        with self._shared_context["lock"]:
            self._shared_context["pod_context"] = None
            self._shared_context["history_cache"] = {}
        return {"username": username, "branch": self._extract_branch(login_response.text)}

    def _extract_branch(self, html: str) -> str:
        match = re.search(r'"branch_name"\s*:\s*"([^"]+)"', html)
        return match.group(1) if match else ""

    def require_login(self) -> None:
        if not self.username:
            raise CoresysError("Sesi portal belum aktif.")

    def get_page(self, workflow: str, refresh: bool = False) -> str:
        self.require_login()
        if workflow not in WORKFLOW_PAGES:
            raise CoresysError("Workflow tidak dikenal.")
        if workflow not in self._page_cache or refresh:
            response = self.session.get(WORKFLOW_PAGES[workflow], timeout=60)
            response.raise_for_status()
            if "/user/login" in response.url:
                raise CoresysError("Sesi portal berakhir. Silakan login ulang.")
            self._page_cache[workflow] = response.text
        return self._page_cache[workflow]

    def get_options(self, workflow: str) -> dict[str, list[dict[str, str]]]:
        parser = SelectParser()
        parser.feed(self.get_page(workflow))
        return parser.selects

    @staticmethod
    def _value(filters: dict[str, Any], key: str, default: str = "-") -> str:
        value = str(filters.get(key, "")).strip()
        return value if value else default

    @staticmethod
    def _path(parts: list[str]) -> str:
        return "/".join(quote(str(part), safe="-") for part in parts)

    @staticmethod
    def _pickup_date(value: str) -> str:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d-%m-%Y")

    def pickup_url(self, start: str, end: str, filters: dict[str, Any], export: str) -> str:
        allowed = {"report_monitoring", "report_monitoring_xlsx", "report", "report_monitoring_zilingo_xlsx"}
        if export not in allowed:
            raise CoresysError("Jenis export Pickup tidak didukung.")
        parts = [
            self._value(filters, "customers"), self._pickup_date(start), self._pickup_date(end),
            self._value(filters, "pilih_status", "0"), self._value(filters, "koli"),
            self._value(filters, "kilo"), self._value(filters, "is_cod"),
            self._value(filters, "branch_ori"), self._value(filters, "branch_dest"),
            self._value(filters, "pilih_pickup_place"), self._value(filters, "pilih_rowstate", "0"),
            self._value(filters, "date_pickup", "1"), self._value(filters, "branch_area_asal"),
            self._value(filters, "branch_area_tujuan"),
        ]
        return f"{BASE_URL}/pickup/{export}/{self._path(parts)}?token=token_02"

    def pickup_manual_url(self, start: str, end: str, filters: dict[str, Any], export: str) -> str:
        allowed = {"report_monitoring", "report_monitoring_v2"}
        if export not in allowed:
            raise CoresysError("Jenis export Pickup Manual tidak didukung.")
        date_pickup = self._value(filters, "date_pickup", "1")
        destination_area = self._value(filters, "destination_area_branch_code")
        if date_pickup == "0":
            date_pickup = "-"
        if destination_area == "0":
            destination_area = "-"
        parts = [
            self._value(filters, "customers"), self._pickup_date(start), self._pickup_date(end),
            self._value(filters, "pilih_status", "0"), self._value(filters, "koli"),
            self._value(filters, "kilo"), self._value(filters, "counter_type"),
            self._value(filters, "branch_ori"), self._value(filters, "branch_dest"),
            date_pickup,
            self._value(filters, "origin_area_branch_code"),
            destination_area,
        ]
        return f"{BASE_URL}/pickup_manual/{export}/{self._path(parts)}"

    def download_direct(
        self,
        url: str,
        destination: Path,
        progress: Callable[[int, int | None], None] | None = None,
        method: str = "GET",
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Path:
        self.require_login()
        with self.session.request(
            method, url, data=data, files=files, headers=headers, stream=True, timeout=(30, 3600)
        ) as response:
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").lower()
            if "text/html" in content_type and "attachment" not in response.headers.get("Content-Disposition", "").lower():
                preview = response.content[:1000].decode("utf-8", errors="ignore")
                raise CoresysError(f"Portal tidak mengirim file. Respons: {re.sub('<[^>]+>', ' ', preview).strip()[:220]}")

            disposition = response.headers.get("Content-Disposition", "")
            filename_match = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", disposition, re.I)
            remote_name = filename_match.group(1).strip() if filename_match else destination.name
            clean_name = safe_filename(remote_name, destination.name)
            batch_prefix = destination.stem.split("_", 1)[0]
            final_path = destination.with_name(f"{batch_prefix}_{clean_name}")
            total = int(response.headers.get("Content-Length", "0")) or None
            downloaded = 0
            final_path.parent.mkdir(parents=True, exist_ok=True)
            with final_path.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)
                        downloaded += len(chunk)
                        if progress:
                            progress(downloaded, total)
            return final_path

    def download_awb_batch(
        self,
        awbs: list[str],
        destination: Path,
        progress: Callable[[int, int | None], None] | None = None,
    ) -> Path:
        return self.download_direct(
            AWB_REPORT_URL,
            destination,
            progress=progress,
            method="POST",
            files={
                "key": (None, "a.awb_no"),
                "val": (None, format_awb_text(awbs)),
            },
            headers={
                "Origin": BASE_URL,
                "Referer": f"{BASE_URL}/report/pod_by_awb",
            },
        )

    def fetch_tracking_history(self, awb: str) -> list[dict[str, Any]]:
        self.require_login()
        with self._shared_context["lock"]:
            cache = self._shared_context.setdefault("history_cache", {})
            cached = cache.get(awb)
            if cached and time.monotonic() - cached[0] < 300:
                return [record.copy() for record in cached[1]]

        last_error: requests.RequestException | None = None
        for attempt in range(3):
            try:
                response = self.session.post(
                    f"{BASE_URL}/tracking/getriwayat",
                    data={"id": awb},
                    headers={
                        "X-Requested-With": "XMLHttpRequest",
                        "Origin": BASE_URL,
                        "Referer": f"{BASE_URL}/tracking/focus",
                    },
                    timeout=90,
                )
                response.raise_for_status()
                if "/user/login" in response.url:
                    raise CoresysError("Sesi portal berakhir. Silakan login ulang.")
                records = parse_tracking_history(response.text)
                with self._shared_context["lock"]:
                    cache = self._shared_context.setdefault("history_cache", {})
                    cache[awb] = (time.monotonic(), records)
                    while len(cache) > 2_000:
                        cache.pop(next(iter(cache)))
                return [record.copy() for record in records]
            except requests.RequestException as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(attempt + 1)
        raise CoresysError(f"Gagal mengambil history {awb} setelah 3 percobaan: {last_error}") from last_error

    def _pod_context(self) -> tuple[str, str]:
        with self._shared_context["lock"]:
            cached = self._shared_context["pod_context"]
            if cached:
                return cached
            html = self.get_page("pod_v2", refresh=True)
            token_match = re.search(r"let auth_token\s*=\s*'([^']+)'", html)
            userdata_match = re.search(r"userdata:\s*'((?:\\.|[^'])*)'", html)
            if not token_match or not userdata_match:
                raise CoresysError("Token Laporan POD V2 tidak ditemukan pada halaman portal.")
            userdata = userdata_match.group(1).replace("\\'", "'")
            context = (token_match.group(1), userdata)
            self._shared_context["pod_context"] = context
            return context

    @staticmethod
    def pod_payload(start: str, end: str, filters: dict[str, Any]) -> dict[str, str]:
        defaults = {
            "tgl_terima": "1", "origin_branch_code": "1", "destination_branch_code": "1",
            "customer_code": "1", "pod_status_code": "1", "report_type_code": "1",
            "transaction_type_code": "1", "transportation_code": "1", "opt_insurance": "1",
            "export_date_type": "1", "awb_master_id": "1", "service_type_code": "1",
            "customer_div": "0", "flag_return": "1", "flag_rowstate": "1",
            "origin_area_branch_code": "1", "destination_area_branch_code": "1",
            "shipment_type_code": "1", "awb_type": "1", "courier_code": "1",
        }
        payload: dict[str, str] = {"from": start, "to": end, "is_encrypted": "0"}
        for key, default in defaults.items():
            value = str(filters.get(key, "")).strip()
            payload[key] = value or default
        if " - " in payload["customer_code"]:
            payload["customer_code"] = payload["customer_code"].split(" - ", 1)[0]
        return payload

    def submit_pod_v2(self, start: str, end: str, filters: dict[str, Any]) -> dict[str, Any]:
        self.require_login()
        token, userdata = self._pod_context()
        payload = self.pod_payload(start, end, filters)
        validation = self.session.post(
            f"{BASE_URL}/pod_report_v2/is_report_exist", data=payload, timeout=90
        )
        validation.raise_for_status()
        result = validation.json()
        status = result.get("status")
        data = result.get("data") or {}

        if status == "FILE_NOT_EXIST":
            process_id = data.get("id")
            file_name = data.get("file_name")
            if not process_id or not file_name:
                raise CoresysError("Portal tidak mengembalikan ID proses POD.")
            report_payload = {
                **payload,
                "userdata": userdata,
                "process_id": process_id,
                "file_name": file_name,
                "auth_token": token,
            }
            report_response = self.session.post(
                f"{REPORT_URL}/report/pod", data=report_payload, timeout=120
            )
            report_response.raise_for_status()
            report_result = report_response.json()
            if report_result.get("success") is not True:
                raise CoresysError(report_result.get("message") or "Server laporan POD menolak proses export.")
            return {"process_id": str(process_id), "state": "processing"}

        if data.get("id"):
            return {"process_id": str(data["id"]), "state": "existing"}

        message = result.get("error") or result.get("message") or f"Validasi POD gagal: {status or 'UNKNOWN'}"
        raise CoresysError(str(message))

    def poll_pod_v2(self, process_id: str) -> dict[str, Any]:
        last_error: requests.RequestException | None = None
        for attempt in range(3):
            try:
                response = self.session.post(
                    f"{BASE_URL}/pod_report_v2/check_progress",
                    data={"id": process_id},
                    headers={"Connection": "close"},
                    timeout=45,
                )
                response.raise_for_status()
                result = response.json()
                break
            except requests.RequestException as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(attempt + 1)
        else:
            raise CoresysError(f"Koneksi polling POD terputus setelah 3 percobaan: {last_error}") from last_error

        status = int(result.get("status", 1))
        if status == 2:
            return {
                "state": "complete",
                "url": f"{REPORT_URL}/download_report/{quote(str(result['file_name']), safe='-')}/"
                f"{quote(str(result['document_name']).replace(' ', '_X_'), safe='._-')}",
            }
        if status == 0:
            return {"state": "failed", "message": result.get("message") or "Proses POD gagal."}
        return {"state": "processing"}
