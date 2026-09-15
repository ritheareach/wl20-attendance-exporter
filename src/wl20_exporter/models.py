"""Data structures shared by the reader, the summary and the exporter.

Nothing in here depends on pyzk: the network layer converts pyzk objects into
these plain dataclasses so the summary/excel/CLI/GUI layers stay testable
without a device attached.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional


# ---------------------------------------------------------------------------
# ZK protocol enums (labels)
# ---------------------------------------------------------------------------

# `punch` field of an attendance record (a.k.a. punch state).
PUNCH_LABELS = {
    0: "Check In",
    1: "Check Out",
    2: "Break Out",
    3: "Break In",
    4: "Overtime In",
    5: "Overtime Out",
}

# `status` field = how the user was verified on the terminal.
VERIFY_LABELS = {
    0: "Password",
    1: "Fingerprint",
    2: "Card",
    3: "Fingerprint+Card",
    15: "Face",
    16: "Face+Fingerprint",
}


def punch_label(value) -> str:
    try:
        return PUNCH_LABELS.get(int(value), f"Punch {value}")
    except (TypeError, ValueError):
        return str(value)


def verify_label(value) -> str:
    try:
        return VERIFY_LABELS.get(int(value), f"Mode {value}")
    except (TypeError, ValueError):
        return str(value)


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeviceUser:
    """A user enrolled on the terminal."""

    uid: int
    user_id: str
    name: str = ""
    privilege: int = 0
    card: str = ""
    group_id: str = ""


@dataclass(frozen=True)
class PunchRecord:
    """One attendance punch read from the terminal."""

    user_id: str
    timestamp: datetime
    status: int = 0
    punch: int = 0
    uid: int = 0
    name: str = ""
    device_user_id: str = ""

    @property
    def day(self) -> date:
        return self.timestamp.date()

    @property
    def punch_text(self) -> str:
        return punch_label(self.punch)

    @property
    def verify_text(self) -> str:
        return verify_label(self.status)


@dataclass
class DeviceInfo:
    """Identity / capacity block of the terminal."""

    host: str = ""
    port: int = 4370
    name: str = ""
    serial: str = ""
    firmware: str = ""
    platform: str = ""
    users: int = 0
    records: int = 0
    users_cap: int = 0
    records_cap: int = 0


@dataclass
class ParseReport:
    """How the raw attendance payload was decoded (shown in Diagnostics)."""

    format_label: str = "unknown"
    record_size: int = 0
    offset: int = 0
    declared_bytes: int = 0
    received_bytes: int = 0
    raw_records_read: int = 0
    duplicates_dropped: int = 0
    users_parsed: int = 0
    used_user_fallback: bool = False
    used_attendance_fallback: bool = False
    warnings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def add_warning(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def add_note(self, message: str) -> None:
        self.notes.append(message)


@dataclass
class DeviceRead:
    """Everything one read of the terminal produced."""

    info: DeviceInfo
    users: List[DeviceUser] = field(default_factory=list)
    records: List[PunchRecord] = field(default_factory=list)
    report: ParseReport = field(default_factory=ParseReport)
    duration_seconds: float = 0.0

    def filtered(self, start=None, end=None) -> "DeviceRead":
        """Return a copy restricted to [start, end] dates (inclusive)."""
        records = self.records
        if start is not None:
            records = [item for item in records if item.timestamp.date() >= start]
        if end is not None:
            records = [item for item in records if item.timestamp.date() <= end]
        return DeviceRead(info=self.info, users=self.users, records=records,
                          report=self.report, duration_seconds=self.duration_seconds)


@dataclass
class DailyRow:
    """One person on one day — first in, last out, hours."""

    day: date
    user_id: str
    name: str
    first_in: Optional[datetime] = None
    last_out: Optional[datetime] = None
    punches: int = 0
    hours: float = 0.0
    minutes: int = 0

    @property
    def single_punch(self) -> bool:
        return self.punches <= 1

    @property
    def hours_text(self) -> str:
        """Hours the way the office log writes them: 9h19mn, 0h07mn."""
        return f"{self.minutes // 60}h{self.minutes % 60:02d}mn"

    @property
    def has_checkout(self) -> bool:
        return self.punches > 1

    @property
    def status_text(self) -> str:
        """Present = one punch (no check-out yet), Completed = in and out."""
        return "Completed" if self.punches > 1 else "Present"
