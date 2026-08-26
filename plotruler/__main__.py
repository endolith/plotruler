"""Run PlotRuler with `python -m plotruler`."""

import sys

from PySide6.QtWidgets import QApplication

from .hotkey import GlobalHotkey
from .overlay import OverlayWindow
from .tray import TrayIcon


def main():
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
