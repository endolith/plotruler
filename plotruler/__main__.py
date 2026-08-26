"""Run PlotRuler with `python -m plotruler`."""

import faulthandler
import os
import sys
import traceback

from PySide6.QtWidgets import QApplication

from .hotkey import GlobalHotkey
from .overlay import OverlayWindow
from .tray import TrayIcon


def _crash_log_path():
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or "."
    return os.path.join(base, "PlotRuler", "crash.log")


def _install_crash_logging():
    """Route fatal signal and Python-exception reports to a log file.

    A native segfault in Qt produces no Python traceback, so faulthandler
    writes its dump to a file we can read afterward; a Python exception
    that escapes the event loop is caught by sys.excepthook.
    """
    path = _crash_log_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("\n===== PlotRuler start =====\n")
    try:
        # faulthandler writes on fatal signals using the file descriptor it
        # captured; the file is left open despite no Python reference, so a
        # C++ segfault can still be recorded.
        faulthandler.enable(file=open(path, "a", encoding="utf-8"))
    except Exception:
        pass

    def excepthook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(text)
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = excepthook


def main():
    _install_crash_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("PlotRuler")
    app.setApplicationDisplayName("PlotRuler")

    window = OverlayWindow()

    # Parent the tray to the window so it lives as long as the app does.
    TrayIcon(window, parent=window)
    app.setQuitOnLastWindowClosed(False)  # stay resident in the tray

    hotkey = GlobalHotkey(callback=window.toggle_visibility)
    hotkey.register()
    app.installNativeEventFilter(hotkey)
    app.aboutToQuit.connect(hotkey.unregister)

    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
