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
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from . import win_hittest
from .titlebar import TITLEBAR_HEIGHT, TitleBar

# Width of the invisible edge hit-zones, in logical pixels.
_EDGE = 8


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

        # Swap Qt's WS_POPUP for real overlapped-window styles so Windows
        # treats this as a normal window: snapping, drag-to-edge, and the
        # taskbar all work. The frame is hidden by WM_NCCALCSIZE. Must
        # happen before the window is first shown.
        self.winId()
        win_hittest.apply_native_overlapped_style(self)

    def toggle_maximize(self):
        """Fill the screen, or return to the last window size."""
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

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
        return win_hittest.handle_native_event(self, event_type, message)

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
