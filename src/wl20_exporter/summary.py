"""Daily attendance summary (first check-in / last check-out / hours)."""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime
from typing import Iterable, List, Optional

from .models import DailyRow, PunchRecord


def build_daily_rows(records: Iterable[PunchRecord], default_name: str = "") -> List[DailyRow]:
    """Group punches per (user, day) and compute the classic HR numbers.

    Rows are sorted by date then user id, which is how HR reads the sheet.
    A person who punched once gets hours = 0 and `single_punch = True` so the
    sheet can flag it instead of silently reporting a zero-length day.
    """
    buckets: "OrderedDict[tuple, DailyRow]" = OrderedDict()
    for record in records:
        key = (record.day, str(record.user_id))
        row = buckets.get(key)
        if row is None:
            row = DailyRow(day=record.day, user_id=str(record.user_id),
                           name=record.name or default_name)
            buckets[key] = row
        elif not row.name and (record.name or default_name):
            row.name = record.name or default_name
        stamp: datetime = record.timestamp
        if row.first_in is None or stamp < row.first_in:
            row.first_in = stamp
        if row.last_out is None or stamp > row.last_out:
            row.last_out = stamp
        row.punches += 1

    rows = list(buckets.values())
    for row in rows:
        if row.first_in and row.last_out and row.last_out > row.first_in:
            seconds = (row.last_out - row.first_in).total_seconds()
            row.hours = round(seconds / 3600.0, 2)
            row.minutes = int(seconds // 60)
        else:
            row.hours = 0.0
            row.minutes = 0
    rows.sort(key=lambda item: (item.day, _user_sort_key(item.user_id)))
    return rows


def _user_sort_key(user_id: str):
    """Sort numeric ids numerically, keep text ids after them."""
    text = str(user_id)
    return (0, int(text), "") if text.isdigit() else (1, 0, text.lower())


def summary_totals(rows: Iterable[DailyRow]) -> dict:
    rows = list(rows)
    people = {row.user_id for row in rows}
    days = {row.day for row in rows}
    return {
        "people": len(people),
        "days": len(days),
        "hours": round(sum(row.hours for row in rows), 2),
        "single_punch": sum(1 for row in rows if row.single_punch),
    }
