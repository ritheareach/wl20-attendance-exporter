"""The destructive terminal-log reset must not be exposed by the CLI."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wl20_exporter import cli, device  # noqa: E402


class ClearOptionRemovalTests(unittest.TestCase):
    def test_destructive_clear_option_is_removed(self):
        help_text = cli.build_parser().format_help()
        self.assertNotIn("--clear-after-export", help_text)
        self.assertFalse(hasattr(device, "clear_attendance_log"))

    def test_destructive_clear_option_is_rejected(self):
        with mock.patch.object(sys, "stderr"):
            with self.assertRaises(SystemExit):
                cli.build_parser().parse_args(["--clear-after-export"])


if __name__ == "__main__":
    unittest.main()
