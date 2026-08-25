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

TITLEBAR_HEIGHT = 32
_BUTTON_WIDTH = 40
_GLYPH = QColor(220, 220, 220)
_HOVER_BG = QColor(255, 255, 255, 36)
_CLOSE_BG = QColor(232, 17, 35)


class TitleBar(QWidget):
    """A translucent title strip painted on the overlay."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._min_rect = QRectF()
        self._max_rect = QRectF()
        self._close_rect = QRectF()
        self._hover_button = None
        self.setMouseTracking(True)

    def _layout(self):
        w = self.width()
        self._close_rect = QRectF(
            w - _BUTTON_WIDTH, 0, _BUTTON_WIDTH, self.height()
        )
        self._max_rect = QRectF(
            w - 2 * _BUTTON_WIDTH, 0, _BUTTON_WIDTH, self.height()
        )
        self._min_rect = QRectF(
            w - 3 * _BUTTON_WIDTH, 0, _BUTTON_WIDTH, self.height()
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
        painter.drawText(
            QRectF(
                10, 0, self.width() - 3 * _BUTTON_WIDTH - 20, self.height()
            ),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            "PlotRuler",
        )

        self._draw_minimize(painter)
        self._draw_maximize(painter)
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
        if self.window().isMaximized():
            # Restore icon: two overlapping squares.
            painter.drawRect(QRectF(rect.x() + 9, rect.y() + 13, 14, 14))
            painter.drawRect(QRectF(rect.x() + 13, rect.y() + 9, 14, 14))
        else:
            painter.drawRect(QRectF(rect.x() + 12, rect.y() + 9, 16, 16))

    def _draw_close(self, painter):
        if self._hover_button == "close":
            painter.fillRect(self._close_rect, _CLOSE_BG)
        painter.setPen(QPen(QColor(255, 255, 255), 2))
        rect = self._close_rect
        painter.drawLine(
            QPointF(rect.x() + 13, rect.y() + 10),
            QPointF(rect.right() - 13, rect.bottom() - 10),
        )
        painter.drawLine(
            QPointF(rect.right() - 13, rect.y() + 10),
            QPointF(rect.x() + 13, rect.bottom() - 10),
        )

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        button = self._button_at(event.position())
        if button == "min":
            self.window().minimize_to_tray()
        elif button == "max":
            self.window().toggle_maximize()
        elif button == "close":
            self.window().close_app()

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
