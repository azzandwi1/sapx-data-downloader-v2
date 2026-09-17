from __future__ import annotations

import re
from pathlib import Path
from typing import Any, BinaryIO

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


HEADER_FILL = PatternFill("solid", fgColor="1B5E20")  # Dark green professional theme
HEADER_FONT = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
ROW_FONT = Font(name="Segoe UI", size=9)
THIN_BORDER = Border(
    left=Side(style="thin", color="E0E0E0"),
    right=Side(style="thin", color="E0E0E0"),
    top=Side(style="thin", color="E0E0E0"),
    bottom=Side(style="thin", color="E0E0E0"),
)

OUTPUT_COLUMNS = [
    ("no", "No", 6, "center"),
    ("reference_no", "No. Referance", 22, "left"),
    ("awb_no", "No. AWB", 20, "center"),
    ("master_no", "No. Master", 15, "center"),
    ("date", "Tanggal", 14, "center"),
    ("origin", "Asal", 16, "left"),
    ("origin_district", "District Asal", 16, "left"),
    ("destination", "Tujuan", 18, "left"),
    ("destination_city", "Kota Tujuan", 18, "left"),
    ("service_type", "Jenis Layanan", 15, "center"),
    ("transaction_type", "Transaksi", 12, "center"),
    ("weight_kg", "Kilo", 8, "center"),
    ("koli", "Koli", 8, "center"),
    ("invoice_no", "No Invoice", 18, "center"),
    ("status", "Status", 20, "left"),
    ("detail_status", "Detail Status", 35, "left"),
    ("max_sla", "Max SLA", 12, "center"),
    ("shipping_duration", "Shipping Duration", 16, "center"),
    ("sla_status", "SLA Status", 24, "center"),
    ("pickup_cn_no", "No. Resi Pickup", 18, "center"),
    ("created_by", "Dibuat Oleh", 16, "center"),
    ("pod_by", "Di POD Oleh", 16, "center"),
]


def _cell_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def read_reference_targets_workbook(source: BinaryIO) -> list[str]:
    workbook = load_workbook(source, read_only=True, data_only=True)
    try:
        sheet = workbook[workbook.sheetnames[0]]
        header_row = None
        target_column = None

        for row_number, row in enumerate(sheet.iter_rows(max_row=25, values_only=True), start=1):
            labels = [re.sub(r"[^A-Z0-9]+", " ", _cell_text(val).upper()).strip() for val in row]
            for col_idx, label in enumerate(labels):
                if any(k in label for k in ("REFERANCE", "REFERENCE", "REFERENSI", "AWB", "RESI")):
                    header_row = row_number
                    target_column = col_idx
                    break
            if header_row is not None:
                break

        # If no explicit header matched, find the first column with non-empty string on row 1 or 2
        if header_row is None or target_column is None:
            header_row = 1
            target_column = 0

        seen: set[str] = set()
        targets: list[str] = []
        for row in sheet.iter_rows(min_row=header_row + 1, values_only=True):
            if not row or target_column >= len(row):
                continue
            raw_val = _cell_text(row[target_column]).strip()
            if not raw_val or raw_val.lower() == "none":
                continue
            # Normalization
            val = re.sub(r"[\s\t\r\n]+", "", raw_val)
            if val and val not in seen:
                seen.add(val)
                targets.append(val)

        if not targets:
            raise ValueError("Tidak ada nomor referensi/AWB yang valid pada file Excel.")
        return targets
    finally:
        workbook.close()


def export_tracking_focus(
    records: list[dict[str, Any]],
    targets: list[str],
    output_path: Path,
    search_by: str = "a.reference_no",
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Riwayat Tracking Focus"
    ws.views.sheetView[0].showGridLines = True

    # Build index map: map target key to list of records
    # If search_by is reference_no, index by reference_no. If awb_no, index by awb_no, etc.
    key_field = "reference_no" if "reference" in search_by else "awb_no"
    if "cn_no" in search_by:
        key_field = "pickup_cn_no"

    indexed_records: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        val = str(r.get(key_field, "")).strip().upper()
        if val:
            indexed_records.setdefault(val, []).append(r)

    # Write headers
    headers = [col[1] for col in OUTPUT_COLUMNS]
    ws.append(headers)

    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # Write data rows
    row_counter = 1
    matched_targets = set()

    for target in targets:
        target_upper = target.strip().upper()
        matches = indexed_records.get(target_upper, [])
        if matches:
            matched_targets.add(target_upper)
            for m in matches:
                row_data = [
                    row_counter,
                    m.get("reference_no", ""),
                    m.get("awb_no", ""),
                    m.get("master_no", ""),
                    m.get("date", ""),
                    m.get("origin", ""),
                    m.get("origin_district", ""),
                    m.get("destination", ""),
                    m.get("destination_city", ""),
                    m.get("service_type", ""),
                    m.get("transaction_type", ""),
                    m.get("weight_kg", ""),
                    m.get("koli", ""),
                    m.get("invoice_no", ""),
                    m.get("status", ""),
                    m.get("detail_status", ""),
                    m.get("max_sla", ""),
                    m.get("shipping_duration", ""),
                    m.get("sla_status", ""),
                    m.get("pickup_cn_no", ""),
                    m.get("created_by", ""),
                    m.get("pod_by", ""),
                ]
                ws.append(row_data)
                curr_row = ws.max_row
                for col_idx, col_cfg in enumerate(OUTPUT_COLUMNS, start=1):
                    c = ws.cell(row=curr_row, column=col_idx)
                    c.font = ROW_FONT
                    c.border = THIN_BORDER
                    c.alignment = Alignment(horizontal=col_cfg[3], vertical="center")
                row_counter += 1
        else:
            # Not found row
            not_found_ref = target if key_field == "reference_no" else "-"
            not_found_awb = target if key_field == "awb_no" else "-"
            row_data = [
                row_counter,
                not_found_ref,
                not_found_awb,
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
                "TIDAK DITEMUKAN",
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
                "-",
            ]
            ws.append(row_data)
            curr_row = ws.max_row
            for col_idx, col_cfg in enumerate(OUTPUT_COLUMNS, start=1):
                c = ws.cell(row=curr_row, column=col_idx)
                c.font = ROW_FONT
                c.border = THIN_BORDER
                c.alignment = Alignment(horizontal=col_cfg[3], vertical="center")
            row_counter += 1

    # Also add any portal records that weren't matched to an exact target in targets list (e.g. if extra AWB returned)
    for key_val, extra_records in indexed_records.items():
        if key_val not in matched_targets:
            for m in extra_records:
                row_data = [
                    row_counter,
                    m.get("reference_no", ""),
                    m.get("awb_no", ""),
                    m.get("master_no", ""),
                    m.get("date", ""),
                    m.get("origin", ""),
                    m.get("origin_district", ""),
                    m.get("destination", ""),
                    m.get("destination_city", ""),
                    m.get("service_type", ""),
                    m.get("transaction_type", ""),
                    m.get("weight_kg", ""),
                    m.get("koli", ""),
                    m.get("invoice_no", ""),
                    m.get("status", ""),
                    m.get("detail_status", ""),
                    m.get("max_sla", ""),
                    m.get("shipping_duration", ""),
                    m.get("sla_status", ""),
                    m.get("pickup_cn_no", ""),
                    m.get("created_by", ""),
                    m.get("pod_by", ""),
                ]
                ws.append(row_data)
                curr_row = ws.max_row
                for col_idx, col_cfg in enumerate(OUTPUT_COLUMNS, start=1):
                    c = ws.cell(row=curr_row, column=col_idx)
                    c.font = ROW_FONT
                    c.border = THIN_BORDER
                    c.alignment = Alignment(horizontal=col_cfg[3], vertical="center")
                row_counter += 1

    # Set column widths
    for col_idx, col_cfg in enumerate(OUTPUT_COLUMNS, start=1):
        col_letter = get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = col_cfg[2]

    ws.freeze_panes = "A2"
    wb.save(output_path)
    return output_path
