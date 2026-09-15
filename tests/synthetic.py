"""Synthetic WL20 payload builders shared by the parser tests."""

from __future__ import annotations

import struct
from datetime import datetime
from typing import List, Sequence

from wl20_exporter.models import DeviceUser


def encode_time(stamp: datetime) -> bytes:
    """Inverse of device.decode_time (same formula as zkemsdk.c EncodeTime)."""
    value = (
        ((stamp.year % 100) * 12 * 31 + (stamp.month - 1) * 31 + stamp.day - 1) * 86400
        + (stamp.hour * 60 + stamp.minute) * 60
        + stamp.second
    )
    return struct.pack("<I", value)


def user_record(uid: int, user_id: str, name: str, privilege: int = 0,
                card: int = 0, group_id: str = "1") -> bytes:
    """72-byte extended user structure used by this WL20 firmware."""
    return struct.pack(
        "<HB8s24sIx7sx24s",
        uid,
        privilege,
        b"\x00" * 8,
        name.encode("utf-8").ljust(24, b"\x00")[:24],
        card,
        group_id.encode("utf-8").ljust(7, b"\x00")[:7],
        user_id.encode("utf-8").ljust(24, b"\x00")[:24],
    )


def users_payload(users: Sequence[DeviceUser]) -> bytes:
    body = b"".join(user_record(user.uid, user.user_id, user.name) for user in users)
    return struct.pack("<I", len(body)) + body


def record_40(uid: int, user_id: str, stamp: datetime, status: int = 1,
              punch: int = 0) -> bytes:
    return struct.pack("<H24sB4sB8s", uid,
                       user_id.encode("utf-8").ljust(24, b"\x00")[:24],
                       status, encode_time(stamp), punch, b"\x00" * 8)


def record_16(uid: int, stamp: datetime, status: int = 1, punch: int = 0) -> bytes:
    return struct.pack("<I4sBB2sI", uid, encode_time(stamp), status, punch, b"\x00" * 2, 0)


def record_8(uid: int, stamp: datetime, status: int = 1, punch: int = 0) -> bytes:
    return struct.pack("<HB4sB", uid, status, encode_time(stamp), punch)


def attendance_payload(records: Sequence[bytes]) -> bytes:
    body = b"".join(records)
    return struct.pack("<I", len(body)) + body


def compressed_record(uid: int, user_id: str, stamp: datetime, status: int = 1,
                      punch: int = 0) -> bytes:
    """WL20 22-byte compressed layout: uid, last id char, status, punch, 8 filler, time."""
    return (struct.pack("<H", uid)          # uid
            + user_id[-1].encode("utf-8")   # printable user id tail
            + bytes([status, punch])        # status, punch
            + b"\x00" * 8                   # unknown payload
            + encode_time(stamp))           # 4-byte packed timestamp


def sample_users() -> List[DeviceUser]:
    return [
        DeviceUser(uid=1, user_id="STF-0001", name="SOK Dara"),
        DeviceUser(uid=2, user_id="STF-0002", name="CHHIM Sokha"),
    ]
