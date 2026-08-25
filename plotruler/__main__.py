"""Run PlotRuler with `python -m plotruler`."""

import sys

from PySide6.QtWidgets import QApplication

from .overlay import OverlayWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("PlotRuler")
    window = OverlayWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
