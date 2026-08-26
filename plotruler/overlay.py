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

from PySide6.QtCore import (
    QEvent,
    QPoint,
    QPointF,
    QRect,
    QStandardPaths,
    Qt,
    QTimer,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPen,
)
from PySide6.QtWidgets import QApplication, QWidget

from . import storage, win_hittest
from .core import CalibrationSession
from .titlebar import TITLEBAR_HEIGHT, TitleBar

# Width of the invisible edge hit-zones, in logical pixels.
_EDGE = 8

# Anchor marker colors: X on one hue, Y on another, both chosen to read
# against dark and light graph content.
_X_COLOR = QColor(80, 200, 255)
_Y_COLOR = QColor(255, 200, 80)
# The calibrated-region guide: a green distinct from the axis hues so it
# stays visible against black gridlines and does not read as an anchor.
_REGION_COLOR = QColor(120, 255, 140)

# Characters allowed while typing a calibration value.
_VALID_CHARS = set("0123456789.-+eE")

DEBUG = bool(os.environ.get("PLOTRULER_DEBUG"))


def _config_path():
    """Return the config file path for the current user.

    Uses the Qt-standard per-user config location so the file lands where
    the OS expects (e.g. %APPDATA%/PlotRuler on Windows). The path is
    resolved at call time because the app name is set in main().
    """
    base = (
        QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppConfigLocation
        )
        or "."
    )
    return os.path.join(base, "plotruler.json")


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

        # Readout state: the last hovered cursor position (local logical),
        # and a transient "copied" banner that fades after a short delay.
        self._hover_pos = QPoint()
        self._hover_active = False
        self._copy_notice = ""
        self._copy_timer = QTimer(self)
        self._copy_timer.setSingleShot(True)
        self._copy_timer.setInterval(900)
        self._copy_timer.timeout.connect(self._clear_copy_notice)

        # Debounce geometry writes so dragging or resizing does not hammer
        # the disk on every pixel of movement.
        self._geometry_timer = QTimer(self)
        self._geometry_timer.setSingleShot(True)
        self._geometry_timer.setInterval(600)
        self._geometry_timer.timeout.connect(self._save_geometry)

        self._config_path = _config_path()
        self._restore_state()

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

    def toggle_visibility(self):
        """Show the overlay if hidden, or hide it if visible."""
        if self.isVisible():
            # Save the exact screen rect before hiding. Restoring the window
            # state is not enough: Aero Snap repositions the window but
            # windowState() only reports a general "maximized", so re-showing
            # would fill the screen instead of the snap slot. The recorded
            # geometry pins it back to the snapped spot.
            self._pre_hide_geometry = self.geometry()
            self.hide()
        else:
            self.show()
            saved = getattr(self, "_pre_hide_geometry", None)
            if saved is not None:
                # Drop any maximized state so the geometry rect is honored.
                self.setWindowState(Qt.WindowState.WindowNoState)
                self.setGeometry(saved)
                self._pre_hide_geometry = None
            self._maximized = self.isMaximized()
            self.raise_()
            self.activateWindow()

    def close_app(self):
        QApplication.quit()

    def _restore_state(self):
        """Load the saved geometry and calibration, if any.

        A saved calibration means the overlay opens already calibrated so
        the user can read immediately without re-clicking anchors. A saved
        geometry puts the window back where it was. Either can be absent
        on a first run.
        """
        geometry = storage.geometry(self._config_path)
        if geometry:
            x, y, width, height = geometry
            self.setGeometry(x, y, width, height)
        self._calibration = storage.calibration(self._config_path)

    def _save_geometry(self):
        """Persist the current window geometry."""
        g = self.geometry()
        storage.save(
            self._config_path,
            geometry=[g.x(), g.y(), g.width(), g.height()],
        )

    def _schedule_geometry_save(self):
        """Debounce a geometry save triggered by a move or resize."""
        self._geometry_timer.start()

    def _save_calibration(self):
        """Persist the completed calibration."""
        storage.save(self._config_path, calibration=self._calibration)

    def start_calibration(self):
        """Begin a fresh click-and-type calibration, or restart one."""
        self._session = CalibrationSession()
        self._calibration = None
        self._value_text = ""
        self._value_error = None
        self._caret_visible = True
        self._copy_notice = ""
        self._hover_active = False
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
        calibration = self._session.calibration()
        if calibration is not None:
            # Calibration is complete: switch to readout mode. The session
            # was only a scaffold for collecting anchors; once we have a
            # Calibration we no longer need it, and keeping it would
            # suppress the hover readout.
            self._calibration = calibration
            self._session = None
            self._blink_timer.stop()
            self._save_calibration()
        self.update()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        if self._session is not None and self._session.expecting_click:
            # Calibration clicks land on the graph beneath the overlay;
            # make sure this window keeps focus so the typed value is
            # captured here rather than by the underlying app.
            self.activateWindow()
            self.setFocus()
            self._record_click(event)
            self.update()
            event.accept()
            return
        if self._calibration is not None:
            # Calibration is done: a click copies the hovered readout.
            self._copy_readout()
            event.accept()
            return
        super().mousePressEvent(event)

    def _copy_readout(self):
        """Copy the readout at the cursor as (X, Y) to the clipboard."""
        if not self._hover_active:
            return
        try:
            px, py = self._physical_from_local(self._hover_pos)
            vx, vy = self._calibration.xy(px, py)
        except ValueError, ZeroDivisionError:
            return
        x_str = self._calibration.x.format(vx)
        y_str = self._calibration.y.format(vy)
        text = f"({x_str}, {y_str})"
        QApplication.clipboard().setText(text)
        self._copy_notice = "Copied " + text
        self._copy_timer.start()
        self.update()

    def _clear_copy_notice(self):
        self._copy_notice = ""
        self.update()

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

    def _physical_from_local(self, local):
        """Map a local logical point to physical screen pixels."""
        dpr = self.devicePixelRatioF()
        global_ = self.mapToGlobal(local)
        return int(global_.x() * dpr), int(global_.y() * dpr)

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
        # Track the cursor. While picking a calibration point the live
        # guide line follows it; with a calibration done the hover readout
        # crosshair does. Repaint only when the position changes so the
        # guide does not shimmer on every mouse move.
        old = self._hover_pos
        self._hover_pos = event.position().toPoint()
        self._hover_active = self._calibration is not None
        active = self._hover_active or (
            self._session is not None and self._session.expecting_click
        )
        if active and self._hover_pos != old:
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self._hover_active:
            self._hover_active = False
            self.update()
        super().leaveEvent(event)

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
        self._schedule_geometry_save()

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
        if self._calibration is not None:
            self._paint_calibration_region(painter)
            self._paint_readout(painter)
        if self._session is not None:
            self._paint_calibration(painter)

    def _paint_calibration(self, painter):
        self._paint_anchors(painter)
        self._paint_live_guide(painter)
        self._paint_instruction(painter)

    def _paint_live_guide(self, painter):
        """Draw a guide line that follows the cursor while a point is
        being picked, in the current axis direction.

        This lets the user align the click with the graph's gridline: a
        vertical line while picking an X point, a horizontal one for Y.
        It fades away once a value is being typed, since the point is
        already placed.
        """
        if not self._session.expecting_click:
            return
        axis = self._session.current_axis
        color = _X_COLOR if axis == "x" else _Y_COLOR
        pen = QPen(color, 1)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        if axis == "x":
            painter.drawLine(
                QPoint(self._hover_pos.x(), TITLEBAR_HEIGHT),
                QPoint(self._hover_pos.x(), self.height()),
            )
        else:
            painter.drawLine(
                QPoint(0, self._hover_pos.y()),
                QPoint(self.width(), self._hover_pos.y()),
            )

    def _paint_anchors(self, painter):
        """Draw the placed anchors as a dot with a guide line in the axis
        direction.

        Each axis only cares about one coordinate: an X anchor marks the
        pixel's horizontal position, a Y anchor the vertical. Draw just
        the guide line along that axis (not a small cross) so the marker
        reads as a gridline crossing, not a cursor.
        """
        for axis, _index, px, py, value in self._session.anchors():
            local = self._local_from_physical(px, py)
            color = _X_COLOR if axis == "x" else _Y_COLOR
            x, y = local.x(), local.y()
            if axis == "x":
                painter.drawLine(
                    QPoint(x, TITLEBAR_HEIGHT), QPoint(x, self.height())
                )
            else:
                painter.drawLine(QPoint(0, y), QPoint(self.width(), y))
            painter.setPen(QPen(color, 2))
            painter.drawEllipse(local, 4, 4)
            if value is not None:
                self._draw_anchor_label(painter, local, color, str(value))

    def _draw_anchor_label(self, painter, local, color, text):
        """Draw an anchor's value beside its marker, translucent with a
        dark halo so it reads over whatever graph is beneath."""
        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        self._draw_outlined_text(
            painter,
            text,
            QPointF(local.x() + 10, local.y()),
            color,
            9,
            bold=True,
        )

    def _draw_outlined_text(self, painter, text, pos, color, size, bold):
        """Draw translucent text with a dark outline so it stays legible
        over any background without an opaque backing box.

        The graph shows through the semi-transparent glyphs, but the dark
        halo keeps the text readable on light or dark content.
        """
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        font = QFont()
        font.setPointSize(size)
        font.setBold(bold)
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        height = metrics.height()
        baseline = pos.y() + height / 2
        # Dark halo: draw the text offset in a ring around the glyph, then
        # the colored glyph on top. Offsets are symmetric on all four
        # sides so the outline reads evenly, not just left and right. This
        # reads as a soft outline, not a box, and stays legible on light
        # or dark content.
        halo_color = QColor(8, 8, 8, 220)
        painter.setPen(halo_color)
        for dx in (-2, -1, 0, 1, 2):
            for dy in (-2, -1, 0, 1, 2):
                if dx == 0 and dy == 0:
                    continue
                painter.drawText(QPointF(pos.x() + dx, baseline + dy), text)
        painter.setPen(color)
        painter.drawText(QPointF(pos.x(), baseline), text)
        painter.restore()

    def _paint_instruction(self, painter):
        """Draw the calibration prompt and hints as floating translucent
        text at the bottom of the window, with no backing box."""
        left = _EDGE + 8
        width = self.width() - left * 2
        top = self.height() - 96
        prompt = self._session.prompt()
        line = 0
        if self._session.active:
            title_color = QColor(255, 255, 255)
        else:
            title_color = QColor(140, 230, 150)
        self._draw_outlined_text(
            painter,
            prompt,
            QPointF(left, top + line * 20),
            title_color,
            11,
            bold=True,
        )
        line += 1
        if self._session.expecting_value:
            self._draw_value_input(painter, left, top + line * 20, width)
            line += 1
        if self._value_error:
            self._draw_outlined_text(
                painter,
                self._value_error,
                QPointF(left, top + line * 20),
                QColor(255, 130, 130),
                9,
                bold=False,
            )
            line += 1
        # Hint row, right-aligned.
        hint_text = (
            "Ctrl+Z undo  ·  Esc cancel"
            if self._session.active
            else "Ctrl+N redo  ·  Esc hide"
        )
        self._draw_outlined_text(
            painter,
            hint_text,
            QPointF(left + width - 220, top + line * 20),
            QColor(210, 210, 210),
            9,
            bold=False,
        )

    def _draw_value_input(self, painter, left, top, width):
        """Draw the typed value and a blinking caret on the input line."""
        self._draw_outlined_text(
            painter,
            self._value_text or " ",
            QPointF(left, top),
            QColor(255, 255, 255),
            11,
            bold=True,
        )
        if self._caret_visible:
            font = QFont()
            font.setPointSize(11)
            font.setBold(True)
            painter.setFont(font)
            metrics = QFontMetricsF(font)
            caret_x = left + metrics.horizontalAdvance(self._value_text) + 2
            baseline = top + metrics.height() / 2
            painter.setPen(QPen(QColor(255, 255, 255, 220), 2))
            painter.drawLine(
                QPointF(caret_x, baseline - 7),
                QPointF(caret_x, baseline + 7),
            )

    def _paint_calibration_region(self, painter):
        """Draw the calibrated screen region as a guide rectangle.

        The rectangle is anchored to absolute screen coordinates, not the
        window, so if the graph underneath is moved the box stays where it
        was calibrated and the misalignment is easy to spot. Drawn dashed
        like the calibration guides and in a green distinct from the axis
        hues, so it stands out against black gridlines.
        """
        left, top, right, bottom = self._calibration.region()
        p0 = self._local_from_physical(left, top)
        p1 = self._local_from_physical(right, bottom)
        rect = QRect(p0, p1)
        pen = QPen(_REGION_COLOR, 1)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawRect(rect)

    def _paint_readout(self, painter):
        """Draw the crosshair and (X, Y) readout at the hover position.

        The crosshair and readout only appear once a calibration exists.
        The values come from the mouse's physical screen position, so the
        readout is independent of where the overlay sits.
        """
        if not self._hover_active or self._session is not None:
            return
        px, py = self._physical_from_local(self._hover_pos)
        try:
            vx, vy = self._calibration.xy(px, py)
        except ValueError, ZeroDivisionError:
            return
        x_text = self._calibration.x.format(vx)
        y_text = self._calibration.y.format(vy)

        # Crosshair: two translucent lines through the cursor, snapped to
        # the graph pixel so the readout lines up with it. Drawn with a
        # dark underline so they read as a clear hairline over any content.
        x = self._hover_pos.x()
        y = self._hover_pos.y()
        for color, ox, oy in (
            (QColor(8, 8, 8, 160), 1, 0),
            (QColor(8, 8, 8, 160), -1, 0),
            (QColor(8, 8, 8, 160), 0, 1),
            (QColor(8, 8, 8, 160), 0, -1),
            (QColor(255, 255, 255, 110), 0, 0),
        ):
            painter.setPen(QPen(color, 1))
            painter.drawLine(QPoint(0, y + oy), QPoint(self.width(), y + oy))
            painter.drawLine(
                QPoint(x + ox, TITLEBAR_HEIGHT), QPoint(x + ox, self.height())
            )

        # Readout text near the cursor, offset below-right so it does not
        # cover the point being read.
        readout = f"({x_text}, {y_text})"
        self._draw_outlined_text(
            painter,
            readout,
            QPointF(x + 14, y + 14),
            QColor(255, 255, 255),
            11,
            bold=True,
        )
        if self._copy_notice:
            self._draw_outlined_text(
                painter,
                self._copy_notice,
                QPointF(x + 14, y + 34),
                QColor(140, 230, 150),
                9,
                bold=False,
            )

    def resizeEvent(self, event):
        self.title_bar.setGeometry(0, 0, self.width(), TITLEBAR_HEIGHT)
        self._schedule_geometry_save()
        super().resizeEvent(event)
