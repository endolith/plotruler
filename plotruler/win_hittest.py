"""Win32 shim that gives the frameless overlay native window behavior.

A frameless window has no native frame, so Windows refuses to move,
resize, or snap it, and external tools like GridMove cannot grab it.
This module answers WM_NCHITTEST so the OS treats our custom title bar
as a real caption (drag + Aero Snap) and our edges as real borders
(native resize with the standard cursors). It also enforces the window's
minimum size during native resizes via WM_GETMINMAXINFO.

Windows-only. On other platforms every function is a no-op.
"""

import ctypes

try:
    from ctypes import wintypes
except ImportError, OSError:
    wintypes = None

from PySide6.QtCore import QPoint

WM_NCHITTEST = 0x0084
WM_NCLBUTTONDBLCLK = 0x00A3
WM_GETMINMAXINFO = 0x0024

HTCLIENT = 1
HTCAPTION = 2
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17


class MINMAXINFO(ctypes.Structure):
    _fields_ = [
        ("ptReserved", wintypes.POINT),
        ("ptMaxSize", wintypes.POINT),
        ("ptMaxPosition", wintypes.POINT),
        ("ptMinTrackSize", wintypes.POINT),
        ("ptMaxTrackSize", wintypes.POINT),
    ]


def _local_point(window, lparam):
    """Convert a WM_* cursor lParam to the window's local coordinates."""
    x = ctypes.c_short(lparam & 0xFFFF).value
    y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
    # lParam is in physical screen pixels; Qt geometry is logical, so
    # scale down before mapping into the widget.
    dpr = window.devicePixelRatioF()
    logical = QPoint(int(x / dpr), int(y / dpr))
    return window.mapFromGlobal(logical)


def handle_native_event(window, event_type, message):
    """Route a native event to its handler; returns (handled, result)."""
    if wintypes is None or event_type != b"windows_generic_MSG":
        return False, 0
    try:
        msg = wintypes.MSG.from_address(int(message))
    except TypeError, ValueError:
        return False, 0
    if msg.message == WM_NCHITTEST:
        code = window.hit_test_code(_local_point(window, msg.lParam))
        return True, code
    if msg.message == WM_NCLBUTTONDBLCLK:
        # The default is the system menu; we want maximize/restore like a
        # real title bar.
        if window.hit_test_code(_local_point(window, msg.lParam)) == HTCAPTION:
            window.toggle_maximize()
        return True, 0
    if msg.message == WM_GETMINMAXINFO:
        _set_min_track(window, msg.lParam)
        return True, 0
    return False, 0


def _set_min_track(window, lparam):
    """Enforce the window's minimum size during native resizes."""
    if not lparam:
        return
    mmi = MINMAXINFO.from_address(int(lparam))
    dpr = window.devicePixelRatioF()
    mmi.ptMinTrackSize.x = int(window.minimumWidth() * dpr)
    mmi.ptMinTrackSize.y = int(window.minimumHeight() * dpr)
