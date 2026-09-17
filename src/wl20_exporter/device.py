"""Read attendance from a ZKTeco WL20 terminal — strictly read-only.

The WL20 firmware this office runs reports zero users/records in its size
counter and uses non-standard record layouts, so the read path has two layers:

1. the normal pyzk call (``get_users`` / ``get_attendance``), and
2. a raw-payload fallback that scans the buffer for a record layout that
   produces valid timestamps (8 / 16 / 40 byte records, then the 22-byte
   compressed WL20 layout).

The parsing functions at the top are pure (payload in, records out) so they can
be unit-tested without the device, and so the same code can be reused by the
server-side service. Nothing here ever writes to the terminal: no clear, no
delete, no user upload, no time set.
"""

from __future__ import annotations

import socket
import struct
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

from .models import (
    DeviceInfo,
    DeviceRead,
    DeviceUser,
    ParseReport,
    PunchRecord,
)

DEFAULT_HOST = "192.168.88.245"
DEFAULT_PORT = 4370
DEFAULT_TIMEOUT = 10
# The terminal takes roughly 1-2 minutes to boot after a remote restart.
RESTART_WAIT = 180.0

# Timestamps outside this window are treated as mis-decoded garbage.
MIN_YEAR = 2015
MAX_YEAR = 2035

ProgressFn = Optional[Callable[[str], None]]

BUSY_HINT = (
    "The terminal is busy or the link is slow: while another program is talking "
    "to it, a read can time out. Wait a moment and try again, or use "
    "'Restart terminal' if it stays stuck."
)

UNREACHABLE_HINT = (
    "Check the address, that the terminal is powered, and that this computer is "
    "on the same office network as it. A firewall or a different Wi-Fi/SSID "
    "(for example a guest network) also looks exactly like this."
)


class DeviceError(RuntimeError):
    """Any failure while talking to the terminal, with a human hint."""


# ---------------------------------------------------------------------------
# Time decoders (same math as zkemsdk.c / pyzk)
# ---------------------------------------------------------------------------


def decode_time(raw: bytes) -> datetime:
    """Decode the 4-byte packed timestamp used in attendance records."""
    if len(raw) < 4:
        raise ValueError("timestamp needs 4 bytes")
    value = struct.unpack("<I", raw[:4])[0]
    second = value % 60
    value //= 60
    minute = value % 60
    value //= 60
    hour = value % 24
    value //= 24
    day = value % 31 + 1
    value //= 31
    month = value % 12 + 1
    value //= 12
    year = value + 2000
    return datetime(year, month, day, hour, minute, second)


def decode_time_hex(raw: bytes) -> datetime:
    """Decode the 6-byte BCD-ish timestamp used by realtime events."""
    year, month, day, hour, minute, second = struct.unpack("6B", raw[:6])
    return datetime(year + 2000, month, day, hour, minute, second)


def _plausible(stamp: Optional[datetime]) -> bool:
    return stamp is not None and MIN_YEAR <= stamp.year <= MAX_YEAR


# ---------------------------------------------------------------------------
# User payload parsing
# ---------------------------------------------------------------------------


def parse_users_payload(payload: bytes) -> List[DeviceUser]:
    """Decode a raw CMD_USERTEMP_RRQ payload into terminal users.

    This WL20 firmware uses the extended 72-byte user structure, but 28-byte
    records exist on other firmware. Both divide some payload lengths, so the
    bigger record wins when it fits.
    """
    if len(payload) < 4:
        return []
    total_size = struct.unpack_from("<I", payload)[0]
    body = payload[4:4 + total_size]
    if not body:
        return []

    packet_size = 72 if len(body) % 72 == 0 else 28
    users: List[DeviceUser] = []
    for offset in range(0, len(body) - packet_size + 1, packet_size):
        packet = body[offset:offset + packet_size]
        try:
            if packet_size == 28:
                uid, privilege, password, name, card, group_id, _tz, user_id = struct.unpack(
                    "<HB5s8sIxBhI", packet
                )
                user_id = str(user_id)
                group_id = str(group_id)
            else:
                uid, privilege, password, name, card, group_id, user_id = struct.unpack(
                    "<HB8s24sIx7sx24s", packet
                )
                group_id = _strip(group_id)
                user_id = _strip(user_id)
        except struct.error:
            continue
        name = _strip(name)
        card_text = _strip(card if isinstance(card, bytes) else str(card))
        users.append(DeviceUser(
            uid=uid,
            user_id=user_id or str(uid),
            name=name or f"NN-{user_id or uid}",
            privilege=privilege,
            card=card_text,
            group_id=group_id,
        ))
    return users


def _strip(value) -> str:
    if isinstance(value, bytes):
        return value.split(b"\0", 1)[0].decode("utf-8", errors="ignore").strip()
    return str(value).strip()


def users_by_uid(users: Iterable[DeviceUser]) -> dict:
    return {user.uid: user for user in users}


def user_lookup(users: Iterable[DeviceUser]) -> dict:
    """Index users by both device user id and uid (string forms)."""
    table = {}
    for user in users:
        table[str(user.user_id)] = user
        table[str(user.uid)] = user
    return table


# ---------------------------------------------------------------------------
# Attendance payload parsing
# ---------------------------------------------------------------------------


def parse_attendance_payload(payload: bytes, users: Sequence[DeviceUser],
                             report: Optional[ParseReport] = None) -> List[PunchRecord]:
    """Decode a raw CMD_ATTLOG_RRQ payload into punch records.

    Candidate layouts are tried and the one that yields the most plausible
    records wins; the WL20 compressed scan is the last resort.
    """
    report = report if report is not None else ParseReport()
    if len(payload) < 4:
        report.add_warning("attendance payload too short to contain a size counter")
        return []

    users = list(users or [])
    by_uid = users_by_uid(users)
    valid_uids = set(by_uid)
    no_user_check = not valid_uids

    total_size = struct.unpack_from("<I", payload)[0]
    body = payload[4:4 + total_size]

    report.declared_bytes = total_size
    report.received_bytes = len(body)
    if not body:
        report.add_warning("attendance payload empty after the size counter")
        return []

    # The WL20 announces the full length of its log but sends a single 4096-byte
    # frame and refuses chunk continuation (command 1504), so once the log grows
    # past ~4 KB the newest punches are simply not transferable. Warn instead of
    # exporting a silently incomplete log. (4 bytes of slack: some firmware
    # counts its own size counter in the declared length.)
    shortfall = total_size - len(body)
    if shortfall > 4:
        report.add_warning(
            f"partial log: the terminal declares {total_size} bytes of attendance but "
            f"sent only {len(body)} ({shortfall} bytes missing) — the newest punches are "
            f"cut off by the terminal's transfer limit, not by this app")

    # Some firmware includes the 4-byte size counter in the declared length.
    # Keep both slices as candidates instead of overwriting the payload:
    # trimming 4 bytes off the end breaks the last record of the compressed
    # WL20 layout, whose records are only 17 bytes long.
    variants = [body]
    if len(body) % 8 and len(body) % 16 and len(body) % 40 and total_size >= 4:
        trimmed = payload[4:4 + total_size - 4]
        if trimmed and len(trimmed) != len(body):
            variants.append(trimmed)

    def build(uid: int, user_id: str, raw_stamp: bytes, status: int, punch: int) -> Optional[PunchRecord]:
        try:
            stamp = decode_time(raw_stamp)
        except (ValueError, struct.error, OverflowError):
            return None
        if not _plausible(stamp):
            return None
        user = by_uid.get(uid)
        name = user.name if user else ""
        device_user_id = str(user.user_id) if user else (user_id or str(uid))
        return PunchRecord(user_id=user_id or device_user_id, timestamp=stamp,
                           status=status, punch=punch, uid=uid, name=name,
                           device_user_id=device_user_id)

    def try_layout(payload_body: bytes, packet_size: int, offset: int) -> List[PunchRecord]:
        aligned = payload_body[offset:]
        if not aligned or len(aligned) % packet_size:
            return []
        result: List[PunchRecord] = []
        try:
            for position in range(0, len(aligned), packet_size):
                packet = aligned[position:position + packet_size]
                if packet_size == 8:
                    uid, status, raw_stamp, punch = struct.unpack("<HB4sB", packet)
                    if valid_uids and uid not in valid_uids:
                        return []
                    user = by_uid.get(uid)
                    record = build(uid, user.user_id if user else str(uid),
                                   raw_stamp, status, punch)
                elif packet_size == 16:
                    uid_value, raw_stamp, status, punch, _reserved, _workcode = struct.unpack(
                        "<I4sBB2sI", packet
                    )
                    if valid_uids and uid_value not in valid_uids:
                        return []
                    user = by_uid.get(uid_value)
                    record = build(uid_value, user.user_id if user else str(uid_value),
                                   raw_stamp, status, punch)
                else:
                    uid, raw_user_id, status, raw_stamp, punch, _space = struct.unpack(
                        "<H24sB4sB8s", packet
                    )
                    if valid_uids and uid not in valid_uids:
                        return []
                    record = build(uid, _strip(raw_user_id), raw_stamp, status, punch)
                if record is not None:
                    result.append(record)
        except (ValueError, struct.error, OverflowError):
            return []
        return result

    def try_compressed(payload_body: bytes) -> List[PunchRecord]:
        """WL20 22-byte compressed layout, scanned without alignment assumptions."""
        if not by_uid:
            return []
        result: List[PunchRecord] = []
        for position in range(0, max(0, len(payload_body) - 16)):
            uid = struct.unpack_from("<H", payload_body, position)[0]
            user = by_uid.get(uid)
            if user is None:
                continue
            user_id = str(user.user_id)
            # The printable user id sits right after the uid on this firmware.
            if (not user_id or position + 2 >= len(payload_body)
                    or payload_body[position + 2] != ord(user_id[-1])):
                continue
            stamp = build(uid, user_id, payload_body[position + 13:position + 17],
                          payload_body[position + 3], payload_body[position + 4])
            if stamp is not None:
                result.append(stamp)
        return result

    candidates: List[Tuple[int, int, bytes, List[PunchRecord]]] = []
    for variant in variants:
        for size in (40, 16, 8):
            for offset in range(size):
                candidates.append((size, offset, variant,
                                   try_layout(variant, size, offset)))
    packet_size, offset, winning_body, records = max(
        candidates, key=lambda item: len(item[3]), default=(0, 0, body, [])
    )

    if records:
        report.format_label = (f"{packet_size}-byte records"
                               + ("" if offset == 0 else f" (offset {offset})"))
        report.record_size = packet_size
        report.offset = offset
    else:
        packet_size, offset, winning_body, records = max(
            ((0, 0, variant, try_compressed(variant)) for variant in variants),
            key=lambda item: len(item[3]), default=(0, 0, body, []))
        if records:
            report.format_label = "WL20 22-byte compressed records"
            report.record_size = 22
            report.offset = 0
        else:
            report.format_label = "undecodable"
            report.add_warning("no attendance record layout could be decoded from the payload")

    if records and winning_body != body:
        report.add_note("payload re-aligned: the declared size included the 4-byte counter")

    report.raw_records_read = len(records)
    if no_user_check and records:
        report.add_warning(
            "the terminal reported no user list; records were accepted without "
            "cross-checking them against enrolled users"
        )

    unique: List[PunchRecord] = []
    seen = set()
    for record in records:
        key = (record.uid, record.timestamp)
        if key in seen:
            report.duplicates_dropped += 1
            continue
        seen.add(key)
        unique.append(record)
    unique.sort(key=lambda item: (item.timestamp, item.user_id))
    return unique


# ---------------------------------------------------------------------------
# Network layer
# ---------------------------------------------------------------------------


def _root_cause(exc: BaseException) -> BaseException:
    """Follow pyzk's wrapping chain down to the socket-level error."""
    current = exc
    seen = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        nxt = current.__cause__ or current.__context__
        if nxt is None:
            break
        current = nxt
    return current


def local_address_for(host: str, port: int = 0) -> str:
    """The local IP address this computer would use to reach ``host``.

    The probe uses a UDP socket, which only performs a route lookup: nothing is
    sent and no connection is opened, so it is safe to call while diagnosing.
    """
    if not host:
        return ""
    try:
        info = socket.getaddrinfo(host, port or 9, socket.AF_INET, socket.SOCK_DGRAM)
    except Exception:
        return ""
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    except OSError:  # pragma: no cover - no socket layer available
        return ""
    try:
        probe.connect(info[0][4][:2])
        return str(probe.getsockname()[0])
    except Exception:
        return ""
    finally:
        probe.close()


def network_hint(host: str, local: str) -> str:
    """One plain-language line comparing this computer's network with the device's.

    'Cannot connect' is far more often a network problem (wrong Wi-Fi, guest
    network, firewall) than an app problem, and the two look identical in the
    error text -- so say which one this is.
    """
    if not host or not local:
        return ""
    host_octets = host.split(".")
    local_octets = local.split(".")
    if len(host_octets) != 4 or len(local_octets) != 4:
        return f"This computer would reach {host} from {local}."
    try:
        numbers = [int(part) for part in host_octets + local_octets]
    except ValueError:
        return f"This computer would reach {host} from {local}."
    host_net, local_net = numbers[:4], numbers[4:]
    mine = ".".join(str(part) for part in local_net[:3])
    theirs = ".".join(str(part) for part in host_net[:3])
    if host_net[:3] == local_net[:3]:
        return (f"This computer is on the same network as the terminal "
                f"({mine}.x), so this is not a network mismatch -- the terminal "
                f"may simply be busy. Try again, or restart it from the app.")
    if host_net[:2] == local_net[:2] and abs(host_net[2] - local_net[2]) == 1:
        return (f"This computer ({mine}.x) and the terminal ({theirs}.x) are in "
                f"the same larger range, so the address should work; the terminal "
                f"is probably unreachable for another reason.")
    return (f"This computer is on {mine}.x but the terminal is on {theirs}.x -- "
            f"two different networks (another Wi-Fi/SSID or VLAN). No app setting "
            f"can fix that: this computer has to join the terminal's network.")


def _explain(exc: Exception, host: str = "", port: int = 0) -> str:
    text = f"{type(exc).__name__}: {exc}"
    cause = _root_cause(exc)
    blob = f"{type(cause).__name__} {cause} {exc}".lower()
    lines = [text]
    if isinstance(cause, (socket.timeout, TimeoutError)) or "timed out" in blob:
        lines.append(BUSY_HINT)
    elif (isinstance(cause, OSError) or "refused" in blob or "broken pipe" in blob
            or "unreachable" in blob):
        lines.append(UNREACHABLE_HINT)
    where = network_hint(host, local_address_for(host) if host else "")
    if where:
        lines.append(where)
    return "\n".join(lines)


@contextmanager
def device_session(host: str, port: int = DEFAULT_PORT, password: int = 0,
                   timeout: int = DEFAULT_TIMEOUT):
    """Open one read-only session to the terminal and always close it."""
    try:
        from zk import ZK
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise DeviceError("pyzk is not installed (pip install pyzk)") from exc

    device = ZK(host, port=port, timeout=timeout, password=password, ommit_ping=True)
    connection = None
    try:
        connection = device.connect()
    except Exception as exc:
        raise DeviceError(_explain(exc, host=host, port=port)) from exc
    try:
        yield connection
    finally:
        try:
            connection.disconnect()
        except Exception:
            pass


def _safe_call(connection, name: str, default="") -> str:
    method = getattr(connection, name, None)
    if method is None:
        return default
    try:
        return str(method() or default)
    except Exception:
        return default


def read_device_info(connection, host: str = "", port: int = DEFAULT_PORT) -> DeviceInfo:
    info = DeviceInfo(
        host=host,
        port=port,
        name=_safe_call(connection, "get_device_name"),
        serial=_safe_call(connection, "get_serialnumber"),
        firmware=_safe_call(connection, "get_firmware_version"),
        platform=_safe_call(connection, "get_platform"),
    )
    try:
        connection.read_sizes()
        info.users = int(getattr(connection, "users", 0) or 0)
        info.records = int(getattr(connection, "records", 0) or 0)
        info.users_cap = int(getattr(connection, "users_cap", 0) or 0)
        info.records_cap = int(getattr(connection, "rec_cap", 0) or 0)
    except Exception:
        pass
    return info


def test_connection(host: str, port: int = DEFAULT_PORT, password: int = 0,
                    timeout: int = DEFAULT_TIMEOUT) -> DeviceInfo:
    """Light-weight identity check used by the GUI's Test button."""
    with device_session(host, port=port, password=password, timeout=timeout) as connection:
        return read_device_info(connection, host=host, port=port)


def read_users(connection, report: ParseReport) -> List[DeviceUser]:
    """Enrolled users, falling back to a raw payload read on this firmware."""
    try:
        raw_users = connection.get_users() or []
    except Exception:
        raw_users = []
    users = [_convert_user(item) for item in raw_users]

    if not users:
        report.used_user_fallback = True
        report.add_note("standard user read returned nothing; using the raw payload fallback")
        try:
            from zk import const
            data, _size = connection.read_with_buffer(const.CMD_USERTEMP_RRQ, const.FCT_USER)
            users = parse_users_payload(data)
        except Exception as exc:
            report.add_warning(f"user fallback failed: {type(exc).__name__}: {exc}")
            users = []
    report.users_parsed = len(users)
    return users


def _convert_user(item) -> DeviceUser:
    def get(name, default=""):
        return getattr(item, name, default)

    user_id = str(get("user_id", "") or get("uid", "") or "")
    return DeviceUser(
        uid=int(get("uid", 0) or 0),
        user_id=user_id,
        name=str(get("name", "") or ""),
        privilege=int(get("privilege", 0) or 0),
        card=str(get("card", "") or ""),
        group_id=str(get("group_id", "") or ""),
    )


def read_attendance(connection, users: Sequence[DeviceUser],
                    report: ParseReport) -> List[PunchRecord]:
    """Attendance history, falling back to a raw payload read on this firmware."""
    try:
        raw_records = connection.get_attendance() or []
    except Exception as exc:
        report.add_warning(f"standard attendance read failed: {type(exc).__name__}: {exc}")
        raw_records = []

    if raw_records:
        lookup = user_lookup(users)
        records: List[PunchRecord] = []
        for item in raw_records:
            stamp = getattr(item, "timestamp", None)
            if not _plausible(stamp):
                continue
            user_id = str(getattr(item, "user_id", "") or "")
            uid = int(getattr(item, "uid", 0) or 0)
            user = lookup.get(user_id) or lookup.get(str(uid))
            records.append(PunchRecord(
                user_id=user_id or (user.user_id if user else str(uid)),
                timestamp=stamp,
                status=int(getattr(item, "status", 0) or 0),
                punch=int(getattr(item, "punch", 0) or 0),
                uid=uid,
                name=user.name if user else "",
                device_user_id=user.user_id if user else (user_id or str(uid)),
            ))
        report.format_label = "standard pyzk record layout"
        report.record_size = 0
        report.raw_records_read = len(records)
        unique: List[PunchRecord] = []
        seen = set()
        for record in records:
            key = (record.uid, record.timestamp)
            if key in seen:
                report.duplicates_dropped += 1
                continue
            seen.add(key)
            unique.append(record)
        unique.sort(key=lambda item: (item.timestamp, item.user_id))
        return unique

    report.used_attendance_fallback = True
    report.add_note("standard record read returned nothing; using the raw payload fallback")
    try:
        from zk import const
        data, _size = connection.read_with_buffer(const.CMD_ATTLOG_RRQ)
    except Exception as exc:
        report.add_warning(f"attendance fallback failed: {type(exc).__name__}: {exc}")
        return []
    return parse_attendance_payload(data, users, report)


def read_all(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, password: int = 0,
             timeout: int = DEFAULT_TIMEOUT, progress: ProgressFn = None,
             pause_device: bool = False) -> DeviceRead:
    """Full read: identity, users and every attendance record (read-only)."""
    def log(message: str) -> None:
        if progress:
            progress(message)

    report = ParseReport()
    started = time.monotonic()
    log(f"Connecting to {host}:{port} ...")
    with device_session(host, port=port, password=password, timeout=timeout) as connection:
        info = read_device_info(connection, host=host, port=port)
        log(f"Connected: {info.name or 'unknown device'} serial={info.serial or '?'} "
            f"firmware={info.firmware or '?'}")

        paused = False
        if pause_device:
            try:
                connection.disable_device()
                paused = True
                report.add_note("terminal was briefly disabled during the read (--pause-device)")
            except Exception as exc:
                report.add_warning(f"could not pause the terminal: {type(exc).__name__}: {exc}")
        try:
            log("Reading enrolled users ...")
            users = read_users(connection, report)
            log(f"Users: {len(users)}")
            log("Reading attendance history ...")
            records = read_attendance(connection, users, report)
            log(f"Attendance records: {len(records)}")
        finally:
            if paused:
                try:
                    connection.enable_device()
                except Exception as exc:
                    report.add_warning(f"could not re-enable the terminal: {type(exc).__name__}: {exc}")

    _cross_check(info, users, records, report)
    duration = round(time.monotonic() - started, 2)
    log(f"Read finished in {duration}s")
    return DeviceRead(info=info, users=users, records=records, report=report,
                      duration_seconds=duration)


def _cross_check(info: DeviceInfo, users: Sequence[DeviceUser],
                 records: Sequence[PunchRecord], report: ParseReport) -> None:
    """Flag disagreements between the device counters and what we decoded."""
    if info.records and len(records) != info.records:
        report.add_warning(
            f"the terminal counter reports {info.records} records but {len(records)} "
            f"were decoded — the firmware counter is unreliable on this model; "
            f"compare the date range before trusting truncation"
        )
    if info.users and len(users) != info.users:
        report.add_warning(
            f"the terminal counter reports {info.users} users but {len(users)} were decoded"
        )
    unknown = {record.user_id for record in records if not record.name}
    if unknown:
        report.add_note(
            f"{len(unknown)} device user id(s) have no name on the terminal "
            f"(e.g. {', '.join(sorted(unknown)[:5])})"
        )
    if not records:
        report.add_warning("no attendance records were returned by the terminal")
    if records:
        first = min(record.timestamp for record in records)
        last = max(record.timestamp for record in records)
        report.add_note(f"decoded range: {first:%d-%m-%Y %H:%M:%S} .. {last:%d-%m-%Y %H:%M:%S}")


def wait_until_reachable(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, password: int = 0,
                         timeout: int = DEFAULT_TIMEOUT, wait_seconds: float = RESTART_WAIT,
                         poll: float = 5.0, progress: ProgressFn = None,
                         should_stop=None) -> bool:
    """Poll the terminal until it accepts a ZK session again (after a reboot)."""
    say = progress or (lambda message: None)
    deadline = time.monotonic() + max(0.0, wait_seconds)
    probe = 0
    while True:
        if should_stop is not None and should_stop():
            say("Wait cancelled.")
            return False
        probe += 1
        try:
            with device_session(host, port=port, password=password,
                                timeout=min(timeout, 8)):
                pass
            say(f"Terminal is back online (after {probe} probe(s)).")
            return True
        except DeviceError as exc:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                say(f"Terminal did not come back within {wait_seconds:.0f}s.")
                return False
            say(f"Not back yet: {str(exc).splitlines()[0]} — {remaining:.0f}s left")
            if _interruptible_sleep(min(poll, remaining), should_stop):
                say("Wait cancelled.")
                return False


def restart_device(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, password: int = 0,
                   timeout: int = DEFAULT_TIMEOUT, wait_seconds: float = RESTART_WAIT,
                   poll: float = 5.0, progress: ProgressFn = None,
                   should_stop=None) -> bool:
    """Reboot the terminal over the ZK protocol (CMD_RESTART) and wait for it back.

    Attendance records live in flash, so a reboot never loses them; the terminal
    is offline for roughly 1-2 minutes. Requires the terminal to answer TCP — a
    terminal that is completely unreachable cannot be rebooted remotely, it can
    only be waited for.
    """
    say = progress or (lambda message: None)
    if should_stop is not None and should_stop():
        say("Restart cancelled.")
        return False
    say(f"Sending the reboot command to {host}:{port} ...")
    try:
        with device_session(host, port=port, password=password,
                            timeout=min(timeout, 8)) as connection:
            connection.restart()
    except DeviceError as exc:
        say(f"Could not send the reboot command: {str(exc).splitlines()[0]}")
        return False
    say("Reboot accepted — the terminal is restarting (~1-2 minutes). "
        "Attendance data is stored in flash and is not lost.")
    if wait_seconds <= 0:
        return True
    return wait_until_reachable(host, port=port, password=password, timeout=timeout,
                                wait_seconds=wait_seconds, poll=poll, progress=progress,
                                should_stop=should_stop)


def _interruptible_sleep(seconds: float, should_stop=None) -> bool:
    """Sleep in slices so a Stop request is honoured within a fraction of a second."""
    end = time.monotonic() + max(0.0, seconds)
    while True:
        if should_stop is not None and should_stop():
            return True
        remaining = end - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(0.25, remaining))


def read_with_retry(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, password: int = 0,
                    timeout: int = DEFAULT_TIMEOUT, attempts: int = 1, delay: float = 30.0,
                    wait_seconds: float = 0.0, pause_device: bool = False,
                    progress: ProgressFn = None, log: ProgressFn = None,
                    should_stop=None, restart_if_stuck: bool = False,
                    restart_wait: float = RESTART_WAIT) -> DeviceRead:
    """Read the terminal, retrying while it is busy, offline or rebooting.

    The WL20 refuses new sessions while another client holds its single one and
    is simply unreachable while it reboots, so a scheduled export has to wait it
    out instead of failing:

    - ``wait_seconds > 0`` keeps trying until that much time has passed
      (``attempts`` is then ignored);
    - otherwise at most ``attempts`` tries are made, ``delay`` seconds apart;
    - ``restart_if_stuck`` reboots the terminal (and waits for it to come back)
      once, when the retries are about to be given up;
    - ``should_stop()`` (e.g. the GUI's Stop button) aborts promptly.
    """
    say = log if log is not None else (progress or (lambda message: None))
    deadline = time.monotonic() + wait_seconds if wait_seconds > 0 else None
    attempt = 0
    restarted = False
    while True:
        attempt += 1
        try:
            if attempt > 1:
                say(f"Attempt {attempt} ...")
            return read_all(host, port=port, password=password, timeout=timeout,
                            pause_device=pause_device, progress=progress)
        except DeviceError as exc:
            first_line = str(exc).splitlines()[0]
            expired = deadline is not None and time.monotonic() >= deadline
            exhausted = deadline is None and attempt >= max(1, attempts)
            if expired or exhausted:
                if restart_if_stuck and not restarted:
                    restarted = True
                    say("Reads keep failing — rebooting the terminal and waiting for it ...")
                    if restart_device(host, port=port, password=password, timeout=timeout,
                                      wait_seconds=restart_wait, progress=say,
                                      should_stop=should_stop):
                        say("Terminal is back — one more read attempt.")
                        continue
                    say("The reboot did not bring the terminal back.")
                say(f"Giving up after {attempt} attempt(s): {first_line}")
                raise
            if should_stop is not None and should_stop():
                raise DeviceError(f"cancelled after {attempt} attempt(s)") from exc
            wait = delay if deadline is None else min(delay, max(0.0, deadline - time.monotonic()))
            say(f"Attempt {attempt} failed: {first_line}")
            if wait <= 0:
                raise
            if deadline is not None:
                say(f"Terminal not ready — retrying in {wait:.0f}s "
                    f"(waiting up to {max(0.0, deadline - time.monotonic()):.0f}s more)")
            else:
                say(f"Retrying in {wait:.0f}s ...")
            if _interruptible_sleep(wait, should_stop):
                raise DeviceError(f"cancelled while waiting to retry") from exc
