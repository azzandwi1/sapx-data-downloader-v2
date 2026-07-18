import unittest
import tempfile
import zipfile
from pathlib import Path

from coresys import CoresysClient, format_awb_text, normalize_awbs, split_awbs, split_date_range
from jobs import JobManager


class DateBatchTests(unittest.TestCase):
    def test_inclusive_batches(self):
        batches = split_date_range("2026-01-01", "2026-01-17", 7)
        self.assertEqual(
            [batch.as_dict() for batch in batches],
            [
                {"from": "2026-01-01", "to": "2026-01-07"},
                {"from": "2026-01-08", "to": "2026-01-14"},
                {"from": "2026-01-15", "to": "2026-01-17"},
            ],
        )

    def test_rejects_reverse_range(self):
        with self.assertRaises(ValueError):
            split_date_range("2026-02-02", "2026-02-01", 7)


class AwbBatchTests(unittest.TestCase):
    def test_normalizes_and_deduplicates(self):
        self.assertEqual(normalize_awbs("cgk1\nCGK2, cgk1;CGK3"), ["CGK1", "CGK2", "CGK3"])

    def test_splits_at_limit(self):
        batches = split_awbs([f"AWB{i}" for i in range(20_001)])
        self.assertEqual([len(batch) for batch in batches], [10_000, 10_000, 1])

    def test_report_payload_uses_browser_crlf_line_endings(self):
        self.assertEqual(format_awb_text(["AWB1", "AWB2"]), "AWB1\r\nAWB2")


class UrlTests(unittest.TestCase):
    def test_pickup_url_matches_portal_contract(self):
        client = CoresysClient()
        url = client.pickup_url(
            "2026-01-01",
            "2026-01-07",
            {"date_pickup": "1", "pilih_status": "0"},
            "report_monitoring_xlsx",
        )
        self.assertIn("/pickup/report_monitoring_xlsx/-/01-01-2026/07-01-2026/0/", url)
        self.assertTrue(url.endswith("?token=token_02"))


class XlsxResultTests(unittest.TestCase):
    def test_detects_header_only_awb_result(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.xlsx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("xl/worksheets/sheet1.xml", b"<sheet><row/><row/><row/></sheet>")
            self.assertEqual(JobManager._xlsx_data_rows(path, header_rows=3), 0)


if __name__ == "__main__":
    unittest.main()
