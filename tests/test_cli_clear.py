"""`--clear-after-export` is destructive: it must never run without an export.

The terminal's copy of the punches is what the erase removes, so the guard that
matters is "no workbook on disk -> no erase", whatever fails on the way there.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wl20_exporter import cli, device, excel  # noqa: E402
from wl20_exporter.models import DeviceInfo, DeviceRead, PunchRecord  # noqa: E402


def sample_read() -> DeviceRead:
    return DeviceRead(info=DeviceInfo(host="192.168.88.245", name="WL20"),
                      records=[PunchRecord(user_id="4", timestamp=datetime(2026, 9, 17, 8, 0, 0))])


class ClearAfterExportGuardTests(unittest.TestCase):
    def setUp(self):
        self.cleared = []

        def fake_clear(host, port=4370, password=0, timeout=10, progress=None):
            self.cleared.append(host)
            return True

        self._original_clear = device.clear_attendance_log
        device.clear_attendance_log = fake_clear
        self.addCleanup(lambda: setattr(device, "clear_attendance_log", self._original_clear))

        self._original_read = device.read_with_retry
        device.read_with_retry = lambda *args, **kwargs: sample_read()
        self.addCleanup(lambda: setattr(device, "read_with_retry", self._original_read))

    def test_failed_read_never_reaches_the_erase(self):
        def boom(*args, **kwargs):
            raise device.DeviceError("timed out")
        device.read_with_retry = boom

        code = cli.main(["--clear-after-export", "--out", "/tmp/should-not-exist.xlsx"])
        self.assertEqual(code, 2)
        self.assertEqual(self.cleared, [], "the log must not be erased when nothing was read")

    def test_failed_export_never_reaches_the_erase(self):
        """An export that raises must abort before the erase, on any platform."""
        def boom(*args, **kwargs):
            raise OSError("disk full or no permission")
        original = excel.export_workbook
        excel.export_workbook = boom
        self.addCleanup(lambda: setattr(excel, "export_workbook", original))

        code = cli.main(["--clear-after-export"])
        self.assertEqual(code, 3)
        self.assertEqual(self.cleared, [], "the log must not be erased when nothing was read")

    def test_erases_only_when_a_workbook_really_exists(self):
        """Claiming success is not enough: the file has to be on disk."""
        original = excel.export_workbook
        excel.export_workbook = lambda path, *args, **kwargs: Path(path)  # writes nothing
        self.addCleanup(lambda: setattr(excel, "export_workbook", original))

        with tempfile.TemporaryDirectory() as tmp:
            code = cli.main(["--clear-after-export", "--out", str(Path(tmp) / "never.xlsx")])
        self.assertEqual(code, 4)
        self.assertEqual(self.cleared, [], "no workbook on disk means no erase")

    def test_erases_only_after_the_workbook_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "attendance.xlsx"
            code = cli.main(["--clear-after-export", "--out", str(target), "--limit", "0"])
            self.assertEqual(code, 0)
            self.assertTrue(target.is_file())
            self.assertEqual(self.cleared, ["192.168.88.245"])

    def test_without_the_flag_nothing_is_erased(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = cli.main(["--out", str(Path(tmp) / "plain.xlsx")])
            self.assertEqual(code, 0)
            self.assertEqual(self.cleared, [])


class ClearFlagDocumentationTests(unittest.TestCase):
    def test_the_flag_says_it_is_one_way(self):
        parser = cli.build_parser()
        help_text = parser.format_help()
        self.assertIn("--clear-after-export", help_text)
        action = next(a for a in parser._actions if a.dest == "clear_after_export")
        self.assertIn("one-way", action.help)


if __name__ == "__main__":
    unittest.main()
