"""PyInstaller entry point (double-clickable app).

``--selftest`` boots the whole stack offscreen and exits 0, which is how CI
verifies that the frozen build actually contains Qt, pyzk and openpyxl.
"""

from __future__ import annotations

import multiprocessing
import os
import sys

if __name__ == "__main__":
    multiprocessing.freeze_support()

    if "--selftest" in sys.argv:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        import PySide6
        import openpyxl
        import zk

        from wl20_exporter import __version__, device, excel, gui
        from wl20_exporter.models import DeviceInfo, DeviceRead, ParseReport

        app = gui.QApplication([])
        app.setStyleSheet(gui.STYLESHEET)
        window = gui.MainWindow()
        window.preset_combo.setCurrentText("All records")
        window.on_fetched(DeviceRead(info=DeviceInfo(host="selftest"),
                                     report=ParseReport()))
        window.close()
        print(f"selftest OK — app {__version__} | PySide6 {PySide6.__version__} | "
              f"pyzk {getattr(zk, '__version__', 'ok')} | openpyxl {openpyxl.__version__} | "
              f"parser={device.decode_time.__name__} exporter={excel.export_workbook.__name__}")
        raise SystemExit(0)

    from wl20_exporter.gui import main

    raise SystemExit(main())
