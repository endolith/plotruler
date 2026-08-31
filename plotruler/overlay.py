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
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QWidget

from . import storage, win_hittest
from .core import CalibrationSession
from .format import AUTO, NAMES, OPTIONS, is_valid
from .titlebar import TITLEBAR_HEIGHT, TitleBar

# Padding for text laid out at the window edges, in logical pixels.
_EDGE = 8

# Width of the invisible resize hit-zones along each border. Larger than
# the text padding so a cursor near the edge reliably grabs a resize grip
# rather than falling through to the graph underneath.
_RESIZE_ZONE = 14

# Calibration instruction block: margin between the last instruction row
# and the window bottom, and the vertical space between stacked rows. The
# block is bottom-aligned so the group reads pinned near the bottom; the
# row height is shared by painting and the mode-button hit-test so they
# never drift.
_INSTRUCTION_BOTTOM_MARGIN = 12
_INSTRUCTION_ROW_H = 26

# Font sizes, one consistent scale across the overlay. Headline text (the
# calibration prompt, the typed value, the hovered readout) is TEXT_LARGE;
# secondary labels (mode buttons, hints, errors, anchor labels) are
# TEXT_MEDIUM; tertiary captions (format indicator, transient notices) are
# TEXT_SMALL. Everything uses one of these so the type reads uniformly.
_TEXT_LARGE = 14
_TEXT_MEDIUM = 12
_TEXT_SMALL = 10

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

        # Tray availability decides how close/min/Esc behave. Windows always
        # has a notification area; some desktop screens (e.g. GNOME without
        # the AppIndicator extension) have no tray at all. Without one the
        # overlay has no way to be brought back, so hiding is a dead end.
        self._tray_available = QSystemTrayIcon.isSystemTrayAvailable()

        # On a no-tray system minimize would quit (no way to bring the
        # overlay back), so show only a close button, not a misleading
        # minimize. With a tray, show minimize + maximize as normal.
        self.title_bar = TitleBar(
            self,
            show_close=not self._tray_available,
            show_min=self._tray_available,
        )
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

        # Readout number format (auto/plain/scientific/engineering/e/si),
        # loaded from the config file; a transient "format changed" notice
        # is shown when the user switches it.
        self._num_format = AUTO
        self._format_notice = ""
        self._format_timer = QTimer(self)
        self._format_timer.setSingleShot(True)
        self._format_timer.setInterval(900)
        self._format_timer.timeout.connect(self._clear_format_notice)

        # Pixel step for arrow-key anchor nudging during calibration.
        self._nudge_step = 1

        # Tracks the manual maximize state; the window itself stays in a
        # normal window state so nothing conflicts with native snapping.
        self._maximized = False
        self._saved_geometry = None

        # Readout state: the last hovered cursor position (local logical),
        # and a transient "copied" banner that fades after a short delay.
        self._hover_pos = QPoint()
        self._hover_active = False
        self._hover_mode = None
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
        """Hide the overlay; the app stays resident in the tray.

        Without a system tray there is no way to bring the overlay back, so
        hiding would strand it unreachable; quit instead so the app does not
        linger invisibly.
        """
        if not self._tray_available:
            self.quit()
            return
        self.hide()

    def toggle_visibility(self):
        """Show the overlay if hidden, or hide it if visible."""
        if self.isVisible():
            # Save the exact on-screen rect before hiding. Qt's geometry()
            # returns the pre-snap "restore" bounds for a snapped window,
            # so we read the true displayed rect from Win32 instead. Stored
            # as physical (left, top, right, bottom).
            rect = win_hittest.window_rect(self)
            if rect is None:
                g = self.geometry()
                dpr = self.devicePixelRatioF()
                rect = (
                    int(g.x() * dpr),
                    int(g.y() * dpr),
                    int((g.x() + g.width()) * dpr),
                    int((g.y() + g.height()) * dpr),
                )
            self._pre_hide_geometry = rect
            self.hide()
        else:
            self.show()
            saved = getattr(self, "_pre_hide_geometry", None)
            if saved is not None:
                # Drop any maximized state so the rect is honored. Using
                # SetWindowPlacement (not setGeometry) is essential: Windows
                # otherwise re-applies a snapped window's stored restore
                # position and overrides the move.
                self.setWindowState(Qt.WindowState.WindowNoState)
                win_hittest.set_window_rect(self, saved)
                self._pre_hide_geometry = None
            self._maximized = self.isMaximized()
            self.raise_()
            self.activateWindow()

    def closeEvent(self, event):
        # There is no close button; a WM_CLOSE (e.g. Alt+F4) should hide the
        # overlay to the tray rather than end the app. Quitting is explicit,
        # from the tray menu. Ignoring the event cancels the close. Without a
        # tray there is nothing to hide to, so let the close proceed.
        if not self._tray_available:
            event.accept()
            return
        event.ignore()
        self.hide()

    def quit(self):
        """End the app outright, bypassing the hide-to-tray close path.

        Geometry saves are debounced, so flush the pending one before the
        event loop stops or the last move/resize would be lost on quit.
        """
        if self._geometry_timer.isActive():
            self._geometry_timer.stop()
            self._save_geometry()
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
        saved_format = storage.num_format(self._config_path)
        if saved_format is not None:
            self._num_format = saved_format

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
        self._hover_mode = None
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
        # Readout mode: nothing is being calibrated. Arrow keys nudge the
        # crosshair to an exact point, and Ctrl+C copies its coordinate,
        # so a reading can be placed precisely without the mouse.
        if self._calibration is not None:
            if (
                event.key() == Qt.Key.Key_C
                and event.modifiers() & Qt.KeyboardModifier.ControlModifier
            ):
                self._copy_readout()
                event.accept()
                return
            nudge = self._crosshair_nudge(event.key())
            if nudge is not None:
                self._nudge_crosshair(*nudge)
                event.accept()
                return
        if event.key() == Qt.Key.Key_Escape:
            self.minimize_to_tray()
            event.accept()
            return
        # Number keys switch the readout format when not calibrating, so
        # the user can flip between plain, scientific, etc. without a menu.
        idx = self._format_key_index(event.key())
        if idx is not None:
            self.set_num_format(OPTIONS[idx])
            event.accept()
            return
        super().keyPressEvent(event)

    def _format_key_index(self, key):
        """Map a number-key to an index into OPTIONS, or None.

        Keys 1..6 (and the numpad equivalents) select the format by the
        same number shown in the tray menu, so the menu and the keyboard
        always agree.
        """
        mapping = {
            Qt.Key.Key_1: 0,
            Qt.Key.Key_2: 1,
            Qt.Key.Key_3: 2,
            Qt.Key.Key_4: 3,
            Qt.Key.Key_5: 4,
            Qt.Key.Key_6: 5,
        }
        return mapping.get(key)

    def _format_number(self, fmt):
        """Return the number-key that selects the given format (1-based)."""
        try:
            return str(OPTIONS.index(fmt) + 1)
        except ValueError:
            return "?"

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
        # Arrow keys nudge the just-placed anchor, so an off-by-one click
        # can be fine-tuned before its value is typed. Physical pixel
        # nudges: one px per keypress. Left/right move along the current
        # axis only, so an X anchor stops at the right place and a Y anchor
        # at the right height. Only meaningful while awaiting a value.
        nudge = self._arrow_nudge(event.key())
        if nudge is not None and self._session.nudge_point(*nudge):
            self.update()
            return
        if self._session.expecting_value:
            text = event.text()
            if text and all(c in _VALID_CHARS for c in text):
                if len(self._value_text) < 24:
                    self._value_text += text
                    self._value_error = None
                    self.update()

    def _arrow_nudge(self, key):
        """Return the (dx, dy) pixel nudge for an arrow key, or None.

        Only the axis being calibrated moves: an X anchor responds to
        left/right, a Y anchor to up/down. Perpendicular arrows do nothing
        rather than shift a marker off the guided line.
        """
        axis = self._session.current_axis
        d = self._nudge_step
        if axis == "x":
            if key == Qt.Key.Key_Left:
                return -d, 0
            if key == Qt.Key.Key_Right:
                return d, 0
            return None
        if axis == "y":
            if key == Qt.Key.Key_Up:
                return 0, -d
            if key == Qt.Key.Key_Down:
                return 0, d
            return None
        return None

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
        self._maybe_finish_calibration()
        self.update()

    def _maybe_finish_calibration(self):
        """Promote the session's calibration to the active one, if complete.

        The session is only a scaffold for collecting anchors; once a
        Calibration exists (every axis has its values and a scale mode), we
        switch to readout mode. Keeping the session around would suppress
        the hover readout, so drop it.
        """
        calibration = self._session.calibration()
        if calibration is not None:
            self._calibration = calibration
            self._session = None
            self._blink_timer.stop()
            self._save_calibration()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        if not win_hittest._IS_WINDOWS:
            # On X11 there is no WM_NCHITTEST to start a native resize, so
            # ask Qt for one when the press lands in an edge zone. Windows
            # keeps the Win32 shim and never reaches this point for edges.
            edges = self._resize_edges(event.position().toPoint())
            if edges is not None:
                self.windowHandle().startSystemResize(edges)
                event.accept()
                return
        if self._session is not None and self._session.expecting_mode:
            # Choose linear/log for the current axis by clicking a button.
            self._choose_mode(event.position())
            event.accept()
            return
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
        except (ValueError, ZeroDivisionError):
            return
        x_str = self._calibration.x.format(vx, fmt=self._num_format)
        y_str = self._calibration.y.format(vy, fmt=self._num_format)
        text = f"{x_str}, {y_str}"
        QApplication.clipboard().setText(text)
        self._copy_notice = "Copied " + text
        self._copy_timer.start()
        self.update()

    def _clear_copy_notice(self):
        self._copy_notice = ""
        self.update()

    def _crosshair_nudge(self, key):
        """Return the (dx, dy) pixel nudge for an arrow key, or None."""
        d = self._nudge_step
        if key == Qt.Key.Key_Left:
            return -d, 0
        if key == Qt.Key.Key_Right:
            return d, 0
        if key == Qt.Key.Key_Up:
            return 0, -d
        if key == Qt.Key.Key_Down:
            return 0, d
        return None

    def _nudge_crosshair(self, dx, dy):
        """Move the readout crosshair by (dx, dy) logical pixels.

        The crosshair normally follows the mouse; once nudged it holds a
        fixed offset from the cursor so a precise coordinate can be read and
        copied. The readout recomputes from the new position.
        """
        self._hover_pos += QPoint(dx, dy)
        self._hover_active = True
        self.update()

    def set_num_format(self, fmt):
        """Switch the readout number format, showing a brief confirmation.

        The change is displayed for a moment via _format_notice and saved
        to the config file so it survives a restart.
        """
        if not is_valid(fmt) or fmt == self._num_format:
            return
        self._num_format = fmt
        self._format_notice = "Number format: " + NAMES[fmt]
        self._format_timer.start()
        self._save_num_format()
        self.update()

    def _clear_format_notice(self):
        self._format_notice = ""
        self.update()

    def _save_num_format(self):
        storage.save(self._config_path, num_format=self._num_format)

    def _record_click(self, event):
        """Store the clicked point in physical screen pixels."""
        pos = event.globalPosition()
        dpr = self.devicePixelRatioF()
        self._session.record_point(int(pos.x() * dpr), int(pos.y() * dpr))

    def _choose_mode(self, pos):
        """Record the linear/log choice from a click on a mode button."""
        # The mode buttons sit one 20px row below the prompt. Reuse the
        # layout from _paint_instruction so click targets match the
        # drawn buttons.
        rects = self._mode_option_rects(self._mode_buttons_top())
        for name, rect in rects.items():
            if rect.contains(pos.toPoint()):
                self._session.record_mode(name)
                self._hover_mode = None
                self._maybe_finish_calibration()
                self.update()
                return

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
        if x < _RESIZE_ZONE and y < _RESIZE_ZONE:
            return win_hittest.HTTOPLEFT
        if x >= w - _RESIZE_ZONE and y < _RESIZE_ZONE:
            return win_hittest.HTTOPRIGHT
        if x < _RESIZE_ZONE and y >= h - _RESIZE_ZONE:
            return win_hittest.HTBOTTOMLEFT
        if x >= w - _RESIZE_ZONE and y >= h - _RESIZE_ZONE:
            return win_hittest.HTBOTTOMRIGHT
        if y < _RESIZE_ZONE:
            return win_hittest.HTTOP
        if y >= h - _RESIZE_ZONE:
            return win_hittest.HTBOTTOM
        if x < _RESIZE_ZONE:
            return win_hittest.HTLEFT
        if x >= w - _RESIZE_ZONE:
            return win_hittest.HTRIGHT
        if y < TITLEBAR_HEIGHT:
            if self.title_bar.is_over_buttons(local):
                return win_hittest.HTCLIENT
            return win_hittest.HTCAPTION
        return win_hittest.HTCLIENT

    def _resize_edges(self, local):
        """Return the Qt.Edges to resize for a local point, or None.

        Used on non-Windows, where a frameless window has no WM_NCHITTEST to
        hand edge drags to the OS. Mirrors hit_test_code's edge zones so
        clicking-and-dragging a border resizes the overlay instead of being
        treated as a click on the graph. Corners combine two edges. The top
        strip is the TitleBar's and is handled there as a move/resize.
        """
        w, h = self.width(), self.height()
        x, y = local.x(), local.y()
        if not self.rect().contains(local) or y < TITLEBAR_HEIGHT:
            return None
        edges = Qt.Edges()
        if x < _RESIZE_ZONE:
            edges |= Qt.Edge.LeftEdge
        elif x >= w - _RESIZE_ZONE:
            edges |= Qt.Edge.RightEdge
        if y >= h - _RESIZE_ZONE:
            edges |= Qt.Edge.BottomEdge
        return edges or None

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
        # Track which mode button is under the cursor so it can brighten.
        mode_hover = None
        if self._session is not None and self._session.expecting_mode:
            for name, rect in self._mode_option_rects(
                self._mode_buttons_top()
            ).items():
                if rect.contains(self._hover_pos):
                    mode_hover = name
                    break
        active = self._hover_active or (
            self._session is not None and self._session.expecting_click
        )
        if (active and self._hover_pos != old) or (
            mode_hover != self._hover_mode
        ):
            self._hover_mode = mode_hover
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self._hover_active:
            self._hover_active = False
            self.update()
        if self._hover_mode:
            self._hover_mode = None
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
        else:
            # No calibration in progress: still show the keyboard hint so the
            # user knows Ctrl+N can start one (only while focused). Position
            # its vertical center a small margin above the window bottom so
            # the text is clearly inside the window, not flush with it.
            self._paint_hint(
                painter,
                self.height() - _INSTRUCTION_BOTTOM_MARGIN - 12,
            )

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
            _TEXT_MEDIUM,
            bold=True,
        )

    def _draw_outlined_text(
        self,
        painter,
        text,
        pos,
        color,
        size,
        bold,
        centered=False,
        right_aligned=False,
    ):
        """Draw translucent text with a dark outline so it stays legible
        over any background without an opaque backing box.

        The graph shows through the semi-transparent glyphs, but the dark
        halo keeps the text readable on light or dark content.

        When centered is True the text is centered on pos.x(), and when
        right_aligned is True its right edge sits at pos.x(); either way it
        can be anchored inside a button or pinned to an edge.
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
        x = pos.x()
        if centered:
            x -= metrics.horizontalAdvance(text) / 2
        elif right_aligned:
            x -= metrics.horizontalAdvance(text)
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
                painter.drawText(QPointF(x + dx, baseline + dy), text)
        painter.setPen(color)
        painter.drawText(QPointF(x, baseline), text)
        painter.restore()

    def _mode_option_rects(self, row_top):
        """Return the linear/log button rectangles for the given row top.

        Two rounded translucent buttons sit side by side below the prompt
        while the session is asking for a linear/log choice. The geometry
        is computed here and shared by painting and hit-testing so the
        drawn buttons and the click targets always agree.
        """
        button_w = 96
        button_h = 28
        gap = 16
        left = _EDGE + 8
        width = self.width() - left * 2
        start_x = left + (width - (button_w * 2 + gap)) // 2
        return {
            "lin": QRect(start_x, row_top, button_w, button_h),
            "log": QRect(
                start_x + button_w + gap, row_top, button_w, button_h
            ),
        }

    def _mode_buttons_top(self):
        """The y of the mode-button row during the linear/log choice.

        During a mode choice the block is just the prompt plus the buttons
        (the value-input and error rows are never shown), so it is
        bottom-aligned as two rows; the buttons occupy the second row.
        This matches the painting in _paint_instruction so the click
        targets and the drawn buttons agree.
        """
        return (
            self.height()
            - _INSTRUCTION_BOTTOM_MARGIN
            - 2 * _INSTRUCTION_ROW_H
            + _INSTRUCTION_ROW_H
        )

    def _paint_instruction(self, painter):
        """Draw the calibration prompt and hints as floating translucent
        text pinned low in the window, with no backing box.

        The rows read in order from the instruction down: prompt, then the
        value input (or mode buttons, or error). The block is placed so its
        last row sits a margin above the bottom edge, keeping the whole
        instruction group near the bottom without any row clipping.
        """
        left = _EDGE + 8
        width = self.width() - left * 2
        prompt = self._session.prompt()
        if self._session.active:
            title_color = QColor(255, 255, 255)
        else:
            title_color = QColor(140, 230, 150)

        # Count the rows that will be drawn so the block can be placed
        # bottom-aligned: prompt always, then the conditional rows.
        rows = 1
        if self._session.expecting_value:
            rows += 1  # value input
            rows += 1  # arrow-nudge note
        if self._session.expecting_mode:
            rows += 1
        if self._value_error:
            rows += 1
        top = (
            self.height()
            - _INSTRUCTION_BOTTOM_MARGIN
            - rows * _INSTRUCTION_ROW_H
        )

        # Prompt on the left and the keyboard hint on the right, on the same
        # baseline so the instruction block reads as one row.
        self._draw_outlined_text(
            painter,
            prompt,
            QPointF(left, top),
            title_color,
            _TEXT_LARGE,
            bold=True,
        )
        self._paint_hint(painter, top)

        # Interactive rows below the prompt, most recent nearest it.
        row_y = top + _INSTRUCTION_ROW_H
        if self._session.expecting_value:
            self._draw_value_input(painter, left, row_y, width)
            row_y += _INSTRUCTION_ROW_H
            # Offer the arrow-key nudge as a hint under the input, so the
            # user knows an off-by-one click can be fine-tuned first. Each
            # anchor is a line along its axis, so only motions along that
            # axis move it. Like all keyboard instructions it is hidden when
            # the window is not focused.
            if self.hasFocus():
                axis = self._session.current_axis
                direction = "left/right" if axis == "x" else "up/down"
                self._draw_outlined_text(
                    painter,
                    f"{direction} arrows: nudge the line",
                    QPointF(left, row_y),
                    QColor(220, 220, 220),
                    _TEXT_MEDIUM,
                    bold=True,
                )
            row_y += _INSTRUCTION_ROW_H
        if self._session.expecting_mode:
            self._draw_mode_buttons(painter, row_y)
            row_y += _INSTRUCTION_ROW_H
        if self._value_error:
            self._draw_outlined_text(
                painter,
                self._value_error,
                QPointF(left, row_y),
                QColor(255, 130, 130),
                _TEXT_MEDIUM,
                bold=True,
            )

    def _paint_hint(self, painter, row_top):
        """Draw the keyboard-shortcut hint at the bottom-right of the window.

        Shown only while the overlay is focused: the shortcuts (and their
        reminders) only apply then. Ctrl+N works at any time, so it always
        appears; Ctrl+Z (undo) only makes sense mid-calibration.

        The hint shares the baseline of the prompt row so the calibration
        block reads as one line; outside calibration it is drawn on its own
        bottom row via _paint_idle_hint.
        """
        if not self.hasFocus():
            return
        parts = []
        if self._session is not None and self._session.anchors():
            # Ctrl+Z only has something to revert once at least one point
            # has been clicked.
            parts.append("Ctrl+Z undo")
        if self._session is None or self._session.active:
            parts.append("Ctrl+N new")
        if self._session is None:
            parts.append("Esc hide")
            if self._calibration is not None:
                parts.append("arrows nudge")
                parts.append("Ctrl+C copy")
        else:
            parts.append("Esc cancel")
        text = "  ·  ".join(parts) if parts else "Ctrl+N new"
        # Right-align the text so its right edge sits a small margin from
        # the window's right edge, instead of a hard-coded offset that can
        # drift off-window as the string grows.
        self._draw_outlined_text(
            painter,
            text,
            QPointF(self.width() - (_EDGE + 8), row_top),
            QColor(235, 235, 235),
            _TEXT_LARGE,
            bold=True,
            right_aligned=True,
        )

    def _draw_value_input(self, painter, left, top, width):
        """Draw the typed value and a blinking caret on the input line."""
        self._draw_outlined_text(
            painter,
            self._value_text or " ",
            QPointF(left, top),
            QColor(255, 255, 255),
            _TEXT_LARGE,
            bold=True,
        )
        if self._caret_visible:
            font = QFont()
            font.setPointSize(_TEXT_LARGE)
            font.setBold(True)
            painter.setFont(font)
            metrics = QFontMetricsF(font)
            caret_x = left + metrics.horizontalAdvance(self._value_text) + 2
            baseline = top + metrics.height() / 2
            painter.setPen(QPen(QColor(255, 255, 255, 220), 2))
            painter.drawLine(
                QPointF(caret_x, baseline - 9),
                QPointF(caret_x, baseline + 9),
            )

    def _draw_mode_buttons(self, painter, row_top):
        """Draw the linear/log choice buttons for the current axis."""
        rects = self._mode_option_rects(row_top)
        self._draw_mode_button(painter, rects["lin"], "Linear", "lin")
        self._draw_mode_button(painter, rects["log"], "Log", "log")

    def _draw_mode_button(self, painter, rect, label, name):
        """Draw one mode button as a translucent rounded rect with a dark
        halo outline and a faint fill that brightens when hovered, so the
        graph shows through and it reads as a button rather than a box.

        The halo is drawn in the halo color around the label so the text
        stays legible over any content; the label itself is colored by the
        axis hue so the choice feels tied to the axis being scaled.
        """
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        hovered = self._hover_mode == name
        # A faint fill so the button has a tangible extent over a busy
        # graph, using the axis hue but heavily faded so it stays
        # translucent and does not obscure what is behind it.
        axis = self._session.current_axis
        base = _X_COLOR if axis == "x" else _Y_COLOR
        fill = QColor(
            base.red(), base.green(), base.blue(), 60 if not hovered else 110
        )
        outline = QColor(
            base.red(), base.green(), base.blue(), 200 if hovered else 140
        )
        painter.setPen(QPen(outline, 1))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, 6, 6)
        painter.restore()
        self._draw_outlined_text(
            painter,
            label,
            QPointF(rect.center().x(), rect.center().y()),
            QColor(240, 240, 240),
            _TEXT_MEDIUM,
            bold=True,
            centered=True,
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
        except (ValueError, ZeroDivisionError):
            return
        x_text = self._calibration.x.format(vx, fmt=self._num_format)
        y_text = self._calibration.y.format(vy, fmt=self._num_format)

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
            _TEXT_LARGE,
            bold=True,
        )
        # A small indicator showing the active number format and the number
        # key that selects it, plus any transient format-change notice. This
        # keeps the user aware of which format is shown since some formats
        # (plain vs scientific for a rounded value) can look alike.
        info = self._format_notice or (
            "Format "
            + self._format_number(self._num_format)
            + " ("
            + NAMES[self._num_format]
            + ")"
        )
        self._draw_outlined_text(
            painter,
            info,
            QPointF(x + 14, y + 40),
            QColor(220, 220, 220),
            _TEXT_SMALL,
            bold=True,
        )
        if self._copy_notice:
            self._draw_outlined_text(
                painter,
                self._copy_notice,
                QPointF(x + 14, y + 64),
                QColor(150, 235, 160),
                _TEXT_SMALL,
                bold=True,
            )

    def resizeEvent(self, event):
        self.title_bar.setGeometry(0, 0, self.width(), TITLEBAR_HEIGHT)
        self._schedule_geometry_save()
        super().resizeEvent(event)

    def focusInEvent(self, event):
        # The keyboard-hint line only shows while the overlay is focused;
        # repaint on focus so it appears and is correct.
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        # Remove the keyboard hint when focus leaves; the shortcuts (and
        # their on-screen reminders) only apply while focused.
        self.update()
        super().focusOutEvent(event)
