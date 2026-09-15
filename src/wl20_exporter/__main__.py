"""Entry point: ``python -m wl20_exporter`` opens the GUI, ``--cli`` the CLI."""

from __future__ import annotations

import sys


def main() -> int:
    if "--cli" in sys.argv:
        from .cli import main as cli_main
        return cli_main([arg for arg in sys.argv[1:] if arg != "--cli"])
    try:
        from .gui import main as gui_main
    except ImportError as exc:
        print(f"PySide6 is required for the graphical app ({exc}).\n"
              f"Use the command line instead: python -m wl20_exporter --cli --help",
              file=sys.stderr)
        return 1
    return gui_main()


if __name__ == "__main__":
    raise SystemExit(main())
