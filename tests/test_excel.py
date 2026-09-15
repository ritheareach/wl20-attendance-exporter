"""Excel/CSV export tests — the workbook must be openable and complete."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from openpyxl import load_workbook  # noqa: E402

from wl20_exporter import excel  # noqa: E402
from wl20_exporter.models import (  # noqa: E402
    DeviceInfo,
    DeviceRead,
    DeviceUser,
    ParseReport,
    PunchRecord,
)


def sample_read() -> DeviceRead:
    records = [
        PunchRecord(user_id="STF-0001", name="SOK Dara", uid=1,
                    timestamp=datetime(2026, 9, 14, 8, 1, 5), punch=0, status=1),
        PunchRecord(user_id="STF-0001", name="SOK Dara", uid=1,
                    timestamp=datetime(2026, 9, 14, 17, 30, 0), punch=1, status=1),
        PunchRecord(user_id="STF-0002", name="CHHIM Sokha", uid=2,
                    timestamp=datetime(2026, 9, 15, 8, 12, 30), punch=0, status=1),
    ]
    report = ParseReport(format_label="40-byte records", declared_bytes=120,
                         received_bytes=120, raw_records_read=3, users_parsed=2,
                         notes=["decoded range: 2026-09-14 08:01:05 .. 2026-09-15 08:12:30"])
    return DeviceRead(
        info=DeviceInfo(host="192.168.88.245", port=4370, name="WL20",
                        serial="A5KN203360148", firmware="Ver 6.60", users=2, records=3),
        users=[DeviceUser(uid=1, user_id="STF-0001", name="SOK Dara"),
               DeviceUser(uid=2, user_id="STF-0002", name="CHHIM Sokha")],
        records=records,
        report=report,
        duration_seconds=4.2,
    )


class WorkbookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "out.xlsx"

    def tearDown(self):
        self.tmp.cleanup()

    def test_workbook_structure(self):
        written = excel.export_workbook(self.path, sample_read(),
                                        date(2026, 9, 14), date(2026, 9, 15))
        self.assertTrue(written.is_file())
        workbook = load_workbook(written)
        self.assertEqual(workbook.sheetnames,
                         ["Attendance", "Daily Summary", "Device Info", "Diagnostics"])

        sheet = workbook["Attendance"]
        headers = [cell.value for cell in sheet[1]]
        self.assertEqual(len(headers), 10)
        self.assertIn("Date (កាលបរិច្ឆេទ)", headers)
        self.assertEqual(sheet.max_row, 4, "header + 3 records")
        self.assertEqual(sheet.cell(row=2, column=4).value, "STF-0001")
        self.assertEqual(sheet.cell(row=2, column=5).value, "SOK Dara")
        self.assertEqual(sheet.cell(row=2, column=7).value, "Check In")
        self.assertEqual(sheet.cell(row=4, column=7).value, "Check In")
        self.assertEqual(sheet.cell(row=2, column=2).value.date(), date(2026, 9, 14))
        self.assertEqual(sheet.cell(row=2, column=2).number_format, "dd-mm-yyyy",
                         "dates must display as DD-MM-YYYY")

    def test_summary_sheet_has_first_last_and_total(self):
        excel.export_workbook(self.path, sample_read())
        sheet = load_workbook(self.path)["Daily Summary"]
        self.assertEqual(sheet.cell(row=1, column=1).value, "No.")
        # 3 rows of data: two days for STF-0001/STF-0002
        self.assertEqual(sheet.cell(row=2, column=3).value, "STF-0001")
        self.assertEqual(sheet.cell(row=2, column=7).value, 9.48)
        self.assertEqual(sheet.cell(row=2, column=8).value, 2)
        self.assertEqual(sheet.cell(row=3, column=4).value, "CHHIM Sokha")
        self.assertEqual(sheet.cell(row=3, column=9).value, "single punch only")
        totals_row = 4  # 2 person-days + header
        self.assertEqual(sheet.cell(row=totals_row, column=1).value, "TOTAL")
        self.assertIn("2 staff", sheet.cell(row=totals_row, column=4).value)

    def test_device_and_diagnostics_sheets(self):
        excel.export_workbook(self.path, sample_read())
        workbook = load_workbook(self.path)
        info_values = [cell.value for row in workbook["Device Info"].iter_rows()
                       for cell in row]
        self.assertIn("A5KN203360148", info_values)
        self.assertIn("WL20 Attendance Exporter", info_values)
        diag = [cell.value for row in workbook["Diagnostics"].iter_rows() for cell in row]
        self.assertIn("40-byte records", diag)
        self.assertIn("none", diag)  # no warnings

    def test_empty_read_still_writes_a_workbook(self):
        empty = DeviceRead(info=DeviceInfo(host="10.0.0.9"), report=ParseReport())
        excel.export_workbook(self.path, empty)
        workbook = load_workbook(self.path)
        self.assertEqual(workbook["Attendance"].max_row, 1)


class CsvTests(unittest.TestCase):
    def test_csv_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "records.csv"
            excel.export_csv(path, sample_read().records)
            text = path.read_text(encoding="utf-8-sig")
            lines = text.strip().splitlines()
            self.assertEqual(len(lines), 4)
            self.assertTrue(lines[0].startswith("date,time,user_id"))
            self.assertIn("STF-0001", lines[1])
            self.assertIn("14-09-2026,08:01:05", lines[1])
            self.assertIn("14-09-2026 08:01:05", lines[1])


class FilenameTests(unittest.TestCase):
    def test_default_filename_uses_dd_mm_yyyy(self):
        name = excel.default_filename(date(2026, 9, 1), date(2026, 9, 15))
        self.assertTrue(name.startswith("WL20_Attendance_01-09-2026_to_15-09-2026_"))
        self.assertTrue(name.endswith(".xlsx"))
        self.assertIn("all", excel.default_filename(None, None))


if __name__ == "__main__":
    unittest.main()
