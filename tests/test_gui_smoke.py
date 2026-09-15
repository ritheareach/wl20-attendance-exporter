"""GUI smoke test — runs the real PySide6 window offscreen (no display needed)."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:  # pragma: no cover - PySide6 is a hard runtime dep, but keep CI honest
    HAVE_QT = False

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
                    timestamp=datetime(2026, 9, 15, 8, 1, 5), punch=0, status=1),
        PunchRecord(user_id="STF-0001", name="SOK Dara", uid=1,
                    timestamp=datetime(2026, 9, 15, 17, 30, 0), punch=1, status=1),
        PunchRecord(user_id="STF-0002", name="CHHIM Sokha", uid=2,
                    timestamp=datetime(2026, 9, 15, 8, 12, 30), punch=0, status=1),
    ]
    return DeviceRead(
        info=DeviceInfo(host="192.168.88.245", name="WL20", serial="A5KN203360148",
                        firmware="Ver 6.60", users=2, records=3),
        users=[DeviceUser(uid=1, user_id="STF-0001", name="SOK Dara")],
        records=records,
        report=ParseReport(format_label="40-byte records", raw_records_read=3,
                           users_parsed=2, declared_bytes=120, received_bytes=120),
        duration_seconds=3.1,
    )


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class GuiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from wl20_exporter import config, gui

        self.tmp = tempfile.TemporaryDirectory()
        self._original_dir = config.app_data_dir
        config.app_data_dir = lambda: Path(self.tmp.name)
        self.window = gui.MainWindow()

    def tearDown(self):
        from wl20_exporter import config

        self.window.close()
        config.app_data_dir = self._original_dir
        self.tmp.cleanup()

    def test_window_builds_with_expected_widgets(self):
        self.assertEqual(self.window.tabs.count(), 4)
        self.assertEqual(self.window.records_model.columnCount(), 8)
        self.assertFalse(self.window.export_button.isEnabled())
        self.assertEqual(self.window.preset_combo.currentText(), "Last 30 days")
        self.assertTrue(self.window.from_edit.isEnabled())

    def test_dates_display_as_dd_mm_yyyy(self):
        self.assertEqual(self.window.from_edit.displayFormat(), "dd-MM-yyyy")
        self.assertEqual(self.window.to_edit.displayFormat(), "dd-MM-yyyy")
        self.window.preset_combo.setCurrentText("All records")
        self.window.on_fetched(sample_read())
        first_date = self.window.records_proxy.index(0, 0).data()
        self.assertRegex(first_date, r"^\d{2}-\d{2}-\d{4}$")
        self.assertEqual(self.window.summary_model.index(0, 0).data(), "15-09-2026")

    def test_preset_all_records_disables_dates(self):
        self.window.preset_combo.setCurrentText("All records")
        self.assertFalse(self.window.from_edit.isEnabled())
        self.assertIsNone(self.window._selected_dates()[0])

    def test_fetched_data_populates_tables(self):
        self.window.preset_combo.setCurrentText("All records")
        self.window.on_fetched(sample_read())
        self.assertEqual(self.window.records_model.rowCount(), 3)
        self.assertEqual(self.window.summary_model.rowCount(), 2)
        self.assertTrue(self.window.export_button.isEnabled())
        self.assertTrue(self.window.csv_button.isEnabled())
        self.assertEqual(self.window.tabs.currentIndex(), 0)
        self.assertIn("3 record(s)", self.window.records_count.text())
        self.assertIn("2 staff", self.window.summary_totals_label.text())
        self.assertIn("40-byte records",
                      self.window.log_view.toPlainText())

    def test_search_filter_matches_name_and_id(self):
        self.window.preset_combo.setCurrentText("All records")
        self.window.on_fetched(sample_read())
        self.window.filter_edit.setText("Kimly")
        self.assertEqual(self.window.records_proxy.rowCount(), 1)
        self.window.filter_edit.setText("STF-0001")
        self.assertEqual(self.window.records_proxy.rowCount(), 2)
        self.window.filter_edit.setText("")
        self.assertEqual(self.window.records_proxy.rowCount(), 3)

    def test_sorting_by_date_column(self):
        self.window.preset_combo.setCurrentText("All records")
        self.window.on_fetched(sample_read())
        self.window.records_view.sortByColumn(4, Qt.DescendingOrder)
        first = self.window.records_proxy.index(0, 4).data()
        self.assertEqual(first, "Check Out")

    def test_date_range_filters_records(self):
        read = sample_read()
        self.window.on_fetched(read)
        self.window.preset_combo.setCurrentText("Custom")
        self.window.from_edit.setDate(self.window.to_edit.date())
        self.window.on_fetched(read)
        self.assertEqual(self.window.last_range[0], self.window.last_range[1])

    def test_failure_path_sets_pill_without_crashing(self):
        from PySide6.QtWidgets import QMessageBox

        original = QMessageBox.critical
        QMessageBox.critical = staticmethod(lambda *args, **kwargs: None)
        try:
            self.window.on_failed("DeviceError: connection timed out")
        finally:
            QMessageBox.critical = original
        self.assertEqual(self.window.device_pill.text(), "Connection failed")
        self.assertIn("connection timed out", self.window.log_view.toPlainText())
        self.assertFalse(self.window.progress.isVisible())

    def test_settings_round_trip(self):
        from wl20_exporter import config

        self.window.host_edit.setText("10.1.2.3")
        self.window.port_spin.setValue(4371)
        self.window._persist_settings()
        stored = config.load()
        self.assertEqual(stored["host"], "10.1.2.3")
        self.assertEqual(stored["port"], 4371)

    def test_export_writes_workbook_from_gui_state(self):
        from openpyxl import load_workbook

        from wl20_exporter import excel

        self.window.preset_combo.setCurrentText("All records")
        self.window.on_fetched(sample_read())
        filtered = self.window.read_result.filtered(*self.window.last_range)
        target = Path(self.tmp.name) / "gui_export.xlsx"
        excel.export_workbook(target, filtered, *self.window.last_range)
        self.assertEqual(load_workbook(target)["Attendance"].max_row, 4)


if __name__ == "__main__":
    unittest.main()
