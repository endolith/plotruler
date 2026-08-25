"""The translucent overlay window.

One frameless, always-on-top, semi-transparent window that floats over
the graph. It spans a region of the screen (user-sizable and movable);
the graph shows through because the background is painted translucent.
Calibration and readout geometry all live in absolute screen
coordinates, so moving or resizing this window never affects them.

The custom title bar and resize handles are implemented by TitleBar and
Resizer. A transparent margin below the title bar remains empty until
the calibration flow (and readout) are wired in later.
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from .resize import Resizer
from .titlebar import TITLEBAR_HEIGHT, TitleBar


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
        # Without mouse tracking the resize cursors would only appear
        # mid-drag; edges need to react on hover too.
        self.setMouseTracking(True)

        self._maximized = False
        self._saved_geometry = None

        self.title_bar = TitleBar(self)
        self.title_bar.setGeometry(0, 0, self.width(), TITLEBAR_HEIGHT)
        self.resizer = Resizer(self)

    def is_maximized(self):
        return self._maximized

    def toggle_maximize(self):
        """Fill the screen, or return to the last window size."""
        if self._maximized:
            self.setGeometry(self._saved_geometry)
            self._maximized = False
        else:
            self._saved_geometry = self.geometry()
            self.setGeometry(self.screen().availableGeometry())
            self._maximized = True

    def minimize_to_tray(self):
        """Hide the overlay; the app stays resident in the tray."""
        self.hide()

    def close_app(self):
        QApplication.quit()

    def titlebar_under(self, pos):
        """True when a local position is over the title bar strip."""
        return pos.y() < TITLEBAR_HEIGHT

    # --- Mouse: forward to title bar or resizer, not both ---
    def mousePressEvent(self, event):
        if self.titlebar_under(event.position().toPoint()):
            self.title_bar.mousePressEvent(event)
        else:
            self.resizer.on_mouse_press(event)

    def mouseMoveEvent(self, event):
        if self.titlebar_under(event.position().toPoint()):
            self.title_bar.mouseMoveEvent(event)
        else:
            self.resizer.on_mouse_move(event)

    def mouseReleaseEvent(self, event):
        self.title_bar.mouseReleaseEvent(event)
        self.resizer.on_mouse_release(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # A faint tint so the window is perceivable, while the graph
        # underneath still shows through.
        painter.fillRect(self.rect(), QColor(255, 255, 255, 14))
        # A clear border so the user can see where the overlay is and
        # grab it to resize.
        painter.setPen(QPen(QColor(60, 60, 60, 200), 2))
        painter.drawRect(self.rect().adjusted(1, 1, -2, -2))

    def resizeEvent(self, event):
        self.title_bar.setGeometry(0, 0, self.width(), TITLEBAR_HEIGHT)
        super().resizeEvent(event)
