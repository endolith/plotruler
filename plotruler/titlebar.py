"""The custom title bar of the overlay window.

There is no native title bar on a frameless translucent window, so we
paint our own: a translucent strip with the app name and a minimize-to-
tray button. Drag anywhere on the strip to move the window; click the
button to hide to the tray. Everything is drawn with QPainter — no
native widgets, matching the rest of the overlay.
"""

from PySide6.QtCore import QRectF, QSizeF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

TITLEBAR_HEIGHT = 28
_BUTTON_WIDTH = 30
_BUTTON_MARGIN = 4


class TitleBar(QWidget):
    """A draggable, translucent title strip painted on the overlay."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._minimize_rect = QRectF()
        self._drag_offset = None
        self._minimized = False

    def _layout(self):
        w = self.width()
        self._minimize_rect = QRectF(
            w - _BUTTON_WIDTH - _BUTTON_MARGIN,
            (self.height() - _BUTTON_WIDTH) / 2,
            _BUTTON_WIDTH,
            _BUTTON_WIDTH,
        )

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Backing strip: translucent dark so text stays readable over
        # any graph while the rest of the window stays see-through.
        painter.fillRect(self.rect(), QColor(30, 30, 30, 120))

        # App name.
        painter.setPen(QColor(230, 230, 230))
        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            QRectF(10, 0, self.width() - _BUTTON_WIDTH - 20, self.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            "PlotRuler",
        )

        # Minimize-to-tray button: a small "—" in the top-right corner.
        painter.setPen(QPen(QColor(200, 200, 200), 2))
        bar = QRectF(
            self._minimize_rect.x() + 7,
            self._minimize_rect.y() + self._minimize_rect.height() / 2 - 1,
            self._minimize_rect.width() - 14,
            2,
        )
        painter.drawLine(bar.topLeft(), bar.topRight())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._minimize_rect.contains(event.position()):
                self._minimized = True
                self.window().hide()
            else:
                self._drag_offset = (
                    event.globalPosition().toPoint()
                    - self.window().frameGeometry().topLeft()
                )

    def mouseMoveEvent(self, event):
        if (
            self._drag_offset is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            self.window().move(
                event.globalPosition().toPoint() - self._drag_offset
            )

    def mouseReleaseEvent(self, event):
        self._drag_offset = None

    def resizeEvent(self, event):
        self._layout()
        super().resizeEvent(event)

    def sizeHint(self):
        return QSizeF(0, TITLEBAR_HEIGHT).toSize()
