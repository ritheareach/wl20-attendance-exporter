"""Render the GUI offscreen with sample data (README screenshots + smoke proof)."""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

ROOT = Path(__file__).resolve().parents[1] if "__file__" in globals() else Path.cwd()
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from wl20_exporter import config, gui, theme  # noqa: E402
from wl20_exporter.models import (  # noqa: E402
    DeviceInfo,
    DeviceRead,
    DeviceUser,
    ParseReport,
    PunchRecord,
)

STAFF = [
    ("STF-0001", "SOK Dara", 1),
    ("STF-0002", "CHHIM Sokha", 2),
    ("STF-0003", "LY Panha", 3),
    ("STF-0004", "MEAS Vannak", 4),
    ("STF-0005", "PRAK Sreyleak", 5),
]

TEMPLATE = [(8, 1), (12, 3), (13, 5), (17, 32), (17, 30), (8, 15)]


def sample_read() -> DeviceRead:
    records = []
    today = date.today()
    for offset in range(5, -1, -1):
        day = today - timedelta(days=offset)
        if day.weekday() == 6:
            continue
        for position, (user_id, name, uid) in enumerate(STAFF):
            if offset == 0 and position > 2:
                continue
            for step, (hour, minute) in enumerate(TEMPLATE[:4]):
                if offset == 0 and position == 0 and step == 3:
                    continue  # leave one single-punch day so the Note flag shows
                if step == 0 or step in (3,):
                    stamp = datetime(day.year, day.month, day.day, hour,
                                     minute + position * 3, (position * 7) % 60)
                    records.append(PunchRecord(user_id=user_id, name=name, uid=uid,
                                               timestamp=stamp, punch=1 if hour > 16 else 0,
                                               status=1))
    records.sort(key=lambda item: item.timestamp)
    report = ParseReport(format_label="40-byte records", record_size=40,
                         declared_bytes=len(records) * 40,
                         received_bytes=len(records) * 40, raw_records_read=len(records),
                         users_parsed=len(STAFF),
                         notes=[f"decoded range: {records[0].timestamp:%Y-%m-%d %H:%M:%S} .. "
                                f"{records[-1].timestamp:%Y-%m-%d %H:%M:%S}"])
    return DeviceRead(
        info=DeviceInfo(host="192.168.88.245", port=4370, name="WL20",
                        serial="A5KN203360148", firmware="Ver 6.60", users=len(STAFF),
                        records=len(records), users_cap=3000, records_cap=100000),
        users=[DeviceUser(uid=uid, user_id=user_id, name=name) for user_id, name, uid in STAFF],
        records=records,
        report=report,
        duration_seconds=6.4,
    )


def main() -> int:
    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp")
    work_dir = out_dir / "wl20-preview"
    work_dir.mkdir(parents=True, exist_ok=True)
    config.app_data_dir = lambda: work_dir

    app = QApplication([])
    app.setStyleSheet(theme.STYLESHEET)
    window = gui.MainWindow()
    window.resize(1280, 780)  # same default as the app itself
    window.preset_combo.setCurrentText("All records")
    window.show()
    app.processEvents()

    read = sample_read()
    window.on_fetched(read)
    app.processEvents()
    app.processEvents()

    records_png = out_dir / "wl20-gui-records.png"
    window.grab().save(str(records_png))

    window.tabs.setCurrentIndex(1)
    app.processEvents()
    summary_png = out_dir / "wl20-gui-summary.png"
    window.grab().save(str(summary_png))

    window.tabs.setCurrentIndex(3)
    app.processEvents()
    log_png = out_dir / "wl20-gui-log.png"
    window.grab().save(str(log_png))

    print(f"records={len(read.records)} "
          f"records_rows={window.records_model.rowCount()} "
          f"summary_rows={window.summary_model.rowCount()} "
          f"totals='{window.summary_totals_label.text()}'")
    for path in (records_png, summary_png, log_png):
        print(f"saved {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
