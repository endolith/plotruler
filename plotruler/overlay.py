"""The translucent overlay window.

One frameless, always-on-top, semi-transparent window that floats over
the graph. It spans a region of the screen (user-sizable and movable);
the graph shows through because the background is painted translucent.
Calibration and readout geometry all live in absolute screen
coordinates, so moving or resizing this window never affects them.

The custom title bar is drawn by TitleBar. Moving, resizing, snapping,
and GridMove compatibility come from the Win32 hit-test shim, which
makes the OS treat the title bar as a caption and the edges as real
borders. A transparent margin below the title bar remains empty until
the calibration flow (and readout) are wired in later.

Set PLOTRULER_DEBUG=1 to log window state and native events to stderr.
"""

import os
import sys

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from . import win_hittest
from .titlebar import TITLEBAR_HEIGHT, TitleBar

# Width of the invisible edge hit-zones, in logical pixels.
_EDGE = 8

DEBUG = bool(os.environ.get("PLOTRULER_DEBUG"))


def _dbg(msg):
    if DEBUG:
        print("[plotruler]", msg, file=sys.stderr, flush=True)


class OverlayWindow(QWidget):
    """The translucent overlay window itself."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(320, 200)
        self.resize(900, 600)
        self.setMouseTracking(True)

        self.title_bar = TitleBar(self)
        self.title_bar.setGeometry(0, 0, self.width(), TITLEBAR_HEIGHT)

        # Tracks the manual maximize state; the window itself stays in a
        # normal window state so nothing conflicts with native snapping.
        self._maximized = False
        self._saved_geometry = None

        # Swap Qt's WS_POPUP for real overlapped-window styles so Windows
        # treats this as a normal window: snapping, drag-to-edge, and the
        # taskbar all work. The frame is hidden by WM_NCCALCSIZE. Must
        # happen before the window is first shown.
        self.winId()
        win_hittest.apply_native_overlapped_style(self)
        if DEBUG:
            win_hittest.debug_enabled = True
            self._debug_timer = QTimer(self)
            self._debug_timer.timeout.connect(self._debug_state)
            self._debug_timer.start(1000)

    def _debug_state(self):
        g = self.geometry().getRect()
        sa = self.screen().availableGeometry().getRect()
        style, exstyle = win_hittest.current_styles(self)
        style_desc = "n/a"
        if style is not None:
            parts = []
            if style & win_hittest.WS_POPUP:
                parts.append("POPUP")
            if style & win_hittest.WS_CAPTION:
                parts.append("CAPTION")
            if style & win_hittest.WS_THICKFRAME:
                parts.append("THICKFRAME")
            if style & win_hittest.WS_MAXIMIZEBOX:
                parts.append("MAXBOX")
            if style & win_hittest.WS_MINIMIZEBOX:
                parts.append("MINBOX")
            if style & win_hittest.WS_SYSMENU:
                parts.append("SYSMENU")
            style_desc = "|".join(parts) or "none"
        ex_desc = "n/a"
        if exstyle is not None:
            ex_parts = []
            if exstyle & win_hittest.WS_EX_TOOLWINDOW:
                ex_parts.append("TOOLWIN")
            if exstyle & win_hittest.WS_EX_TOPMOST:
                ex_parts.append("TOPMOST")
            if exstyle & win_hittest.WS_EX_LAYERED:
                ex_parts.append("LAYERED")
            ex_desc = "|".join(ex_parts) or "none"
        _dbg(
            f"state max={self.is_maximized()} ws={self.windowState()} "
            f"vis={self.isVisible()} geo={g} work={sa} "
            f"style=[{style_desc}] ex=[{ex_desc}]"
        )

    def is_maximized(self):
        return self._maximized

    def toggle_maximize(self):
        """Fill the screen, or return to the last window size."""
        _dbg(f"toggle_maximize called, is_max={self._maximized}")
        if self._maximized:
            self.setGeometry(self._saved_geometry)
            self._maximized = False
        else:
            self._saved_geometry = self.geometry()
            # Setting the geometry directly (instead of showMaximized)
            # skips the native slide-to-corner animation that reads as a
            # flash on a frameless overlay.
            self.setGeometry(self.screen().availableGeometry())
            self._maximized = True
        _dbg(
            f"toggle_maximize done, is_max={self._maximized} "
            f"geo={self.geometry().getRect()}"
        )

    def minimize_to_tray(self):
        """Hide the overlay; the app stays resident in the tray."""
        self.hide()

    def close_app(self):
        QApplication.quit()

    def hit_test_code(self, local):
        """Classify a local point for Win32 hit testing.

        Returns an HT* value telling Windows what this part of the
        window is for: borders resize natively, the title bar is a real
        caption (drag + snap), and everything else is ordinary client
        area that Qt receives.
        """
        w, h = self.width(), self.height()
        x, y = local.x(), local.y()
        if not self.rect().contains(local):
            return win_hittest.HTCLIENT
        if x < _EDGE and y < _EDGE:
            return win_hittest.HTTOPLEFT
        if x >= w - _EDGE and y < _EDGE:
            return win_hittest.HTTOPRIGHT
        if x < _EDGE and y >= h - _EDGE:
            return win_hittest.HTBOTTOMLEFT
        if x >= w - _EDGE and y >= h - _EDGE:
            return win_hittest.HTBOTTOMRIGHT
        if y < _EDGE:
            return win_hittest.HTTOP
        if y >= h - _EDGE:
            return win_hittest.HTBOTTOM
        if x < _EDGE:
            return win_hittest.HTLEFT
        if x >= w - _EDGE:
            return win_hittest.HTRIGHT
        if y < TITLEBAR_HEIGHT:
            if self.title_bar.is_over_buttons(local):
                return win_hittest.HTCLIENT
            return win_hittest.HTCAPTION
        return win_hittest.HTCLIENT

    def nativeEvent(self, event_type, message):
        result = win_hittest.handle_native_event(self, event_type, message)
        if DEBUG and result[0]:
            msg = win_hittest.wintypes.MSG.from_address(int(message))
            _dbg(f"nativeEvent msg=0x{msg.message:04x} handled={result[1]}")
        return result

    def mousePressEvent(self, event):
        pos = event.position().toPoint()
        _dbg(f"mousePress at {pos.x()},{pos.y()}")
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if DEBUG and event.buttons():
            pos = event.position().toPoint()
            _dbg(f"mouseMove (dragging) at {pos.x()},{pos.y()}")
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        pos = event.position().toPoint()
        _dbg(f"mouseRelease at {pos.x()},{pos.y()}")
        super().mouseReleaseEvent(event)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            # A native maximize (drag-to-top-edge snap) sets the real
            # window state behind our back; mirror it so the button glyph
            # stays honest.
            self._maximized = self.isMaximized()
            if DEBUG:
                _dbg(
                    f"changeEvent ws={self.windowState()} "
                    f"max={self.isMaximized()}"
                )

    def moveEvent(self, event):
        super().moveEvent(event)
        # Dragging a manually-maximized window restores its normal shape;
        # notice and clear the flag so the next toggle maximizes again.
        if (
            self._maximized
            and self.geometry() != self.screen().availableGeometry()
        ):
            self._maximized = False
            _dbg("cleared _maximized after drag")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # A faint reddish tint so the window is perceivable over both
        # white and black backgrounds, while the graph underneath still
        # shows through.
        painter.fillRect(self.rect(), QColor(255, 60, 60, 26))
        # A clear red border so the user can see where the overlay is
        # and grab it to resize, on light and dark backgrounds alike.
        painter.setPen(QPen(QColor(255, 90, 90, 240), 2))
        painter.drawRect(self.rect().adjusted(1, 1, -2, -2))

    def resizeEvent(self, event):
        self.title_bar.setGeometry(0, 0, self.width(), TITLEBAR_HEIGHT)
        super().resizeEvent(event)
