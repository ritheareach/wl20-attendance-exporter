"""Parser tests: the WL20 quirks must decode from raw payloads without a device."""

from __future__ import annotations

import struct
import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from wl20_exporter import device  # noqa: E402
from wl20_exporter.models import DeviceUser, ParseReport  # noqa: E402
from synthetic import (  # noqa: E402
    attendance_payload,
    compressed_record,
    record_16,
    record_40,
    record_8,
    sample_users,
    users_payload,
)


class TimeCodecTests(unittest.TestCase):
    def test_round_trip(self):
        for stamp in (datetime(2026, 9, 15, 8, 30, 0),
                      datetime(2026, 1, 1, 0, 0, 1),
                      datetime(2030, 12, 31, 23, 59, 59)):
            raw = struct.pack("<I", (
                ((stamp.year % 100) * 12 * 31 + (stamp.month - 1) * 31 + stamp.day - 1) * 86400
                + (stamp.hour * 60 + stamp.minute) * 60 + stamp.second))
            self.assertEqual(device.decode_time(raw), stamp)

    def test_garbage_timestamp_raises(self):
        with self.assertRaises(ValueError):
            device.decode_time(b"\x00")


class UserParsingTests(unittest.TestCase):
    def test_extended_72_byte_users(self):
        users = device.parse_users_payload(users_payload(sample_users()))
        self.assertEqual([user.user_id for user in users], ["STF-0001", "STF-0002"])
        self.assertEqual(users[0].name, "SOK Dara")
        self.assertEqual(users[0].uid, 1)

    def test_empty_payload(self):
        self.assertEqual(device.parse_users_payload(b""), [])
        self.assertEqual(device.parse_users_payload(struct.pack("<I", 0)), [])


class AttendanceParsingTests(unittest.TestCase):
    def setUp(self):
        self.users = sample_users()

    def test_40_byte_records(self):
        stamps = [(1, datetime(2026, 9, 15, 8, 1, 5)), (2, datetime(2026, 9, 15, 8, 5, 30)),
                  (1, datetime(2026, 9, 15, 17, 30, 0))]
        payload = attendance_payload([
            record_40(uid, user.user_id, stamp)
            for uid, stamp in stamps
            for user in [next(item for item in self.users if item.uid == uid)]
        ])
        report = ParseReport()
        records = device.parse_attendance_payload(payload, self.users, report)
        self.assertEqual(len(records), 3)
        self.assertEqual(records[0].user_id, "STF-0001")
        self.assertEqual(records[0].name, "SOK Dara")
        self.assertEqual(records[0].timestamp, datetime(2026, 9, 15, 8, 1, 5))
        self.assertIn("40-byte", report.format_label)
        self.assertEqual(report.duplicates_dropped, 0)

    def test_16_byte_records(self):
        payload = attendance_payload([
            record_16(1, datetime(2026, 9, 15, 9, 0, 0)),
            record_16(2, datetime(2026, 9, 15, 9, 2, 0)),
        ])
        records = device.parse_attendance_payload(payload, self.users, ParseReport())
        self.assertEqual([record.user_id for record in records], ["STF-0001", "STF-0002"])
        self.assertEqual(records[1].timestamp, datetime(2026, 9, 15, 9, 2, 0))

    def test_8_byte_records(self):
        payload = attendance_payload([
            record_8(1, datetime(2026, 9, 15, 7, 45, 0), punch=0),
            record_8(1, datetime(2026, 9, 15, 18, 10, 0), punch=1),
        ])
        records = device.parse_attendance_payload(payload, self.users, ParseReport())
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].punch_text, "Check In")
        self.assertEqual(records[1].punch_text, "Check Out")

    def test_compressed_wl20_records(self):
        payload = attendance_payload([
            compressed_record(1, "STF-0001", datetime(2026, 9, 15, 8, 0, 0)),
            compressed_record(2, "STF-0002", datetime(2026, 9, 15, 8, 3, 0)),
        ])
        report = ParseReport()
        records = device.parse_attendance_payload(payload, self.users, report)
        self.assertEqual(sorted(record.user_id for record in records),
                         ["STF-0001", "STF-0002"])
        self.assertEqual(records[0].timestamp, datetime(2026, 9, 15, 8, 0, 0))

    def test_duplicates_are_dropped(self):
        stamp = datetime(2026, 9, 15, 8, 0, 0)
        payload = attendance_payload([record_40(1, "STF-0001", stamp),
                                      record_40(1, "STF-0001", stamp)])
        report = ParseReport()
        records = device.parse_attendance_payload(payload, self.users, report)
        self.assertEqual(len(records), 1)
        self.assertEqual(report.duplicates_dropped, 1)

    def test_records_are_sorted_by_time(self):
        payload = attendance_payload([
            record_40(1, "STF-0001", datetime(2026, 9, 15, 17, 0, 0)),
            record_40(1, "STF-0001", datetime(2026, 9, 15, 8, 0, 0)),
        ])
        records = device.parse_attendance_payload(payload, self.users, ParseReport())
        self.assertEqual([record.timestamp.hour for record in records], [8, 17])

    def test_garbage_payload_warns_instead_of_crashing(self):
        report = ParseReport()
        payload = struct.pack("<I", 64) + bytes(range(64))
        records = device.parse_attendance_payload(payload, self.users, report)
        self.assertEqual(records, [])
        self.assertTrue(report.warnings)

    def test_empty_payload(self):
        report = ParseReport()
        self.assertEqual(device.parse_attendance_payload(b"", self.users, report), [])
        self.assertTrue(report.warnings)

    def test_without_users_records_still_parse_and_warn(self):
        payload = attendance_payload([record_16(1, datetime(2026, 9, 15, 8, 0, 0))])
        report = ParseReport()
        records = device.parse_attendance_payload(payload, [], report)
        self.assertEqual(len(records), 1)
        self.assertTrue(any("no user list" in warning for warning in report.warnings))

    def test_size_counter_offset_variant(self):
        """Firmware that includes the counter in the declared size."""
        body = record_40(1, "STF-0001", datetime(2026, 9, 15, 8, 0, 0))
        payload = struct.pack("<I", len(body) + 4) + body
        records = device.parse_attendance_payload(payload, self.users, ParseReport())
        self.assertEqual(len(records), 1)


class FakeConnection:
    """Minimal stand-in for a pyzk connection, including the fallback path."""

    def __init__(self, users=None, attendance=None, users_payload_bytes=b"",
                 attendance_payload_bytes=b"", standard_users=True, standard_attendance=True):
        self._users = users if users is not None else []
        self._attendance = attendance if attendance is not None else []
        self._users_payload = users_payload_bytes
        self._attendance_payload = attendance_payload_bytes
        self.standard_users = standard_users
        self.standard_attendance = standard_attendance

    def get_users(self):
        return self._users if self.standard_users else []

    def get_attendance(self):
        return self._attendance if self.standard_attendance else []

    def read_with_buffer(self, command, fct=0):
        from zk import const
        if command == const.CMD_USERTEMP_RRQ:
            return self._users_payload, len(self._users_payload)
        return self._attendance_payload, len(self._attendance_payload)


class ReadPathTests(unittest.TestCase):
    """The fallback wiring must kick in when the firmware reports nothing."""

    def test_user_fallback_used_when_standard_read_empty(self):
        report = ParseReport()
        connection = FakeConnection(standard_users=False,
                                    users_payload_bytes=users_payload(sample_users()))
        users = device.read_users(connection, report)
        self.assertEqual([user.user_id for user in users], ["STF-0001", "STF-0002"])
        self.assertTrue(report.used_user_fallback)

    def test_attendance_fallback_used_when_standard_read_empty(self):
        users = sample_users()
        payload = attendance_payload([record_40(1, "STF-0001", datetime(2026, 9, 15, 8, 0, 0))])
        report = ParseReport()
        connection = FakeConnection(standard_attendance=False,
                                    attendance_payload_bytes=payload)
        records = device.read_attendance(connection, users, report)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].name, "SOK Dara")
        self.assertTrue(report.used_attendance_fallback)

    def test_standard_path_attaches_names_and_dedupes(self):
        from zk.attendance import Attendance

        users = sample_users()
        records_in = [
            Attendance("STF-0001", datetime(2026, 9, 15, 8, 0, 0), 1, 0, 1),
            Attendance("STF-0001", datetime(2026, 9, 15, 8, 0, 0), 1, 0, 1),
        ]
        report = ParseReport()
        connection = FakeConnection(users=users, attendance=records_in)
        records = device.read_attendance(connection, users, report)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].name, "SOK Dara")
        self.assertEqual(report.duplicates_dropped, 1)
        self.assertFalse(report.used_attendance_fallback)


class FilterTests(unittest.TestCase):
    def test_filtered_by_date_range(self):
        from wl20_exporter.models import DeviceRead, DeviceInfo, PunchRecord

        read = DeviceRead(info=DeviceInfo(host="10.0.0.1"), records=[
            PunchRecord(user_id="1", timestamp=datetime(2026, 9, 14, 8, 0)),
            PunchRecord(user_id="1", timestamp=datetime(2026, 9, 15, 8, 0)),
            PunchRecord(user_id="1", timestamp=datetime(2026, 9, 16, 8, 0)),
        ])
        from datetime import date
        narrowed = read.filtered(date(2026, 9, 15), date(2026, 9, 15))
        self.assertEqual(len(narrowed.records), 1)
        self.assertEqual(narrowed.records[0].timestamp.day, 15)
        self.assertEqual(len(read.records), 3, "the original read must not be mutated")


class PartialLogWarningTests(unittest.TestCase):
    """The WL20 sends one 4096-byte frame and refuses the continuation.

    Once its log grows past that, the newest punches cannot be transferred at
    all. An export must say so rather than look complete.
    """

    def setUp(self):
        self.users = sample_users()

    def test_short_payload_warns_that_the_newest_punches_are_cut_off(self):
        # Exactly what the office terminal does: the buffer declares 4400 bytes
        # (200 x 22-byte records) but only 4092 bytes of payload are delivered.
        body = b"".join(compressed_record(1, "STF-0001", datetime(2026, 9, 1, 8, 0))
                        for _ in range(260))[:4092]
        truncated = struct.pack("<I", 4400) + body
        self.assertEqual(len(truncated), 4096)

        report = ParseReport()
        device.parse_attendance_payload(truncated, self.users, report)

        warnings = " ".join(report.warnings)
        self.assertIn("partial log", warnings)
        self.assertIn("declares 4400", warnings)
        self.assertIn("cut off", warnings)
        self.assertEqual(report.declared_bytes, 4400)
        self.assertEqual(report.received_bytes, 4092)

    def test_complete_payload_is_not_flagged(self):
        payload = attendance_payload(
            [compressed_record(1, "STF-0001", datetime(2026, 9, 15, 8, 0))])
        report = ParseReport()
        device.parse_attendance_payload(payload, self.users, report)
        self.assertEqual(report.warnings, [])

    def test_firmware_that_counts_its_own_size_field_is_not_flagged(self):
        body = b"".join([compressed_record(1, "STF-0001", datetime(2026, 9, 15, 8, 0))])
        payload = struct.pack("<I", len(body) + 4) + body  # declared includes the counter
        report = ParseReport()
        device.parse_attendance_payload(payload, self.users, report)
        self.assertEqual(report.warnings, [])


class ErrorMessageTests(unittest.TestCase):
    """Connection failures must produce a hint the user can act on.

    The assertions match the hint constants rather than loose wording, so the
    sentences can be improved without silently losing the guidance.
    """

    def test_timeout_points_at_the_busy_terminal(self):
        text = device._explain(TimeoutError("timed out"))
        self.assertIn(device.BUSY_HINT, text)

    def test_refused_points_at_power_and_network(self):
        text = device._explain(ConnectionRefusedError(111, "Connection refused"))
        self.assertIn("powered", text)
        self.assertIn(device.UNREACHABLE_HINT, text)

    def test_wrapped_socket_error_is_unwrapped(self):
        class ZKNetworkError(Exception):
            pass

        try:
            try:
                raise ConnectionResetError(32, "Broken pipe")
            except OSError as exc:
                raise ZKNetworkError("ZKNetworkError: [Errno 32] Broken pipe") from exc
        except ZKNetworkError as exc:
            text = device._explain(exc)
        self.assertIn(device.UNREACHABLE_HINT, text)
        self.assertIn("ZKNetworkError", text, "the original error text must survive")

    def test_unknown_error_has_no_invented_hint(self):
        self.assertEqual(device._explain(ValueError("weird")), "ValueError: weird")


if __name__ == "__main__":
    unittest.main()
