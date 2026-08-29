"""System tray icon for the resident overlay app.

The overlay is an always-on-top window, but it still needs a home in the
taskbar tray so it can be summoned and dismissed and quit without being
visible. This module builds the tray icon (drawn programmatically so no
image asset is needed) and wires a small context menu: show/hide, start a
new calibration, and quit.
"""

from PySide6.QtCore import QObject, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QIcon,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .format import NAMES, OPTIONS

# Accent colors matching the overlay so the tray icon feels consistent.
# The icon cyan is brighter than the overlay's so the crosshair arms have
# similar luminance (the amber Y-arm would otherwise outshine it).
_TRAY_RED_BG = QColor(90, 30, 30)
_ICON_CYAN = QColor(140, 230, 255)
_AMBER = QColor(255, 200, 80)
_LIGHT = QColor(235, 235, 235)


def make_icon(size=64):
    """Build a PlotRuler tray icon.

    A dark rounded tile with a graph-axes L (light) and a crosshair whose
    two arms are the app's X/Y accent colors. The crosshair is the focal
    point so the icon still reads as 'measure a point on a graph' at the
    tiny size Windows tray icons render.

    Everything is drawn on even pixel coordinates with integer rects so
    the icon downsamples symmetrically: the crosshair sits at the tile's
    center and each arm is exactly 4px thick, so at 16px the two arms
    land on the same 1-pixel column/row and stay equally bright.

    `size` is the render canvas in pixels. The layout is tuned for 64px
    and scaled up proportionally for other sizes (e.g. a high-res icon
    for the packaged executable).
    """
    k = size // 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    # Dark rounded tile so the light strokes pop on the taskbar tray.
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_TRAY_RED_BG)
    painter.drawRoundedRect(QRectF(0, 0, size, size), 14 * k, 14 * k)

    # Graph axes: a light L along the bottom and left. Rects are
    # integer-aligned and 4px thick, symmetric about their center.
    painter.setPen(Qt.PenStyle.NoPen)
    painter.fillRect(QRect(8 * k, 52 * k, 48 * k, 4 * k), _LIGHT)  # x-axis
    painter.fillRect(QRect(8 * k, 8 * k, 4 * k, 48 * k), _LIGHT)  # y-axis

    # Crosshair arms: identical 4px-thick integer rects. The center is at
    # 34 (not 32) because the 64->16 downsampler bins the canvas into 4x4
    # blocks; an arm centered on 32 spans rows 30-33 and straddles two bins,
    # lighting up two 16px rows. Centering on 34 (= 4*8 + 2) puts each arm
    # wholly inside one bin, so both arms are single symmetric pixels.
    thickness = 4 * k
    half = 10 * k
    t2 = thickness // 2
    cx = cy = 34 * k
    painter.fillRect(
        QRect(cx - half, cy - t2, half * 2, thickness), _ICON_CYAN
    )  # X arm (horizontal)
    painter.fillRect(
        QRect(cx - t2, cy - half, thickness, half * 2), _AMBER
    )  # Y arm (vertical)

    # A small light center dot so the crosshair reads as one target.
    painter.setBrush(_LIGHT)
    painter.drawEllipse(QPointF(cx, cy), 2.0 * k, 2.0 * k)

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

        self._format_menu = QMenu("Number Format", self._menu)
        self._format_group = QActionGroup(self._format_menu)
        self._format_actions = {}
        for index, fmt in enumerate(OPTIONS):
            # Number each option the same way the keyboard selects it, so
            # the menu and the number-key shortcuts always agree.
            action = QAction(f"{index + 1}. {NAMES[fmt]}", self._format_menu)
            action.setCheckable(True)
            action.triggered.connect(
                lambda _checked, key=fmt: self._choose_format(key)
            )
            self._format_group.addAction(action)
            self._format_actions[fmt] = action
            self._format_menu.addAction(action)
        self._format_menu.aboutToShow.connect(self._sync_format_check)

        self._menu.addAction(self._toggle_action)
        self._menu.addSeparator()
        self._menu.addAction(self._new_action)
        self._menu.addAction(self._hotkey_action)
        self._menu.addSeparator()
        self._menu.addMenu(self._format_menu)
        self._menu.addSeparator()
        self._menu.addAction(self._quit_action)

        self._tray.setContextMenu(self._menu)
        self._tray.setToolTip("PlotRuler")
        self._tray.activated.connect(self._on_activated)
        self._tray.show()

    def _change_hotkey(self):
        if self._on_change_hotkey is not None:
            self._on_change_hotkey()

    def _choose_format(self, fmt):
        """Apply a number format chosen from the tray menu."""
        self._window.set_num_format(fmt)

    def _sync_format_check(self):
        """Re-check the menu item matching the overlay's current format.

        The format can change via the number-key shortcuts while the
        overlay is focused, so the menu must reflect the live selection
        each time it opens rather than remembering a stale check.
        """
        current = getattr(self._window, "_num_format", OPTIONS[0])
        for fmt, action in self._format_actions.items():
            action.setChecked(fmt == current)

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
