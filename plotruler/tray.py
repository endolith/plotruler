"""System tray icon for the resident overlay app.

The overlay is an always-on-top window, but it still needs a home in the
taskbar tray so it can be summoned and dismissed and quit without being
visible. This module builds the tray icon (drawn programmatically so no
image asset is needed) and wires a small context menu: show/hide, start a
new calibration, and quit.
"""

from PySide6.QtCore import QObject, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

# Accent colors matching the overlay so the tray icon feels consistent.
# The icon cyan is brighter than the overlay's so the crosshair arms have
# similar luminance (the amber Y-arm would otherwise outshine it).
_TRAY_RED_BG = QColor(90, 30, 30)
_ICON_CYAN = QColor(140, 230, 255)
_AMBER = QColor(255, 200, 80)
_LIGHT = QColor(235, 235, 235)


def make_icon():
    """Build a PlotRuler tray icon.

    A dark rounded tile with a graph-axes L (light) and a crosshair whose
    two arms are the app's X/Y accent colors. The crosshair is the focal
    point so the icon still reads as 'measure a point on a graph' at the
    tiny size Windows tray icons render.

    Everything is drawn on even pixel coordinates with integer rects so
    the icon downsamples symmetrically: the crosshair sits at the tile's
    center (32,32) and each arm is exactly 4px thick, so at 16px the two
    arms land on the same 1-pixel column/row and stay equally bright.
    """
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    # Dark rounded tile so the light strokes pop on the taskbar tray.
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_TRAY_RED_BG)
    painter.drawRoundedRect(QRectF(0, 0, size, size), 14, 14)

    # Graph axes: a light L along the bottom and left. Rects are
    # integer-aligned and 4px thick, symmetric about their center.
    painter.setPen(Qt.PenStyle.NoPen)
    painter.fillRect(QRect(8, 52, 48, 4), _LIGHT)  # x-axis (horizontal)
    painter.fillRect(QRect(8, 8, 4, 48), _LIGHT)  # y-axis (vertical)

    # Crosshair arms: identical 4px-thick integer rects, centered on the
    # tile's midpoint so the vertical does not straddle a half-pixel.
    thickness = 4
    half = 10
    t2 = thickness // 2
    cx = cy = size // 2  # 32, 32
    painter.fillRect(
        QRect(cx - half, cy - t2, half * 2, thickness), _ICON_CYAN
    )  # X arm (horizontal)
    painter.fillRect(
        QRect(cx - t2, cy - half, thickness, half * 2), _AMBER
    )  # Y arm (vertical)

    # A small light center dot so the crosshair reads as one target.
    painter.setBrush(_LIGHT)
    painter.drawEllipse(QPointF(cx, cy), 2.0, 2.0)

    painter.end()
    return QIcon(pixmap)


class TrayIcon(QObject):
    """Owns the system tray icon and its menu, tied to the overlay window."""

    def __init__(self, window, on_change_hotkey=None, parent=None):
        super().__init__(parent)
        self._window = window
        self._on_change_hotkey = on_change_hotkey
        self._tray = QSystemTrayIcon(make_icon(), self)
        self._menu = QMenu()

        self._toggle_action = QAction("Show / Hide", self)
        self._toggle_action.triggered.connect(self._window.toggle_visibility)
        self._new_action = QAction("New Calibration", self)
        self._new_action.triggered.connect(self._start_calibration)
        self._hotkey_action = QAction("Change Hotkey…", self)
        self._hotkey_action.triggered.connect(self._change_hotkey)
        self._quit_action = QAction("Quit", self)
        self._quit_action.triggered.connect(self._quit)

        self._menu.addAction(self._toggle_action)
        self._menu.addSeparator()
        self._menu.addAction(self._new_action)
        self._menu.addAction(self._hotkey_action)
        self._menu.addSeparator()
        self._menu.addAction(self._quit_action)

        self._tray.setContextMenu(self._menu)
        self._tray.setToolTip("PlotRuler")
        self._tray.activated.connect(self._on_activated)
        self._tray.show()

    def _change_hotkey(self):
        if self._on_change_hotkey is not None:
            self._on_change_hotkey()

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
