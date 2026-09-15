"""Excel (.xlsx) and CSV export.

Layout matches the palette of the office's existing attendance reports
(Arial, white-on-#366092 headers) and carries bilingual Khmer + English
column headers because HR reads the Khmer first.
"""

from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import __version__
from .models import DailyRow, DeviceRead, PunchRecord
from .summary import build_daily_rows, summary_totals

HEADER_FILL = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
HEADER_FONT = Font(name="Arial", size=12, bold=True, color="FFFFFF")
TITLE_FONT = Font(name="Arial", size=12, bold=True, color="366092")
DATA_FONT = Font(name="Arial", size=10)
BOLD_FONT = Font(name="Arial", size=10, bold=True)
TOTAL_FILL = PatternFill(start_color="D9E2F3", end_color="D9E2F3", fill_type="solid")
WARN_FILL = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

DATE_FMT = "yyyy-mm-dd"
TIME_FMT = "hh:mm:ss"
DATETIME_FMT = "yyyy-mm-dd hh:mm:ss"

CENTER = Alignment(horizontal="center", vertical="center")
LEFT = Alignment(horizontal="left", vertical="center")

# Bilingual column labels: English (Khmer).
L = {
    "index": "No.",
    "date": "Date (កាលបរិច្ឆេទ)",
    "time": "Time (ម៉ោង)",
    "staff_id": "Staff ID (លេខកូដបុគ្គលិក)",
    "name": "Name (ឈ្មោះ)",
    "device_user": "Device User ID (លេខអ្នកប្រើលើម៉ាស៊ីន)",
    "punch": "Punch (ចលនា)",
    "verify": "Verified By (វិធីផ្ទៀងផ្ទាត់)",
    "uid": "UID",
    "first_in": "First Check-In (ចូលដំបូង)",
    "last_out": "Last Check-Out (ចេញចុងក្រោយ)",
    "hours": "Hours (ម៉ោងសរុប)",
    "punches": "Punches (ចំនួនស្កេន)",
    "note": "Note (កំណត់សម្គាល់)",
    "device": "Device (ឧបករណ៍)",
}

DEFAULT_SHEET = "Attendance"


def _style_header(sheet, row: int, headers: Sequence[str]) -> None:
    for column, label in enumerate(headers, start=1):
        cell = sheet.cell(row=row, column=column, value=label)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER
    sheet.row_dimensions[row].height = 30


def _autosize(sheet, widths: Sequence[int]) -> None:
    for column, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(column)].width = width


def _setup_print(sheet, landscape: bool = True, repeat_header: bool = False) -> None:
    """Make the sheet print/export as one page wide instead of column fragments."""
    sheet.page_setup.orientation = "landscape" if landscape else "portrait"
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.print_options.horizontalCentered = True
    if repeat_header:
        sheet.print_title_rows = "1:1"


def _write_records_sheet(sheet, records: Sequence[PunchRecord], device_label: str) -> None:
    headers = [L["index"], L["date"], L["time"], L["staff_id"], L["name"],
               L["device_user"], L["punch"], L["verify"], L["uid"], L["device"]]
    _style_header(sheet, 1, headers)
    for position, record in enumerate(records, start=1):
        row = position + 1
        sheet.cell(row=row, column=1, value=position).font = DATA_FONT
        date_cell = sheet.cell(row=row, column=2, value=record.timestamp.date())
        date_cell.number_format = DATE_FMT
        time_cell = sheet.cell(row=row, column=3, value=record.timestamp.time())
        time_cell.number_format = TIME_FMT
        sheet.cell(row=row, column=4, value=record.user_id).font = DATA_FONT
        sheet.cell(row=row, column=5, value=record.name or "").font = DATA_FONT
        sheet.cell(row=row, column=6, value=record.device_user_id).font = DATA_FONT
        sheet.cell(row=row, column=7, value=record.punch_text).font = DATA_FONT
        sheet.cell(row=row, column=8, value=record.verify_text).font = DATA_FONT
        sheet.cell(row=row, column=9, value=record.uid).font = DATA_FONT
        sheet.cell(row=row, column=10, value=device_label).font = DATA_FONT
        for column in range(1, len(headers) + 1):
            cell = sheet.cell(row=row, column=column)
            cell.border = BORDER
            cell.alignment = CENTER if column in (1, 2, 3, 7, 8, 9) else LEFT
    _autosize(sheet, [6, 13, 11, 18, 30, 24, 14, 16, 8, 26])
    sheet.freeze_panes = "A2"
    _setup_print(sheet, landscape=True, repeat_header=True)
    if records:
        sheet.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(records) + 1}"


def _write_summary_sheet(sheet, rows: Sequence[DailyRow]) -> None:
    headers = [L["index"], L["date"], L["staff_id"], L["name"], L["first_in"],
               L["last_out"], L["hours"], L["punches"], L["note"]]
    _style_header(sheet, 1, headers)
    for position, row_data in enumerate(rows, start=1):
        row = position + 1
        sheet.cell(row=row, column=1, value=position).font = DATA_FONT
        date_cell = sheet.cell(row=row, column=2, value=row_data.day)
        date_cell.number_format = DATE_FMT
        sheet.cell(row=row, column=3, value=row_data.user_id).font = DATA_FONT
        sheet.cell(row=row, column=4, value=row_data.name or "").font = DATA_FONT
        if row_data.first_in:
            first_cell = sheet.cell(row=row, column=5, value=row_data.first_in)
            first_cell.number_format = TIME_FMT
        if row_data.last_out:
            last_cell = sheet.cell(row=row, column=6, value=row_data.last_out)
            last_cell.number_format = TIME_FMT
        hours_cell = sheet.cell(row=row, column=7, value=row_data.hours)
        hours_cell.number_format = "0.00"
        sheet.cell(row=row, column=8, value=row_data.punches).font = DATA_FONT
        note_cell = sheet.cell(row=row, column=9,
                               value="single punch only" if row_data.single_punch else "")
        note_cell.font = DATA_FONT
        if row_data.single_punch:
            note_cell.fill = WARN_FILL
        for column in range(1, len(headers) + 1):
            cell = sheet.cell(row=row, column=column)
            cell.border = BORDER
            cell.alignment = CENTER if column in (1, 2, 5, 6, 7, 8) else LEFT

    totals = summary_totals(rows)
    total_row = len(rows) + 2
    sheet.cell(row=total_row, column=1, value="TOTAL").font = BOLD_FONT
    sheet.cell(row=total_row, column=4,
               value=f"{totals['people']} staff / {totals['days']} day(s)").font = BOLD_FONT
    hours_cell = sheet.cell(row=total_row, column=7, value=totals["hours"])
    hours_cell.font = BOLD_FONT
    hours_cell.number_format = "0.00"
    sheet.cell(row=total_row, column=8, value=sum(row.punches for row in rows)).font = BOLD_FONT
    if totals["single_punch"]:
        sheet.cell(row=total_row, column=9,
                   value=f"{totals['single_punch']} day(s) with a single punch").font = BOLD_FONT
    for column in range(1, len(headers) + 1):
        sheet.cell(row=total_row, column=column).fill = TOTAL_FILL
        sheet.cell(row=total_row, column=column).border = BORDER

    _autosize(sheet, [6, 13, 18, 30, 20, 20, 12, 14, 26])
    sheet.freeze_panes = "A2"
    _setup_print(sheet, landscape=True, repeat_header=True)
    if rows:
        sheet.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(rows) + 1}"


def _write_info_sheet(sheet, read: DeviceRead, start: Optional[date], end: Optional[date],
                      record_count: int) -> None:
    info = read.info
    pairs = [
        ("Report (របាយការណ៍)", "WL20 Attendance Exporter"),
        ("Exported at (នាំចេញនៅ)", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ("App version", __version__),
        ("Device name (ឈ្មោះឧបករណ៍)", info.name or "-"),
        ("Serial number (លេខសៀរៀល)", info.serial or "-"),
        ("Firmware (កម្មវិធីបង្កប់)", info.firmware or "-"),
        ("Address (អាសយដ្ឋាន)", f"{info.host}:{info.port}"),
        ("Users on terminal (អ្នកប្រើលើម៉ាស៊ីន)", len(read.users)),
        ("Records decoded (កំណត់ត្រាដែលអានបាន)", len(read.records)),
        ("Records exported (កំណត់ត្រាបាននាំចេញ)", record_count),
        ("Read duration (s)", read.duration_seconds),
        ("Date range (ចន្លោះកាលបរិច្ឆេទ)",
         f"{start or 'beginning'} .. {end or 'latest'}"),
        ("Decoded format", read.report.format_label),
    ]
    for position, (key, value) in enumerate(pairs, start=1):
        key_cell = sheet.cell(row=position, column=1, value=key)
        key_cell.font = BOLD_FONT
        sheet.cell(row=position, column=2, value=value).font = DATA_FONT
    _autosize(sheet, [42, 46])
    _setup_print(sheet, landscape=False)


def _write_diagnostics_sheet(sheet, read: DeviceRead) -> None:
    report = read.report
    lines: List[tuple] = [
        ("Decoded format", report.format_label),
        ("Record size (bytes)", report.record_size),
        ("Payload offset", report.offset),
        ("Declared payload bytes", report.declared_bytes),
        ("Received payload bytes", report.received_bytes),
        ("Records before de-duplication", report.raw_records_read),
        ("Duplicate records dropped", report.duplicates_dropped),
        ("Users decoded", report.users_parsed),
        ("Used user fallback parser", "yes" if report.used_user_fallback else "no"),
        ("Used attendance fallback parser", "yes" if report.used_attendance_fallback else "no"),
        ("Device counter: users", read.info.users),
        ("Device counter: records", read.info.records),
        ("Device capacity: users", read.info.users_cap),
        ("Device capacity: records", read.info.records_cap),
        ("Read duration (s)", read.duration_seconds),
    ]
    for position, (key, value) in enumerate(lines, start=1):
        sheet.cell(row=position, column=1, value=key).font = BOLD_FONT
        sheet.cell(row=position, column=2, value=value).font = DATA_FONT

    row = len(lines) + 2
    sheet.cell(row=row, column=1, value="NOTES").font = TITLE_FONT
    for note in report.notes:
        row += 1
        sheet.cell(row=row, column=1, value=note).font = DATA_FONT
    row += 1
    sheet.cell(row=row, column=1, value="WARNINGS").font = TITLE_FONT
    if report.warnings:
        for warning in report.warnings:
            row += 1
            cell = sheet.cell(row=row, column=1, value=warning)
            cell.font = DATA_FONT
            cell.fill = WARN_FILL
    else:
        row += 1
        sheet.cell(row=row, column=1, value="none").font = DATA_FONT
    _autosize(sheet, [40, 70])
    _setup_print(sheet, landscape=False)


def export_workbook(path, read: DeviceRead, start: Optional[date] = None,
                    end: Optional[date] = None) -> Path:
    """Write the four-sheet attendance workbook and return its path."""
    path = Path(path)
    records = list(read.records)
    rows = build_daily_rows(records)

    workbook = Workbook()
    device_label = read.info.name or read.info.serial or read.info.host or "WL20"

    sheet = workbook.active
    sheet.title = DEFAULT_SHEET
    _write_records_sheet(sheet, records, device_label)

    _write_summary_sheet(workbook.create_sheet("Daily Summary"), rows)
    _write_info_sheet(workbook.create_sheet("Device Info"), read, start, end, len(records))
    _write_diagnostics_sheet(workbook.create_sheet("Diagnostics"), read)

    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)
    return path


def export_csv(path, records: Iterable[PunchRecord]) -> Path:
    """Plain CSV copy of the raw records (UTF-8 with BOM so Excel opens it right)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "time", "user_id", "name", "device_user_id",
                         "punch", "status", "uid", "timestamp"])
        for record in records:
            writer.writerow([
                record.timestamp.strftime("%Y-%m-%d"),
                record.timestamp.strftime("%H:%M:%S"),
                record.user_id,
                record.name,
                record.device_user_id,
                record.punch,
                record.status,
                record.uid,
                record.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            ])
    return path


def default_filename(start: Optional[date], end: Optional[date]) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    if start and end:
        span = f"{start:%Y%m%d}-{end:%Y%m%d}"
    elif start:
        span = f"from_{start:%Y%m%d}"
    elif end:
        span = f"until_{end:%Y%m%d}"
    else:
        span = "all"
    return f"WL20_Attendance_{span}_{stamp}.xlsx"
