"""Qt stylesheet — light, modern, and matching the office report palette."""

ACCENT = "#366092"
ACCENT_DARK = "#2b4c75"

STYLESHEET = f"""
QWidget {{
    font-family: "Segoe UI", "SF Pro Text", "Ubuntu", "DejaVu Sans", sans-serif;
    font-size: 13px;
    color: #1f2430;
}}
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
    background: #ffffff; border: 1px solid #c9d1de; border-radius: 7px;
    padding: 6px 8px; selection-background-color: {ACCENT};
}}
QLineEdit:focus, QSpinBox:focus, QDateEdit:focus, QComboBox:focus {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{ border: none; width: 18px; }}
QCheckBox {{ spacing: 6px; }}

QTableView {{
    background: #ffffff; border: 1px solid #e2e6ee; border-radius: 10px;
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
    background: #ffffff; border: 1px solid #e2e6ee; border-radius: 10px;
    font-family: "SF Mono", "Consolas", "DejaVu Sans Mono", monospace;
    font-size: 12px; padding: 6px;
}}
QProgressBar {{
    border: none; border-radius: 3px; background: #e2e6ee; height: 6px; text-align: center;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}
QStatusBar {{ background: #ffffff; border-top: 1px solid #e2e6ee; color: #4b5563; }}
QToolTip {{ background: #1f2430; color: #ffffff; border: none; padding: 6px; }}
"""
