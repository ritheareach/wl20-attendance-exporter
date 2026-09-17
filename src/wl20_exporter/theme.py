"""Qt stylesheet — light, modern, and matching the office report palette."""

ACCENT = "#366092"
ACCENT_DARK = "#2b4c75"

STYLESHEET = f"""
QWidget {{
    font-family: "Segoe UI", "SF Pro Text", "Ubuntu", "DejaVu Sans", sans-serif;
    font-size: 13px;
    color: #1f2430;
}}
/* Every surface that paints its own white background must also pin its text
   colour: with the OS in dark mode the inherited palette text is white, which
   renders white-on-white inside these widgets. */
QLabel, QCheckBox, QRadioButton, QGroupBox {{ color: #1f2430; }}
QGroupBox {{ margin-top: 8px; }}
QGroupBox::title {{ color: #4b5563; subcontrol-origin: margin; left: 10px; padding: 0 4px; }}
QMainWindow, QDialog {{ background: #f4f6f9; }}

QLabel#Title {{ font-size: 22px; font-weight: 700; color: {ACCENT}; }}
QLabel#Subtitle {{ font-size: 13px; color: #6b7280; }}
QLabel#SectionLabel {{ font-size: 12px; font-weight: 700; color: #4b5563; }}
QLabel#Hint {{ color: #6b7280; font-size: 12px; }}
QLabel#Pill {{
    background: #e8eef7; color: {ACCENT}; border: 1px solid #c9d8ec;
    border-radius: 10px; padding: 3px 10px; font-size: 12px; font-weight: 600;
}}
QLabel#PillOk {{ background: #e7f6ec; color: #1b7f3b; border: 1px solid #bfe6cb;
    border-radius: 10px; padding: 3px 10px; font-size: 12px; font-weight: 600; }}
QLabel#PillBad {{ background: #fdeaea; color: #b3261e; border: 1px solid #f4c7c3;
    border-radius: 10px; padding: 3px 10px; font-size: 12px; font-weight: 600; }}
QLabel#PillWarn {{ background: #fff4e5; color: #9a5b00; border: 1px solid #f2d5a8;
    border-radius: 10px; padding: 3px 10px; font-size: 12px; font-weight: 600; }}

QFrame#Card {{
    background: #ffffff; border: 1px solid #e2e6ee; border-radius: 10px;
}}
QFrame#Separator {{ background: #e2e6ee; max-height: 1px; border: none; }}

QPushButton {{
    background: #ffffff; border: 1px solid #c9d1de; border-radius: 7px;
    padding: 7px 14px; font-weight: 600;
}}
QPushButton:hover {{ background: #f0f4fa; border-color: #a9b8ce; }}
QPushButton:pressed {{ background: #e4ebf5; }}
QPushButton:disabled {{ color: #a3aab6; background: #f4f5f7; border-color: #e2e5ea; }}
QPushButton#Primary {{
    background: {ACCENT}; color: #ffffff; border-color: {ACCENT};
}}
QPushButton#Primary:hover {{ background: {ACCENT_DARK}; border-color: {ACCENT_DARK}; }}
QPushButton#Primary:disabled {{ background: #9fb2cc; border-color: #9fb2cc; color: #eef2f8; }}
QPushButton#Accent {{
    background: #1b7f3b; color: #ffffff; border-color: #1b7f3b;
}}
QPushButton#Accent:hover {{ background: #166a31; border-color: #166a31; }}
QPushButton#Accent:disabled {{ background: #a9cbb4; border-color: #a9cbb4; color: #eef7f0; }}

QLineEdit, QSpinBox, QDateEdit, QComboBox {{
    color: #1f2430; background: #ffffff; border: 1px solid #c9d1de;
    border-radius: 7px; padding: 5px 6px; min-height: 22px;
    selection-background-color: {ACCENT}; selection-color: #ffffff;
}}
/* Spin boxes and date fields draw their text through the style, which on
   macOS reserves room for the stepper buttons — keep their own padding small
   so the digits always have a text area left. */
QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit, QDateTimeEdit {{
    padding: 4px 4px;
}}
QLineEdit:focus, QSpinBox:focus, QDateEdit:focus, QComboBox:focus {{
    border-color: {ACCENT};
}}
QLineEdit:disabled, QSpinBox:disabled, QDateEdit:disabled, QComboBox:disabled {{
    color: #8b93a1; background: #f2f4f7; border-color: #dfe3ea;
}}
QLineEdit:read-only {{ color: #4b5563; }}
QComboBox QAbstractItemView, QCalendarWidget QAbstractItemView {{
    color: #1f2430; background: #ffffff; selection-background-color: {ACCENT};
    selection-color: #ffffff; border: 1px solid #c9d1de;
}}
QCalendarWidget QWidget {{ color: #1f2430; background: #ffffff; }}
QComboBox::drop-down {{ border: none; width: 18px; }}
QSpinBox::up-button, QSpinBox::down-button,
QDateEdit::up-button, QDateEdit::down-button {{ width: 16px; }}
QCheckBox {{ spacing: 6px; }}

QTableView {{
    color: #1f2430; background: #ffffff; border: 1px solid #e2e6ee; border-radius: 10px;
    gridline-color: #eef1f6; selection-background-color: #dbe6f6;
    selection-color: #1f2430; alternate-background-color: #fafbfd;
}}
QHeaderView::section {{
    background: {ACCENT}; color: #ffffff; border: none; padding: 8px 6px;
    font-weight: 700;
}}
QHeaderView::section:horizontal {{ border-right: 1px solid #4a7099; }}
QTableCornerButton::section {{ background: {ACCENT}; border: none; }}

QTabWidget::pane {{ border: none; top: 6px; }}
QTabBar::tab {{
    background: transparent; padding: 8px 16px; margin-right: 4px;
    border-radius: 7px; color: #4b5563; font-weight: 600;
}}
QTabBar::tab:selected {{ background: #ffffff; color: {ACCENT}; border: 1px solid #e2e6ee; }}
QTabBar::tab:hover {{ color: {ACCENT}; }}

QPlainTextEdit {{
    color: #1f2430; background: #ffffff; border: 1px solid #e2e6ee; border-radius: 10px;
    font-family: "SF Mono", "Consolas", "DejaVu Sans Mono", monospace;
    font-size: 12px; padding: 6px;
}}
QProgressBar {{
    color: #1f2430; border: none; border-radius: 3px; background: #e2e6ee;
    height: 6px; text-align: center;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}
QStatusBar {{ background: #ffffff; border-top: 1px solid #e2e6ee; color: #4b5563; }}
QTabWidget::pane, QTabBar::tab {{ color: #4b5563; }}
QToolTip {{ background: #1f2430; color: #ffffff; border: none; padding: 6px; }}
QScrollBar:vertical, QScrollBar:horizontal {{ background: #f4f6f9; border: none; }}
QScrollBar::handle {{ background: #c3cbd8; border-radius: 5px; min-height: 24px; }}
QMenu {{ color: #1f2430; background: #ffffff; }}
"""
