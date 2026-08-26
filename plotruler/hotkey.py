"""Global hotkey support via the Win32 RegisterHotKey API.

A tray-resident overlay needs a system-wide key to summon and dismiss it
without the window having focus. On Windows this is RegisterHotKey, which
posts a WM_HOTKEY message to the thread that registered it. Qt's event
loop delivers that message to a QAbstractNativeEventFilter, which is how
we receive it regardless of which window is focused.

The key combination is configurable, not hard-coded, so users can avoid
collisions with other software (the default is Win+Alt+P for PlotRuler).

Windows-only. On other platforms registration is a no-op.
"""

import ctypes

try:
    from ctypes import wintypes
except ImportError, OSError:
    wintypes = None

from PySide6.QtCore import QAbstractNativeEventFilter

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

WM_HOTKEY = 0x0312

# Default summon key: Win+Alt+P (P for PlotRuler). Unclaimed on stock
# Windows; the only known collision is PowerToys' optional mouse-pointer
# crosshairs, which users can remap here.
DEFAULT_VK = 0x50  # 'P'
DEFAULT_MODIFIERS = MOD_WIN | MOD_ALT


class GlobalHotkey(QAbstractNativeEventFilter):
    """Registers one global hotkey and calls a callback when pressed.

    The callback is invoked on the Qt main thread from within the native
    event filter, so it is safe to manipulate widgets directly.
    """

    def __init__(
        self, key=DEFAULT_VK, modifiers=DEFAULT_MODIFIERS, callback=None
    ):
        super().__init__()
        self._key = key
        self._modifiers = modifiers
        self._callback = callback
        self._hotkey_id = 0xBEEF
        self._registered = False

    def register(self):
        """Register the hotkey; returns True on success."""
        if wintypes is None:
            return False
        if self._registered:
            return True
        result = ctypes.windll.user32.RegisterHotKey(
            None, self._hotkey_id, self._modifiers, self._key
        )
        self._registered = bool(result)
        return self._registered

    def unregister(self):
        """Remove the hotkey if it was registered."""
        if self._registered and wintypes is not None:
            ctypes.windll.user32.UnregisterHotKey(None, self._hotkey_id)
            self._registered = False

    def set_callback(self, callback):
        self._callback = callback

    def nativeEventFilter(self, event_type, message):
        if wintypes is None or event_type != b"windows_generic_MSG":
            return False, 0
        try:
            msg = wintypes.MSG.from_address(int(message))
        except TypeError, ValueError:
            return False, 0
        if msg.message == WM_HOTKEY and msg.wParam == self._hotkey_id:
            if self._callback is not None:
                self._callback()
            return True, 0
        return False, 0
