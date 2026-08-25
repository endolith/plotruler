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

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from . import win_hittest
from .core import CalibrationSession
from .titlebar import TITLEBAR_HEIGHT, TitleBar

# Width of the invisible edge hit-zones, in logical pixels.
_EDGE = 8

# Anchor marker colors: X on one hue, Y on another, both chosen to read
# against dark and light graph content.
_X_COLOR = QColor(80, 200, 255)
_Y_COLOR = QColor(255, 200, 80)

# Characters allowed while typing a calibration value.
_VALID_CHARS = set("0123456789.-+eE")

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
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.title_bar = TitleBar(self)
        self.title_bar.setGeometry(0, 0, self.width(), TITLEBAR_HEIGHT)

        # Calibration state. A session exists only while the user is
        # (or has just finished) clicking anchors and typing values.
        self._session = None
        self._calibration = None
        self._value_text = ""
        self._value_error = None
        self._caret_visible = True
        self._blink_timer = QTimer(self)
        self._blink_timer.setInterval(530)
        self._blink_timer.timeout.connect(self._blink)

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

    def start_calibration(self):
        """Begin a fresh click-and-type calibration, or restart one."""
        self._session = CalibrationSession()
        self._calibration = None
        self._value_text = ""
        self._value_error = None
        self._caret_visible = True
        if not self._blink_timer.isActive():
            self._blink_timer.start()
        self.activateWindow()
        self.setFocus()
        self.update()

    def cancel_calibration(self):
        """Abandon the calibration in progress and drop all anchors."""
        self._session = None
        self._value_text = ""
        self._value_error = None
        self._blink_timer.stop()
        self.update()

    def _blink(self):
        """Toggle the input caret; repaint only while a value is expected."""
        self._caret_visible = not self._caret_visible
        if self._session is not None and self._session.expecting_value:
            self.update()

    def keyPressEvent(self, event):
        if (
            event.key() == Qt.Key.Key_N
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.start_calibration()
            event.accept()
            return
        if self._session is not None and self._session.active:
            self._session_key(event)
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.minimize_to_tray()
            event.accept()
            return
        super().keyPressEvent(event)

    def _session_key(self, event):
        """Route a key press during calibration."""
        if event.key() == Qt.Key.Key_Escape:
            self.cancel_calibration()
            return
        if (
            event.key() == Qt.Key.Key_Z
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            # Undo un-submitted text first, then a whole step.
            if self._session.expecting_value and self._value_text:
                self._value_text = ""
            else:
                self._session.undo()
                self._value_error = None
            self.update()
            return
        if event.key() == Qt.Key.Key_Backspace:
            if self._session.expecting_value and self._value_text:
                self._value_text = self._value_text[:-1]
                self._value_error = None
                self.update()
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._session.expecting_value:
                self._submit_value()
            return
        if self._session.expecting_value:
            text = event.text()
            if text and all(c in _VALID_CHARS for c in text):
                if len(self._value_text) < 24:
                    self._value_text += text
                    self._value_error = None
                    self.update()

    def _submit_value(self):
        """Commit the typed value to the current anchor point."""
        try:
            value = float(self._value_text)
        except ValueError:
            self._value_error = "That is not a number"
            self.update()
            return
        self._value_text = ""
        self._value_error = None
        self._session.record_value(value)
        self._calibration = self._session.calibration()
        self.update()

    def mousePressEvent(self, event):
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._session is not None
            and self._session.expecting_click
        ):
            # Calibration clicks land on the graph beneath the overlay;
            # make sure this window keeps focus so the typed value is
            # captured here rather than by the underlying app.
            self.activateWindow()
            self.setFocus()
            self._record_click(event)
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def _record_click(self, event):
        """Store the clicked point in physical screen pixels."""
        pos = event.globalPosition()
        dpr = self.devicePixelRatioF()
        self._session.record_point(int(pos.x() * dpr), int(pos.y() * dpr))

    def _local_from_physical(self, px, py):
        """Map a physical screen point back to local logical coordinates."""
        dpr = self.devicePixelRatioF()
        logical = QPoint(int(px / dpr), int(py / dpr))
        return self.mapFromGlobal(logical)

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
        # While Windows drags the window it moves the painted surface as a
        # whole, so screen-anchored calibration markers would stay glued
        # to the old position. Force a repaint so they recompute to their
        # true screen positions.
        self.update()

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
        if self._session is not None:
            self._paint_calibration(painter)

    def _paint_calibration(self, painter):
        self._paint_axis_lines(painter)
        self._paint_anchors(painter)
        self._paint_instruction_box(painter)

    def _paint_axis_lines(self, painter):
        """Draw a guide between the two anchors of each axis once both
        exist, so the user sees the line the calibration will define."""
        for axis, color in (("x", _X_COLOR), ("y", _Y_COLOR)):
            anchors = [a for a in self._session.anchors() if a[0] == axis]
            if len(anchors) < 2:
                continue
            p0 = self._local_from_physical(anchors[0][2], anchors[0][3])
            p1 = self._local_from_physical(anchors[1][2], anchors[1][3])
            pen = QPen(color, 1)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawLine(p0, p1)

    def _paint_anchors(self, painter):
        """Draw a crosshair marker (and value label) for each anchor."""
        for axis, _index, px, py, value in self._session.anchors():
            local = self._local_from_physical(px, py)
            color = _X_COLOR if axis == "x" else _Y_COLOR
            x, y = local.x(), local.y()
            painter.setPen(QPen(color, 2))
            painter.drawLine(x - 8, y, x + 8, y)
            painter.drawLine(x, y - 8, x, y + 8)
            painter.setPen(QPen(QColor(20, 20, 20), 1))
            painter.setBrush(QColor(255, 255, 255, 220))
            painter.drawEllipse(local, 3, 3)
            if value is not None:
                self._draw_anchor_label(painter, local, value, color)

    def _draw_anchor_label(self, painter, local, value, color):
        """Paint a value beside its anchor on a light chip for legibility."""
        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        text = str(value)
        metrics = QFontMetricsF(font)
        box = QRectF(
            local.x() + 10,
            local.y() - metrics.height() / 2 - 2,
            metrics.horizontalAdvance(text) + 8,
            metrics.height() + 4,
        )
        painter.fillRect(box, QColor(255, 255, 255, 235))
        painter.setPen(QColor(20, 20, 20))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

    def _paint_instruction_box(self, painter):
        """Paint the translucent prompt box at the bottom of the window."""
        box = QRectF(20, self.height() - 92, self.width() - 40, 72)
        painter.fillRect(box, QColor(20, 20, 20, 235))
        painter.setPen(QPen(QColor(255, 255, 255, 50), 1))
        painter.drawRoundedRect(box, 8, 8)

        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        painter.setFont(font)
        if self._session.active:
            title_color = QColor(255, 255, 255)
        else:
            title_color = QColor(120, 230, 140)
        painter.setPen(title_color)
        painter.drawText(
            QRectF(box.x() + 8, box.y() + 4, box.width() - 16, 16),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._session.prompt(),
        )

        if self._session.expecting_value:
            self._draw_value_input(painter, box)
        if self._value_error:
            small = QFont()
            small.setPointSize(8)
            painter.setFont(small)
            painter.setPen(QColor(255, 120, 120))
            painter.drawText(
                QRectF(box.x() + 8, box.y() + 42, box.width() - 16, 14),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                self._value_error,
            )

        hint = QFont()
        hint.setPointSize(9)
        painter.setFont(hint)
        painter.setPen(QColor(200, 200, 200))
        if self._session.active:
            hint_text = "Ctrl+Z undo  ·  Esc cancel"
        else:
            hint_text = "Ctrl+N redo  ·  Esc hide"
        painter.drawText(
            QRectF(box.x() + 8, box.y() + 56, box.width() - 16, 12),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            hint_text,
        )

    def _draw_value_input(self, painter, box):
        """Paint the typed value and a blinking caret on the input line."""
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        line = QRectF(box.x() + 8, box.y() + 22, box.width() - 16, 20)
        text = self._value_text or " "
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(
            line,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            text,
        )
        if self._caret_visible:
            caret_x = line.x() + metrics.horizontalAdvance(text) + 1
            cy = line.center().y()
            painter.drawLine(
                QPointF(caret_x, cy - 7), QPointF(caret_x, cy + 7)
            )

    def resizeEvent(self, event):
        self.title_bar.setGeometry(0, 0, self.width(), TITLEBAR_HEIGHT)
        super().resizeEvent(event)
