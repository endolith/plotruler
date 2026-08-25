"""Win32 shim that gives the frameless overlay native window behavior.

A frameless window has no native frame, so Windows refuses to move,
resize, or snap it, and external tools like GridMove cannot grab it. On
its own, answering WM_NCHITTEST with HTCAPTION gives dragging but not
snapping, because Qt's FramelessWindowHint creates the window as
WS_POPUP and the OS will not run its modal move loop for such a window.

The fix has three parts, all in this module:

1. Give the window the native overlapped-window style bits (WS_CAPTION,
   WS_THICKFRAME, WS_MAXIMIZEBOX, ...) so Windows treats it as an
   ordinary application window. This is what makes it snappable.
2. Hide the actual frame by answering WM_NCCALCSIZE and collapsing the
   non-client area, so the native title bar and borders are never drawn.
3. Answer WM_NCHITTEST so the custom title bar behaves as a caption and
   the edges resize natively, and WM_GETMINMAXINFO so the window's
   minimum size is respected and maximizing fills the work area exactly.

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
WM_NCCALCSIZE = 0x0083
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

GWL_STYLE = -16
WS_POPUP = 0x80000000
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_SYSMENU = 0x00080000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_OVERLAPPEDWINDOW = (
    WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX
)

SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020


class MINMAXINFO(ctypes.Structure):
    _fields_ = [
        ("ptReserved", wintypes.POINT),
        ("ptMaxSize", wintypes.POINT),
        ("ptMaxPosition", wintypes.POINT),
        ("ptMinTrackSize", wintypes.POINT),
        ("ptMaxTrackSize", wintypes.POINT),
    ]


class NCCALCSIZE_PARAMS(ctypes.Structure):
    _fields_ = [
        ("rgrc", wintypes.RECT * 3),
        ("lppos", ctypes.c_void_p),
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


def apply_native_overlapped_style(window):
    """Give the window real overlapped-window styles for snapping.

    Qt's FramelessWindowHint produces WS_POPUP, which throws away the
    shell behavior attached to the frame styles (snapping, taskbar
    interaction, the move loop). Replace WS_POPUP with the standard
    overlapped-window styles. The frame is never drawn because
    WM_NCCALCSIZE collapses it.
    """
    if wintypes is None:
        return
    hwnd = int(window.winId())
    user32 = ctypes.windll.user32
    style = user32.GetWindowLongW(hwnd, GWL_STYLE) & 0xFFFFFFFF
    style = (style & ~WS_POPUP) | WS_OVERLAPPEDWINDOW
    style &= 0xFFFFFFFF
    # Win32 styles are signed 32-bit; convert before calling back.
    if style >= 0x80000000:
        style -= 0x100000000
    user32.SetWindowLongW(hwnd, GWL_STYLE, style)
    # Asking for a frame recalculation makes Windows re-query the frame
    # (WM_NCCALCSIZE) so the collapsed client rect takes effect at once.
    user32.SetWindowPos(
        hwnd,
        None,
        0,
        0,
        0,
        0,
        SWP_FRAMECHANGED
        | SWP_NOMOVE
        | SWP_NOSIZE
        | SWP_NOZORDER
        | SWP_NOACTIVATE,
    )


def disable_window_animations(window):
    """Turn off this window's transition animations.

    Windows plays a slide-then-expand animation when maximizing. On a
    translucent frameless overlay that reads as a flash toward the
    top-left corner before the window fills the screen, so suppress the
    transitions for this window.
    """
    if wintypes is None:
        return
    try:
        dwmapi = ctypes.windll.dwmapi
        DWMWA_TRANSITIONS_FORCEDISABLED = 3
        value = ctypes.c_int(1)
        dwmapi.DwmSetWindowAttribute(
            int(window.winId()),
            DWMWA_TRANSITIONS_FORCEDISABLED,
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
    except Exception:
        # The attribute is optional; some configurations reject it and
        # that is fine — the flash is cosmetic.
        pass


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
    if msg.message == WM_NCCALCSIZE:
        # Collapse the non-client area so no native frame is drawn.
        _collapse_frame(msg)
        return True, 0
    if msg.message == WM_GETMINMAXINFO:
        _set_min_max_info(window, msg.lParam)
        return True, 0
    return False, 0


def _collapse_frame(msg):
    """Make the client area fill the whole window (no native frame)."""
    if not msg.lParam:
        return
    if msg.wParam:
        params = NCCALCSIZE_PARAMS.from_address(int(msg.lParam))
        window_rect = params.rgrc[1]
        # The proposed client rect (rgrc[0]) becomes the window rect.
        params.rgrc[0].left = window_rect.left
        params.rgrc[0].top = window_rect.top
        params.rgrc[0].right = window_rect.right
        params.rgrc[0].bottom = window_rect.bottom


def _set_min_max_info(window, lparam):
    """Enforce minimum size and a maximized size that fills the work area."""
    if not lparam:
        return
    mmi = MINMAXINFO.from_address(int(lparam))
    dpr = window.devicePixelRatioF()
    mmi.ptMinTrackSize.x = int(window.minimumWidth() * dpr)
    mmi.ptMinTrackSize.y = int(window.minimumHeight() * dpr)
    # With the frame collapsed, a normal maximized window would overhang
    # the screen by the frame width. Pin the maximized size to the work
    # area so maximize and snap fill it exactly.
    work = window.screen().availableGeometry()
    mmi.ptMaxSize.x = int(work.width() * dpr)
    mmi.ptMaxSize.y = int(work.height() * dpr)
    mmi.ptMaxPosition.x = int(work.x() * dpr)
    mmi.ptMaxPosition.y = int(work.y() * dpr)
