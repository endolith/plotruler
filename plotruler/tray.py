"""System tray icon for the resident overlay app.

The overlay is an always-on-top window, but it still needs a home in the
taskbar tray so it can be summoned and dismissed and quit without being
visible. This module builds the tray icon (drawn programmatically so no
image asset is needed) and wires a small context menu: show/hide, start a
new calibration, and quit.
"""

from PySide6.QtCore import QObject, QPointF, QRectF, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

# Accent colors matching the overlay so the tray icon feels consistent.
_TRAY_RED_BG = QColor(90, 30, 30)
_CYAN = QColor(80, 200, 255)
_AMBER = QColor(255, 200, 80)


def make_icon():
    """Build a PlotRuler tray icon: a translucent rounded square with a
    stylized graph (axes plus a rising line) drawn in the app colors."""
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    body = _TRAY_RED_BG
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(body)
    painter.drawRoundedRect(QRectF(0, 0, size, size), 14, 14)

    # Axes.
    pen = QPen(QColor(230, 230, 230), 3)
    pen.setStyle(Qt.PenStyle.SolidLine)
    painter.setPen(pen)
    painter.drawLine(QPointF(18, 46), QPointF(44, 12))  # diagonal rising line

    # Small data points along the line.
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_CYAN)
    painter.drawEllipse(QPointF(22, 42), 2.5, 2.5)
    painter.setBrush(_AMBER)
    painter.drawEllipse(QPointF(40, 16), 2.5, 2.5)

    painter.end()
    return QIcon(pixmap)


class TrayIcon(QObject):
    """Owns the system tray icon and its menu, tied to the overlay window."""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self._window = window
        self._tray = QSystemTrayIcon(make_icon(), self)
        self._menu = QMenu()

        self._toggle_action = QAction("Show / Hide", self)
        self._toggle_action.triggered.connect(self._window.toggle_visibility)
        self._new_action = QAction("New Calibration", self)
        self._new_action.triggered.connect(self._start_calibration)
        self._quit_action = QAction("Quit", self)
        self._quit_action.triggered.connect(self._quit)

        self._menu.addAction(self._toggle_action)
        self._menu.addSeparator()
        self._menu.addAction(self._new_action)
        self._menu.addSeparator()
        self._menu.addAction(self._quit_action)

        self._tray.setContextMenu(self._menu)
        self._tray.setToolTip("PlotRuler")
        self._tray.activated.connect(self._on_activated)
        self._tray.show()

    def _start_calibration(self):
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()
        self._window.start_calibration()

    def _on_activated(self, reason):
        # A single left click on the icon toggles the overlay, matching the
        # hotkey and the "Show / Hide" menu item.
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._window.toggle_visibility()

    def _quit(self):
        # QApplication.quit() stops the event loop; the tray icon and window
        # are then torn down by the application object's destructor.
        from PySide6.QtWidgets import QApplication

        QApplication.quit()
