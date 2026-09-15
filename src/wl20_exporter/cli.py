"""Command line interface: wl20-export."""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

from . import __version__, device, excel
from .summary import build_daily_rows


def parse_day(value: str) -> date:
    text = value.strip()
    for pattern in ("%d-%m-%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(
        f"invalid date {value!r} — use DD-MM-YYYY")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wl20-export",
        description="Read attendance from a ZKTeco WL20 terminal and export it to Excel "
                    "(read-only: nothing is written to the device).",
    )
    parser.add_argument("--host", default=device.DEFAULT_HOST,
                        help=f"terminal IP address (default: {device.DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=device.DEFAULT_PORT,
                        help=f"ZK protocol TCP port (default: {device.DEFAULT_PORT})")
    parser.add_argument("--password", type=int, default=0,
                        help="device communication password (default: 0)")
    parser.add_argument("--timeout", type=int, default=device.DEFAULT_TIMEOUT,
                        help="socket timeout in seconds (default: 10)")
    parser.add_argument("--from", dest="start", type=parse_day, metavar="DD-MM-YYYY",
                        help="keep records on/after this date (DD-MM-YYYY)")
    parser.add_argument("--to", dest="end", type=parse_day, metavar="DD-MM-YYYY",
                        help="keep records on/before this date (DD-MM-YYYY)")
    parser.add_argument("--out", type=Path, metavar="FILE.xlsx",
                        help="Excel output path (default: WL20_Attendance_<range>.xlsx)")
    parser.add_argument("--csv", type=Path, metavar="FILE.csv",
                        help="also write a CSV copy of the raw records")
    parser.add_argument("--punches", action="store_true",
                        help="add a raw punch-list sheet for each day")
    parser.add_argument("--details", action="store_true",
                        help="add the Device Info and Diagnostics sheets (troubleshooting)")
    parser.add_argument("--limit", type=int, default=10,
                        help="how many records to print on the console (default: 10, 0 = all)")
    parser.add_argument("--test", action="store_true",
                        help="only check connectivity and print device details")
    parser.add_argument("--pause-device", action="store_true",
                        help="briefly disable the terminal while reading (only for stubborn firmware)")
    parser.add_argument("--verbose", action="store_true", help="print read progress")
    parser.add_argument("--version", action="version", version=f"wl20-export {__version__}")
    return parser


def _print_read_summary(read) -> None:
    info = read.info
    report = read.report
    print(f"Device:        {info.name or 'unknown'}")
    print(f"Serial:        {info.serial or '?'}")
    print(f"Firmware:      {info.firmware or '?'}")
    print(f"Users:         {len(read.users)}")
    print(f"Records read:  {len(read.records)}")
    print(f"Decoded as:    {report.format_label}")
    if report.duplicates_dropped:
        print(f"Duplicates:    {report.duplicates_dropped} dropped")
    for warning in report.warnings:
        print(f"WARNING:       {warning}")


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    def say(message: str = "") -> None:
        print(message, flush=True)

    say(f"Connecting to {args.host}:{args.port} ...")
    try:
        if args.test:
            info = device.test_connection(args.host, port=args.port, password=args.password,
                                          timeout=args.timeout)
            say("Connection OK")
            say(f"Device:    {info.name or 'unknown'}")
            say(f"Serial:    {info.serial or '?'}")
            say(f"Firmware:  {info.firmware or '?'}")
            say(f"Counters:  users={info.users}/{info.users_cap} "
                f"records={info.records}/{info.records_cap}")
            return 0

        read = device.read_all(args.host, port=args.port, password=args.password,
                               timeout=args.timeout, pause_device=args.pause_device,
                               progress=say if args.verbose else None)
    except device.DeviceError as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 2

    filtered = read.filtered(args.start, args.end)
    _print_read_summary(read)
    if args.start or args.end:
        span = (f"{args.start:%d-%m-%Y}" if args.start else "beginning") + " .. " + \
               (f"{args.end:%d-%m-%Y}" if args.end else "latest")
        print(f"Range filter:  {span} -> {len(filtered.records)} record(s)")

    out = args.out or Path(excel.default_filename(args.start, args.end))
    if args.out is None:
        out = Path.cwd() / out.name
    try:
        written = excel.export_workbook(out, filtered, args.start, args.end,
                                        include_punches=args.punches,
                                        include_details=args.details)
    except OSError as exc:
        print(f"FAILED to write Excel file: {exc}", file=sys.stderr)
        return 3
    print(f"Excel written: {written}")

    rows = build_daily_rows(filtered.records)
    if rows:
        totals = excel.workbook_summary(rows)
        print(f"Sheets:        one per day ({totals['days']} day(s)), newest first"
              + ("  + punch lists" if args.punches else "")
              + ("  + device info/diagnostics" if args.details else ""))
        print(f"Totals:        {totals['people']} staff, "
              f"{sum(row.punches for row in rows)} punch(es), "
              f"{totals['single_punch']} day(s) with a single punch")

    if args.csv:
        csv_path = excel.export_csv(args.csv, filtered.records)
        print(f"CSV written:   {csv_path}")

    if filtered.records:
        records = filtered.records if args.limit == 0 else filtered.records[-args.limit:]
        print("\nLatest records:")
        for record in records:
            print(f"  {record.timestamp:%d-%m-%Y %H:%M:%S}  "
                  f"user_id={record.user_id:<12} {record.punch_text:<12} "
                  f"{record.name}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
