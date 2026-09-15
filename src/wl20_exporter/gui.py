"""PySide6 desktop UI for the WL20 Attendance Exporter."""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import (
    QAbstractTableModel,
    QDate,
    QModelIndex,
    QObject,
    QSortFilterProxyModel,
    Qt,
    QThread,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIcon, QKeySequence, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QStatusBar,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import __version__, config, device, excel
from .models import DailyRow, DeviceRead, PunchRecord
from .summary import build_daily_rows, summary_totals
from .theme import ACCENT, STYLESHEET

APP_TITLE = "WL20 Attendance Exporter"
PRESETS = ["All records", "Today", "Last 7 days", "Last 30 days", "This month", "Custom"]

BUSY_NOTE = ("The terminal serves one connection at a time. While this app reads, the "
             "FaceGO live listener on the office server is pushed off its socket — run "
             "exports outside peak hours.")

# Sorting must not use the displayed text: "01-10-2026" would sort before
# "02-09-2026" in DD-MM-YYYY, and "10.00" before "9.52". This role carries a
# numeric/chronological key per cell and every proxy sorts on it.
SORT_ROLE = int(Qt.UserRole) + 1


def _seconds_of_day(stamp: datetime) -> int:
    return stamp.hour * 3600 + stamp.minute * 60 + stamp.second


def asset_path(name: str) -> Path:
    """Locate a bundled asset in a source checkout or inside a frozen build."""
    roots = []
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        roots += [Path(frozen_root) / "wl20_exporter" / "assets",
                  Path(frozen_root) / "assets"]
    roots.append(Path(__file__).resolve().parent / "assets")
    for root in roots:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return roots[-1] / name


def app_icon() -> QIcon:
    """AIFarm icon; empty only if the asset was somehow not shipped."""
    path = asset_path("icon.png")
    return QIcon(str(path)) if path.is_file() else QIcon()


def light_palette() -> QPalette:
    """Pin a light palette so a dark OS theme cannot bleed into the widgets.

    The stylesheet paints white input backgrounds; without this the inherited
    dark-theme text colour is white too and every field renders blank.
    """
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#f4f6f9"))
    palette.setColor(QPalette.WindowText, QColor("#1f2430"))
    palette.setColor(QPalette.Base, QColor("#ffffff"))
    palette.setColor(QPalette.AlternateBase, QColor("#fafbfd"))
    palette.setColor(QPalette.Text, QColor("#1f2430"))
    palette.setColor(QPalette.Button, QColor("#ffffff"))
    palette.setColor(QPalette.ButtonText, QColor("#1f2430"))
    palette.setColor(QPalette.Highlight, QColor(ACCENT))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ToolTipBase, QColor("#1f2430"))
    palette.setColor(QPalette.ToolTipText, QColor("#ffffff"))
    palette.setColor(QPalette.PlaceholderText, QColor("#8b93a1"))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor("#8b93a1"))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#a3aab6"))
    return palette


def configure_app(app: QApplication) -> None:
    """One place that sets style, palette, icon and stylesheet for every entry point."""
    app.setApplicationName(APP_TITLE)
    app.setApplicationVersion(__version__)
    # Fusion keeps widget metrics identical on Windows, macOS and Linux; the
    # native Aqua style ignores parts of the stylesheet and squeezed the fields.
    app.setStyle("Fusion")
    app.setPalette(light_palette())
    app.setWindowIcon(app_icon())
    app.setStyleSheet(STYLESHEET)


# ---------------------------------------------------------------------------
# Table models
# ---------------------------------------------------------------------------


class RecordsModel(QAbstractTableModel):
    HEADERS = ["Date", "Time", "Staff ID", "Name", "Punch", "Verified by",
               "UID", "Device user"]
    KEYS = ["date", "time", "user_id", "name", "punch", "verify", "uid", "device_user"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[PunchRecord] = []

    def set_records(self, records) -> None:
        self.beginResetModel()
        self._rows = list(records)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return self.HEADERS[section]
        return section + 1

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        record = self._rows[index.row()]
        column = index.column()
        if role == SORT_ROLE:
            # Chronological/numeric keys: real instants for date and time,
            # lower-cased text for names so sorting matches what is displayed.
            if column == 0:
                return record.timestamp.toordinal() * 86400 + _seconds_of_day(record.timestamp)
            if column == 1:
                return _seconds_of_day(record.timestamp)
            if column == 2:
                return record.user_id.lower()
            if column == 3:
                return (record.name or "").lower()
            if column == 4:
                return record.punch
            if column == 5:
                return record.verify_text.lower()
            if column == 6:
                return record.uid
            return (record.device_user_id or "").lower()
        if role == Qt.DisplayRole:
            if column == 0:
                return record.timestamp.strftime("%d-%m-%Y")
            if column == 1:
                return record.timestamp.strftime("%H:%M:%S")
            if column == 2:
                return record.user_id
            if column == 3:
                return record.name
            if column == 4:
                return record.punch_text
            if column == 5:
                return record.verify_text
            if column == 6:
                return record.uid
            if column == 7:
                return record.device_user_id
        if role == Qt.TextAlignmentRole and column in (0, 1, 6):
            return int(Qt.AlignCenter)
        if role == Qt.ToolTipRole:
            return (f"{record.timestamp:%d-%m-%Y %H:%M:%S}\n"
                    f"user_id={record.user_id} uid={record.uid}\n"
                    f"{record.punch_text} / {record.verify_text}")
        return None

    def record_at(self, row: int) -> PunchRecord | None:
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None


class SummaryModel(QAbstractTableModel):
    HEADERS = ["Date", "Staff ID", "Name", "First in", "Last out", "Hours",
               "Punches", "Note"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[DailyRow] = []

    def set_rows(self, rows) -> None:
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return self.HEADERS[section]
        return section + 1

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        column = index.column()
        if role == SORT_ROLE:
            if column == 0:
                return row.day.toordinal()
            if column == 1:
                return row.user_id.lower()
            if column == 2:
                return (row.name or "").lower()
            if column == 3:
                return _seconds_of_day(row.first_in) if row.first_in else -1
            if column == 4:
                return _seconds_of_day(row.last_out) if row.last_out else -1
            if column == 5:
                return row.hours
            if column == 6:
                return row.punches
            return 1 if row.single_punch else 0
        if role == Qt.DisplayRole:
            if column == 0:
                return row.day.strftime("%d-%m-%Y")
            if column == 1:
                return row.user_id
            if column == 2:
                return row.name
            if column == 3:
                return row.first_in.strftime("%H:%M:%S") if row.first_in else ""
            if column == 4:
                return row.last_out.strftime("%H:%M:%S") if row.last_out else ""
            if column == 5:
                return f"{row.hours:.2f}"
            if column == 6:
                return row.punches
            if column == 7:
                return "single punch only" if row.single_punch else ""
        if role == Qt.TextAlignmentRole and column in (0, 3, 4, 5, 6):
            return int(Qt.AlignCenter)
        return None


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------


class DeviceWorker(QObject):
    log = Signal(str)
    tested = Signal(object)
    fetched = Signal(object)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self._job = ""
        self._kwargs: dict = {}

    def configure(self, job: str, **kwargs) -> None:
        self._job = job
        self._kwargs = kwargs

    @Slot()
    def run(self) -> None:
        try:
            if self._job == "test":
                self.tested.emit(device.test_connection(**self._kwargs))
            else:
                read = device.read_all(progress=self.log.emit, **self._kwargs)
                self.fetched.emit(read)
        except device.DeviceError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # pragma: no cover - defensive
            self.failed.emit(f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = config.load()
        self.read_result: DeviceRead | None = None
        self.last_range: tuple = (None, None)
        self.thread: QThread | None = None
        self.worker: DeviceWorker | None = None

        self.setWindowTitle(f"{APP_TITLE} {__version__}")
        self.setWindowIcon(app_icon())
        self.resize(1180, 760)
        self.setMinimumSize(980, 620)

        self._build_ui()
        self._build_shortcuts()
        self._restore_settings()
        self.log_line(f"Ready. Terminal default {self.settings['host']}:{self.settings['port']}.")

    # -- UI construction ---------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(16, 14, 16, 10)
        outer.setSpacing(12)

        outer.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setSpacing(12)
        body.addWidget(self._build_side_panel(), 0)
        body.addWidget(self._build_tabs(), 1)
        outer.addLayout(body, 1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        self.progress.setFixedHeight(6)

        status = QStatusBar()
        status.addWidget(self.status_label(), 1)
        status.addPermanentWidget(self.progress, 0)
        self.setStatusBar(status)

    def _build_header(self) -> QWidget:
        card = QFrame()
        card.setObjectName("Card")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)

        titles = QVBoxLayout()
        title = QLabel(APP_TITLE)
        title.setObjectName("Title")
        subtitle = QLabel("ZKTeco WL20 fingerprint terminal → Excel report  ·  "
                          "read-only, no server required")
        subtitle.setObjectName("Subtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        layout.addLayout(titles, 1)

        self.device_pill = QLabel("Not connected")
        self.device_pill.setObjectName("Pill")
        layout.addWidget(self.device_pill, 0, Qt.AlignVCenter)
        return card

    def _build_side_panel(self) -> QWidget:
        panel = QWidget()
        # A hard 330px pin squeezed the spin boxes on macOS (Aqua padding plus
        # the stylesheet's own padding left room for barely one digit).
        panel.setMinimumWidth(360)
        panel.setMaximumWidth(430)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # Terminal group
        terminal = QGroupBox("Terminal")
        form = QFormLayout(terminal)
        form.setLabelAlignment(Qt.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.DontWrapRows)
        form.setHorizontalSpacing(10)
        self.host_edit = QLineEdit(self.settings["host"])
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(int(self.settings["port"]))
        self.password_spin = QSpinBox()
        self.password_spin.setRange(0, 999999)
        self.password_spin.setValue(int(self.settings["password"]))
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(3, 120)
        self.timeout_spin.setSuffix(" s")
        self.timeout_spin.setValue(int(self.settings["timeout"]))
        self.pause_check = QCheckBox("Pause terminal while reading")
        self.pause_check.setChecked(bool(self.settings["pause_device"]))
        self.pause_check.setToolTip("Only needed if reads fail on this firmware. "
                                   "The terminal is re-enabled automatically.")
        self.test_button = QPushButton("Test connection")
        self.test_button.clicked.connect(self.on_test)
        # Minimum widths that fit the longest real value on every platform:
        # full IP, 4-digit port, 6-digit password, "120 s" timeout.
        self.host_edit.setMinimumWidth(150)
        for spin in (self.port_spin, self.password_spin, self.timeout_spin):
            spin.setMinimumWidth(92)
            spin.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.addRow("Address", self.host_edit)
        form.addRow("Port", self.port_spin)
        form.addRow("Password", self.password_spin)
        form.addRow("Timeout", self.timeout_spin)
        form.addRow("", self.pause_check)
        form.addRow("", self.test_button)
        layout.addWidget(terminal)

        # Range group
        rng = QGroupBox("Date range")
        range_layout = QVBoxLayout(rng)
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(PRESETS)
        self.from_edit = QDateEdit()
        self.from_edit.setCalendarPopup(True)
        self.from_edit.setDisplayFormat("dd-MM-yyyy")
        self.to_edit = QDateEdit()
        self.to_edit.setCalendarPopup(True)
        self.to_edit.setDisplayFormat("dd-MM-yyyy")
        today = QDate.currentDate()
        self.from_edit.setDate(today.addDays(-30))
        self.to_edit.setDate(today)
        self.preset_combo.currentTextChanged.connect(self.on_preset_changed)
        self.from_edit.dateChanged.connect(self._mark_custom)
        self.to_edit.dateChanged.connect(self._mark_custom)
        self.preset_combo.setMinimumWidth(160)
        self.from_edit.setMinimumWidth(130)
        self.to_edit.setMinimumWidth(130)
        range_layout.addWidget(self.preset_combo)
        range_layout.addWidget(QLabel("From"))
        range_layout.addWidget(self.from_edit)
        range_layout.addWidget(QLabel("To"))
        range_layout.addWidget(self.to_edit)
        layout.addWidget(rng)

        # Actions
        actions = QGroupBox("Actions")
        actions_layout = QVBoxLayout(actions)
        self.fetch_button = QPushButton("Fetch attendance  (F5)")
        self.fetch_button.setObjectName("Primary")
        self.fetch_button.clicked.connect(self.on_fetch)
        self.export_button = QPushButton("Export to Excel…  (Ctrl+E)")
        self.export_button.setObjectName("Accent")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.on_export)
        self.csv_button = QPushButton("Export CSV copy…")
        self.csv_button.setEnabled(False)
        self.csv_button.clicked.connect(self.on_export_csv)
        actions_layout.addWidget(self.fetch_button)
        actions_layout.addWidget(self.export_button)
        actions_layout.addWidget(self.csv_button)
        layout.addWidget(actions)

        note = QLabel(BUSY_NOTE)
        note.setObjectName("Hint")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        return panel

    def _build_tabs(self) -> QWidget:
        self.tabs = QTabWidget()

        # Records tab
        records_tab = QWidget()
        records_layout = QVBoxLayout(records_tab)
        records_layout.setContentsMargins(0, 0, 0, 0)
        records_layout.setSpacing(8)

        filter_row = QHBoxLayout()
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Search name or ID…")
        self.filter_edit.setClearButtonEnabled(True)
        self.records_count = QLabel("No data yet")
        self.records_count.setObjectName("SectionLabel")
        filter_row.addWidget(self.filter_edit, 1)
        filter_row.addWidget(self.records_count, 0)
        records_layout.addLayout(filter_row)

        self.records_model = RecordsModel(self)
        self.records_proxy = QSortFilterProxyModel(self)
        self.records_proxy.setSourceModel(self.records_model)
        self.records_proxy.setSortRole(SORT_ROLE)
        self.records_proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.records_proxy.setFilterKeyColumn(-1)
        self.filter_edit.textChanged.connect(self.records_proxy.setFilterFixedString)

        self.records_view = self._make_table(self.records_proxy, stretch_column=3)
        records_layout.addWidget(self.records_view, 1)
        self.tabs.addTab(records_tab, "Attendance")

        # Summary tab
        summary_tab = QWidget()
        summary_layout = QVBoxLayout(summary_tab)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(8)
        self.summary_totals_label = QLabel("No data yet")
        self.summary_totals_label.setObjectName("SectionLabel")
        summary_layout.addWidget(self.summary_totals_label)
        self.summary_model = SummaryModel(self)
        self.summary_proxy = QSortFilterProxyModel(self)
        self.summary_proxy.setSourceModel(self.summary_model)
        self.summary_proxy.setSortRole(SORT_ROLE)
        self.summary_view = self._make_table(self.summary_proxy, stretch_column=2)
        summary_layout.addWidget(self.summary_view, 1)
        self.tabs.addTab(summary_tab, "Daily Summary")

        # Device tab
        device_tab = QWidget()
        device_layout = QVBoxLayout(device_tab)
        device_layout.setContentsMargins(0, 0, 0, 0)
        self.device_grid = QGridLayout()
        self.device_grid.setHorizontalSpacing(18)
        self.device_grid.setVerticalSpacing(8)
        device_holder = QWidget()
        device_holder.setLayout(self.device_grid)
        device_layout.addWidget(device_holder)
        device_layout.addStretch(1)
        self.tabs.addTab(device_tab, "Device Info")

        # Log tab
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.tabs.addTab(self.log_view, "Log & Diagnostics")
        return self.tabs

    def _make_table(self, model, stretch_column: int | None = None) -> QTableView:
        view = QTableView()
        view.setModel(model)
        view.setSortingEnabled(True)
        view.setAlternatingRowColors(True)
        view.setSelectionBehavior(QTableView.SelectRows)
        view.setSelectionMode(QTableView.ExtendedSelection)
        view.setEditTriggers(QTableView.NoEditTriggers)
        view.verticalHeader().setVisible(False)
        header = view.horizontalHeader()
        # Size to the widest of (header text, cell content) so no header is ever
        # clipped, and let the name column absorb the leftover width.
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        if stretch_column is not None:
            header.setSectionResizeMode(stretch_column, QHeaderView.Stretch)
            header.setStretchLastSection(False)
        else:
            header.setStretchLastSection(True)
        view.setWordWrap(False)
        return view

    def _build_shortcuts(self) -> None:
        for key, slot in (("F5", self.on_fetch), ("Ctrl+T", self.on_test),
                          ("Ctrl+E", self.on_export), ("Ctrl+Q", self.close)):
            action = QAction(self)
            action.setShortcut(QKeySequence(key))
            action.triggered.connect(slot)
            self.addAction(action)

    def status_label(self) -> QLabel:
        label = QLabel("Idle")
        return label

    # -- settings ----------------------------------------------------------

    def _restore_settings(self) -> None:
        preset = self.settings.get("range_preset", PRESETS[3])
        index = self.preset_combo.findText(preset)
        self.preset_combo.setCurrentIndex(index if index >= 0 else PRESETS.index("Last 30 days"))
        self.on_preset_changed(self.preset_combo.currentText())

    def _persist_settings(self) -> None:
        self.settings.update({
            "host": self.host_edit.text().strip(),
            "port": int(self.port_spin.value()),
            "password": int(self.password_spin.value()),
            "timeout": int(self.timeout_spin.value()),
            "pause_device": bool(self.pause_check.isChecked()),
            "range_preset": self.preset_combo.currentText(),
        })
        try:
            config.save(self.settings)
        except OSError:
            pass

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self._persist_settings()
        super().closeEvent(event)

    # -- helpers -----------------------------------------------------------

    def log_line(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"[{stamp}] {message}")
        self.statusBar().findChild(QLabel).setText(message)

    def log_block(self, title: str, lines) -> None:
        self.log_line(f"— {title} —")
        for line in lines:
            self.log_view.appendPlainText(f"    {line}")

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self.progress.setVisible(busy)
        for widget in (self.fetch_button, self.test_button, self.host_edit,
                       self.port_spin,
                       self.password_spin, self.timeout_spin, self.pause_check):
            widget.setEnabled(not busy)
        has_data = self.read_result is not None
        self.export_button.setEnabled(not busy and has_data)
        self.csv_button.setEnabled(not busy and has_data)
        if message:
            self.log_line(message)

    def _selected_dates(self):
        preset = self.preset_combo.currentText()
        if preset == "All records":
            return None, None
        today = date.today()
        qd_from = self.from_edit.date()
        qd_to = self.to_edit.date()
        start = date(qd_from.year(), qd_from.month(), qd_from.day())
        end = date(qd_to.year(), qd_to.month(), qd_to.day())
        if preset == "Today":
            start = end = today
        elif preset == "Last 7 days":
            start, end = today - timedelta(days=6), today
        elif preset == "Last 30 days":
            start, end = today - timedelta(days=29), today
        elif preset == "This month":
            start, end = today.replace(day=1), today
        if start > end:
            start, end = end, start
        return start, end

    def on_preset_changed(self, text: str) -> None:
        if text == "All records":
            self.from_edit.setEnabled(False)
            self.to_edit.setEnabled(False)
            return
        self.from_edit.setEnabled(True)
        self.to_edit.setEnabled(True)
        today = QDate.currentDate()
        if text == "Today":
            self._set_dates(today, today)
        elif text == "Last 7 days":
            self._set_dates(today.addDays(-6), today)
        elif text == "Last 30 days":
            self._set_dates(today.addDays(-29), today)
        elif text == "This month":
            self._set_dates(QDate(today.year(), today.month(), 1), today)

    def _set_dates(self, start: QDate, end: QDate) -> None:
        """Apply preset dates without tripping the Custom switch."""
        for editor in (self.from_edit, self.to_edit):
            editor.blockSignals(True)
        self.from_edit.setDate(start)
        self.to_edit.setDate(end)
        for editor in (self.from_edit, self.to_edit):
            editor.blockSignals(False)

    def _mark_custom(self, *_args) -> None:
        if self.preset_combo.currentText() not in ("Custom", "All records"):
            self.preset_combo.blockSignals(True)
            self.preset_combo.setCurrentText("Custom")
            self.preset_combo.blockSignals(False)

    def _show_device(self, info) -> None:
        while self.device_grid.count():
            item = self.device_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        rows = [
            ("Device name", info.name or "-"),
            ("Serial number", info.serial or "-"),
            ("Firmware", info.firmware or "-"),
            ("Address", f"{info.host}:{info.port}"),
            ("Users counter", f"{info.users} / {info.users_cap}"),
            ("Records counter", f"{info.records} / {info.records_cap}"),
        ]
        for row, (key, value) in enumerate(rows):
            key_label = QLabel(key)
            key_label.setObjectName("SectionLabel")
            self.device_grid.addWidget(key_label, row, 0, Qt.AlignRight | Qt.AlignTop)
            self.device_grid.addWidget(QLabel(str(value)), row, 1)

    def _set_pill(self, text: str, style: str = "Pill") -> None:
        self.device_pill.setText(text)
        self.device_pill.setObjectName(style)
        self.device_pill.style().unpolish(self.device_pill)
        self.device_pill.style().polish(self.device_pill)

    # -- device jobs -------------------------------------------------------

    def _start_job(self, job: str, **kwargs) -> None:
        if self.thread is not None:
            return
        self.thread = QThread(self)
        self.worker = DeviceWorker()
        self.worker.configure(job, **kwargs)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self.log_line)
        self.worker.tested.connect(self.on_tested)
        self.worker.fetched.connect(self.on_fetched)
        self.worker.failed.connect(self.on_failed)
        self.thread.start()

    def _finish_job(self) -> None:
        if self.thread is not None:
            self.thread.quit()
            self.thread.wait(3000)
            self.thread = None
            self.worker = None
        self._set_busy(False)

    def on_test(self) -> None:
        if self.thread is not None:
            return
        self._set_busy(True, f"Testing {self.host_edit.text().strip()}:{self.port_spin.value()} …")
        self._start_job("test", host=self.host_edit.text().strip(), port=self.port_spin.value(),
                        password=self.password_spin.value(), timeout=self.timeout_spin.value())

    def on_fetch(self) -> None:
        if self.thread is not None:
            return
        self.tabs.setCurrentIndex(3)
        self._set_busy(True, "Fetching attendance …")
        self.read_result = None
        self._start_job("fetch", host=self.host_edit.text().strip(), port=self.port_spin.value(),
                        password=self.password_spin.value(), timeout=self.timeout_spin.value(),
                        pause_device=self.pause_check.isChecked())

    @Slot(object)
    def on_tested(self, info) -> None:
        self._show_device(info)
        self._set_pill(f"{info.name or 'Connected'} · {info.serial or info.host}", "PillOk")
        self._finish_job()
        QMessageBox.information(
            self, "Connection OK",
            f"Device:   {info.name or 'unknown'}\n"
            f"Serial:   {info.serial or '?'}\n"
            f"Firmware: {info.firmware or '?'}\n"
            f"Records:  {info.records}/{info.records_cap}")

    @Slot(object)
    def on_fetched(self, read: DeviceRead) -> None:
        self.read_result = read
        self._show_device(read.info)
        self._set_pill(f"{read.info.name or 'Connected'} · {len(read.records)} records", "PillOk")

        start, end = self._selected_dates()
        self.last_range = (start, end)
        filtered = read.filtered(start, end)

        self.records_model.set_records(filtered.records)
        rows = build_daily_rows(filtered.records)
        self.summary_model.set_rows(rows)
        totals = summary_totals(rows)

        self.records_count.setText(f"{len(filtered.records)} record(s)"
                                   + (f" of {len(read.records)} read" if len(filtered.records) != len(read.records) else ""))
        self.summary_totals_label.setText(
            f"{totals['people']} staff · {totals['days']} day(s) · {totals['hours']:.2f} hours "
            f"· {totals['single_punch']} day(s) with a single punch")

        self.log_block("Decoded", [
            f"format: {read.report.format_label}",
            f"payload: declared {read.report.declared_bytes} B, received {read.report.received_bytes} B",
            f"records: {len(read.records)} (duplicates dropped: {read.report.duplicates_dropped})",
            f"users: {read.report.users_parsed}",
            f"read took {read.duration_seconds}s",
        ] + [f"note: {note}" for note in read.report.notes]
          + [f"WARNING: {warn}" for warn in read.report.warnings])

        self.export_button.setEnabled(bool(filtered.records))
        self.csv_button.setEnabled(bool(filtered.records))
        self.tabs.setCurrentIndex(0)
        self._finish_job()
        self.log_line(f"Fetched {len(read.records)} record(s); {len(filtered.records)} in range.")

    @Slot(str)
    def on_failed(self, message: str) -> None:
        self._set_pill("Connection failed", "PillBad")
        self.log_line(f"FAILED: {message}")
        self._finish_job()
        QMessageBox.critical(self, "Terminal connection failed", message)

    # -- exports -----------------------------------------------------------

    def _ask_path(self, extension: str, kind: str) -> Path | None:
        start, end = self.last_range
        if extension == "xlsx":
            suggested = excel.default_filename(start, end)
            file_filter = "Excel workbook (*.xlsx)"
        else:
            suggested = Path(excel.default_filename(start, end)).with_suffix(".csv").name
            file_filter = "CSV file (*.csv)"
        base = self.settings.get("last_export_dir") or str(Path.home())
        chosen, _ = QFileDialog.getSaveFileName(self, f"Save {kind}", str(Path(base) / suggested),
                                               file_filter)
        if not chosen:
            return None
        path = Path(chosen)
        if path.suffix.lower() != f".{extension}":
            path = path.with_suffix(f".{extension}")
        self.settings["last_export_dir"] = str(path.parent)
        return path

    def on_export(self) -> None:
        if not self.read_result:
            return
        filtered = self.read_result.filtered(*self.last_range)
        if not filtered.records:
            QMessageBox.warning(self, "Nothing to export",
                                "No records in the selected date range.")
            return
        path = self._ask_path("xlsx", "Excel report")
        if path is None:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            start, end = self.last_range
            written = excel.export_workbook(path, filtered, start, end)
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Export failed", f"{type(exc).__name__}: {exc}")
            return
        QApplication.restoreOverrideCursor()
        self.log_line(f"Excel written: {written}")
        self._offer_open(written, "Excel report saved")

    def on_export_csv(self) -> None:
        if not self.read_result:
            return
        filtered = self.read_result.filtered(*self.last_range)
        path = self._ask_path("csv", "CSV copy")
        if path is None:
            return
        try:
            written = excel.export_csv(path, filtered.records)
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", f"{type(exc).__name__}: {exc}")
            return
        self.log_line(f"CSV written: {written}")
        self._offer_open(written, "CSV saved")

    def _offer_open(self, path, title: str) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setIcon(QMessageBox.Information)
        box.setText(f"Saved to:\n{path}")
        open_button = box.addButton("Open file", QMessageBox.AcceptRole)
        box.addButton("Open folder", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Close)
        box.exec()
        clicked = box.clickedButton()
        if clicked is open_button:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        elif clicked is not None and clicked.text() == "Open folder":
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))


def main() -> int:
    app = QApplication(sys.argv)
    configure_app(app)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
