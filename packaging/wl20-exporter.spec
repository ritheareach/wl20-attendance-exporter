# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build — the same spec produces the Windows, macOS and Linux app.

    pyinstaller packaging/wl20-exporter.spec --noconfirm

Windows / Linux  -> dist/WL20-Attendance-Exporter[.exe]  (single file)
macOS            -> dist/WL20 Attendance Exporter.app    (self-contained bundle)
"""

import sys
from pathlib import Path

SPEC_DIR = Path(SPECPATH).resolve()
ROOT = SPEC_DIR.parent
SRC = ROOT / "src"

# Qt ships hundreds of modules; only Widgets/Gui/Core are used. Dropping the
# rest keeps the single-file build ~3x smaller and much faster to start.
EXCLUDES = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets", "PySide6.QtQml", "PySide6.QtQuick",
    "PySide6.QtQuick3D", "PySide6.QtQuickWidgets", "PySide6.Qt3DCore", "PySide6.Qt3DRender",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets", "PySide6.QtBluetooth", "PySide6.QtNfc",
    "PySide6.QtPositioning", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner",
    "PySide6.QtHelp", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtPdf",
    "PySide6.QtPdfWidgets", "PySide6.QtSerialPort", "PySide6.QtSvgWidgets",
    "PySide6.QtTextToSpeech", "PySide6.QtUiTools", "PySide6.QtNetworkAuth",
    "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtSensors",
    "PySide6.QtSpatialAudio", "PySide6.QtStateMachine", "PySide6.QtWebView",
    "tkinter", "unittest", "pydoc", "doctest", "pytest",
]

a = Analysis(
    [str(SPEC_DIR / "launcher.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=[],
    hiddenimports=["zk", "openpyxl", "wl20_exporter"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)

pyz = PYZ(a.pure)

EXE_KWARGS = dict(
    name="WL20-Attendance-Exporter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

if sys.platform == "darwin":
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **EXE_KWARGS)
    app = BUNDLE(
        exe,
        name="WL20 Attendance Exporter.app",
        icon=None,
        bundle_identifier="com.facego.wl20exporter",
        info_plist={
            "CFBundleName": "WL20 Attendance Exporter",
            "CFBundleDisplayName": "WL20 Attendance Exporter",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], runtime_tmpdir=None,
              **EXE_KWARGS)
