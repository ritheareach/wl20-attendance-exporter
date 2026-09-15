"""Daily summary math tests."""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wl20_exporter.models import PunchRecord  # noqa: E402
from wl20_exporter.summary import build_daily_rows, summary_totals  # noqa: E402


def punches(user_id: str, name: str, *stamps) -> list:
    return [PunchRecord(user_id=user_id, name=name, timestamp=stamp) for stamp in stamps]


class DailySummaryTests(unittest.TestCase):
    def test_first_in_last_out_and_hours(self):
        records = punches(
            "STF-0001", "SOK Dara",
            datetime(2026, 9, 15, 8, 1, 0),
            datetime(2026, 9, 15, 12, 0, 0),
            datetime(2026, 9, 15, 17, 30, 0),
        )
        rows = build_daily_rows(records)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.first_in, datetime(2026, 9, 15, 8, 1, 0))
        self.assertEqual(row.last_out, datetime(2026, 9, 15, 17, 30, 0))
        self.assertEqual(row.punches, 3)
        self.assertEqual(row.hours, 9.48)
        self.assertFalse(row.single_punch)

    def test_single_punch_day_is_flagged_with_zero_hours(self):
        rows = build_daily_rows(punches("STF-0002", "CHHIM Sokha",
                                        datetime(2026, 9, 15, 8, 12, 0)))
        self.assertEqual(rows[0].hours, 0.0)
        self.assertTrue(rows[0].single_punch)

    def test_multiple_days_and_people_sorted(self):
        records = (punches("2", "B", datetime(2026, 9, 16, 8, 0, 0))
                   + punches("1", "A", datetime(2026, 9, 15, 8, 0, 0),
                             datetime(2026, 9, 15, 17, 0, 0))
                   + punches("10", "C", datetime(2026, 9, 15, 9, 0, 0)))
        rows = build_daily_rows(records)
        self.assertEqual([(row.day, row.user_id) for row in rows],
                         [(date(2026, 9, 15), "1"), (date(2026, 9, 15), "10"),
                          (date(2026, 9, 16), "2")])

    def test_totals(self):
        records = (punches("1", "A", datetime(2026, 9, 15, 8, 0, 0),
                           datetime(2026, 9, 15, 17, 0, 0))
                   + punches("2", "B", datetime(2026, 9, 15, 8, 0, 0)))
        totals = summary_totals(build_daily_rows(records))
        self.assertEqual(totals["people"], 2)
        self.assertEqual(totals["days"], 1)
        self.assertEqual(totals["hours"], 9.0)
        self.assertEqual(totals["single_punch"], 1)
        self.assertTrue(all(row.name for row in build_daily_rows(records)))


if __name__ == "__main__":
    unittest.main()
