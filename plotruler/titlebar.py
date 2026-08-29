"""The custom title bar of the overlay window.

There is no native title bar on a frameless translucent window, so we
paint our own: a translucent red strip with the app name and the
standard window controls (minimize to tray, maximize/restore, close).
Moving, snapping, and double-click-maximize are handled by the Win32
hit-test shim, which makes the OS treat this strip as a real caption,
so Aero Snap and external window tools work. Everything here is drawn
with QPainter — no native widgets.
"""

from PySide6.QtCore import QPointF, QRectF, QSizeF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from . import win_hittest

TITLEBAR_HEIGHT = 32
_BUTTON_WIDTH = 40
# The invisible resize hit-zone width, matching the overlay so the top edge
# and top corners resize the same way the other borders do on non-Windows.
_RESIZE_ZONE = 14
_GLYPH = QColor(220, 220, 220)
_HOVER_BG = QColor(255, 255, 255, 36)


class TitleBar(QWidget):
    """A translucent title strip painted on the overlay."""

    def __init__(self, parent=None, show_close=False):
        super().__init__(parent)
        self._min_rect = QRectF()
        self._max_rect = QRectF()
        self._close_rect = QRectF()
        self._hover_button = None
        self._pressed_button = None
        # On platforms with no system tray there is no way to summon the
        # overlay back after hiding, so hiding is a dead end; offer a real
        # close (quit) button instead. On Windows the tray is the natural
        # close path and no button is drawn.
        self.show_close = show_close
        self.setMouseTracking(True)

    def _layout(self):
        w = self.width()
        # Buttons are laid right to left. With a close button present it
        # takes the rightmost slot; otherwise minimize and maximize fill the
        # two slots next to the edge, as on Windows.
        right = w
        if self.show_close:
            self._close_rect = QRectF(
                right - _BUTTON_WIDTH, 0, _BUTTON_WIDTH, self.height()
            )
            right -= _BUTTON_WIDTH
        self._max_rect = QRectF(
            right - _BUTTON_WIDTH, 0, _BUTTON_WIDTH, self.height()
        )
        self._min_rect = QRectF(
            right - 2 * _BUTTON_WIDTH, 0, _BUTTON_WIDTH, self.height()
        )

    def is_over_buttons(self, pos):
        """True when a window-coordinate point hits a control button."""
        for rect in (self._min_rect, self._max_rect, self._close_rect):
            if rect.contains(pos):
                return True
        return False

    def _button_at(self, pos):
        for rect, name in (
            (self._min_rect, "min"),
            (self._max_rect, "max"),
            (self._close_rect, "close"),
        ):
            if rect.contains(pos):
                return name
        return None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Backing strip: translucent dark red so the bar reads clearly
        # over any graph while the rest of the window stays see-through.
        painter.fillRect(self.rect(), QColor(45, 10, 10, 220))
        # A red accent line along the bottom so the bar's edge stays
        # visible even over a black background.
        painter.fillRect(
            0, self.height() - 2, self.width(), 2, QColor(255, 90, 90, 220)
        )

        # App name.
        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(235, 235, 235))
        # Reserve room for the buttons on the right; three when a close
        # button is shown, two otherwise.
        button_span = _BUTTON_WIDTH * (3 if self.show_close else 2)
        painter.drawText(
            QRectF(10, 0, self.width() - button_span - 20, self.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            "PlotRuler",
        )

        self._draw_minimize(painter)
        self._draw_maximize(painter)
        if self.show_close:
            self._draw_close(painter)

    def _draw_minimize(self, painter):
        if self._hover_button == "min":
            painter.fillRect(self._min_rect, _HOVER_BG)
        painter.setPen(QPen(_GLYPH, 2))
        y = self._min_rect.center().y()
        painter.drawLine(
            QPointF(self._min_rect.x() + 14, y),
            QPointF(self._min_rect.right() - 14, y),
        )

    def _draw_maximize(self, painter):
        if self._hover_button == "max":
            painter.fillRect(self._max_rect, _HOVER_BG)
        painter.setPen(QPen(_GLYPH, 2))
        rect = self._max_rect
        if self.window().is_maximized():
            # Restore icon: two overlapping squares.
            painter.drawRect(QRectF(rect.x() + 9, rect.y() + 13, 14, 14))
            painter.drawRect(QRectF(rect.x() + 13, rect.y() + 9, 14, 14))
        else:
            painter.drawRect(QRectF(rect.x() + 12, rect.y() + 9, 16, 16))

    def _draw_close(self, painter):
        """Draw an X glyph for the close button."""
        if self._hover_button == "close":
            painter.fillRect(self._close_rect, _HOVER_BG)
        painter.setPen(QPen(_GLYPH, 2))
        rect = self._close_rect
        x = rect.center().x()
        y = rect.center().y()
        painter.drawLine(QPointF(x - 7, y - 7), QPointF(x + 7, y + 7))
        painter.drawLine(QPointF(x - 7, y + 7), QPointF(x + 7, y - 7))

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if not win_hittest._IS_WINDOWS:
            # On X11 there is no WM_NCHITTEST, so a press on an edge zone
            # resizes and a press on the bar moves the window itself. Ask
            # Qt to drive the gesture directly.
            edges = self._resize_edges(event.position())
            if edges is not None:
                self.window().windowHandle().startSystemResize(edges)
                event.accept()
                return
            if self._button_at(event.position()) is None:
                self.window().windowHandle().startSystemMove()
                event.accept()
                return
        # Remember which button was pressed, but do not act yet. Acting on
        # press would let the button's release fall through to whatever
        # window is underneath once we quit (see mouseReleaseEvent), which
        # is how a click on PlotRuler's close button could also close the
        # app beneath it.
        self._pressed_button = self._button_at(event.position())
        event.accept()

    def _resize_edges(self, pos):
        """Return the Qt.Edges for a top-edge resize at a titlebar point,
        or None.

        The titlebar covers the top strip, so the top border's resize zones
        land here rather than in the overlay's mousePressEvent. Top corners
        combine a vertical edge with a horizontal one; the middle of the bar
        is a move, handled by the caller as a plain drag.
        """
        w = self.width()
        x, y = pos.x(), pos.y()
        if y >= _RESIZE_ZONE:
            return None
        edges = Qt.Edges()
        if x < _RESIZE_ZONE:
            edges |= Qt.Edge.LeftEdge
        elif x >= w - _RESIZE_ZONE:
            edges |= Qt.Edge.RightEdge
        edges |= Qt.Edge.TopEdge
        return edges

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        # Only act if the press began on the same button, so a click that
        # starts elsewhere and ends here (or vice versa) does not fire.
        button = self._button_at(event.position())
        if button != self._pressed_button:
            self._pressed_button = None
            event.accept()
            return
        self._pressed_button = None
        event.accept()
        if button == "min":
            self.window().minimize_to_tray()
        elif button == "max":
            self.window().toggle_maximize()
        elif button == "close":
            # On no-tray platforms there is no way back after hiding, so
            # close really quits rather than depositing a ghost overlay.
            self.window().quit()

    def mouseMoveEvent(self, event):
        hover = self._button_at(event.position())
        if hover != self._hover_button:
            self._hover_button = hover
            self.update()

    def leaveEvent(self, event):
        self._hover_button = None
        self.update()

    def resizeEvent(self, event):
        self._layout()
        super().resizeEvent(event)

    def sizeHint(self):
        return QSizeF(0, TITLEBAR_HEIGHT).toSize()
