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

MOD_BY_NAME = {
    "win": MOD_WIN,
    "alt": MOD_ALT,
    "ctrl": MOD_CONTROL,
    "shift": MOD_SHIFT,
}
MOD_NAME_BY_BIT = {bit: name for name, bit in MOD_BY_NAME.items()}

WM_HOTKEY = 0x0312

# Default summon key: Win+Alt+P (P for PlotRuler). Unclaimed on stock
# Windows; the only known collision is PowerToys' optional mouse-pointer
# crosshairs, which users can remap here.
DEFAULT_VK = 0x50  # 'P'
DEFAULT_MODIFIERS = MOD_WIN | MOD_ALT


class KeyCombo:
    """A single key plus its modifiers, in an OS-agnostic form.

    Modifiers are stored as a frozenset of names ("win", "alt", "ctrl",
    "shift") so they serialize as a stable ordered list. The key is a
    human name ("P", "F1", "Space") plus its Win32 virtual-key code. The
    overlay and settings dialog build these; the Win32 GlobalHotkey turns
    one into a RegisterHotKey call.
    """

    def __init__(self, modifiers, key_name, vk):
        self.modifiers = frozenset(modifiers)
        self.key_name = key_name
        self.vk = int(vk)

    def text(self):
        """Return a human-readable form, e.g. 'Win+Alt+P'."""
        order = ("win", "alt", "ctrl", "shift")
        parts = [name.title() for name in order if name in self.modifiers]
        parts.append(self.key_name)
        return "+".join(parts)

    def win32_modifiers(self):
        """Return the Win32 modifier bitmask for this combo."""
        mask = 0
        for name in self.modifiers:
            mask |= MOD_BY_NAME.get(name, 0)
        return mask

    def to_dict(self):
        """Return a storage-safe dict for this combo."""
        order = ("win", "alt", "ctrl", "shift")
        mods = [name for name in order if name in self.modifiers]
        return {"modifiers": mods, "key": self.key_name, "vk": self.vk}

    def __eq__(self, other):
        return (
            isinstance(other, KeyCombo)
            and self.modifiers == other.modifiers
            and self.key_name == other.key_name
            and self.vk == other.vk
        )

    def __hash__(self):
        return hash((tuple(sorted(self.modifiers)), self.key_name, self.vk))

    def __repr__(self):
        return f"KeyCombo({self.text()})"


DEFAULT_COMBO = KeyCombo(("win", "alt"), "P", DEFAULT_VK)


def combo_from_dict(data):
    """Build a KeyCombo from a dict, or None if it is malformed."""
    if not isinstance(data, dict):
        return None
    try:
        modifiers = data["modifiers"]
        key_name = str(data["key"])
        vk = int(data["vk"])
    except KeyError, TypeError, ValueError:
        return None
    clean = [name for name in modifiers if name in MOD_BY_NAME]
    if not clean or not key_name:
        return None
    return KeyCombo(clean, key_name, vk)


def qkey_to_vk(qt_key):
    """Convert a Qt.Key alias to a Win32 virtual-key code.

    For letters and digits Qt already uses the VK code, but function and
    other special keys use a Qt-specific value that must be mapped. F1-F12
    are contiguous in Qt (0x01000030..0x0100003B) and in Win32
    (0x70..0x7B), so they can be computed; the rest come from a table.
    """
    # Qt.Key.F1 = 0x01000030 == VK_F1 = 0x70, and both run contiguously.
    if 0x01000030 <= qt_key <= 0x0100003B:
        return 0x70 + (qt_key - 0x01000030)
    special = {
        0x01000006: 0x2D,  # Insert
        0x01000007: 0x2E,  # Delete
        0x01000010: 0x24,  # Home
        0x01000011: 0x23,  # End
        0x01000012: 0x25,  # Left
        0x01000013: 0x26,  # Up
        0x01000014: 0x27,  # Right
        0x01000015: 0x28,  # Down
        0x01000016: 0x21,  # Page Up
        0x01000017: 0x22,  # Page Down
        0x01000020: 0x2C,  # PrintScreen
        0x20: 0x20,  # Space (VK is 0x20, same as Qt)
    }
    if qt_key in special:
        return special[qt_key]
    # Qt reserves 0x01000000-0x0100FFFF for special keys; below that an
    # ASCII/ANSI key's value is already the VK code.
    if 0x01000000 <= qt_key <= 0x0100FFFF:
        return 0
    return qt_key


def qmodifiers_to_names(qt_modifiers):
    """Convert a Qt.KeyboardModifier bitmask to modifier names."""
    names = []
    # The Windows key appears to Qt as the Meta modifier.
    if qt_modifiers & 0x00000008:
        names.append("win")
    if qt_modifiers & 0x00000004:
        names.append("alt")
    if qt_modifiers & 0x00000002:
        names.append("ctrl")
    if qt_modifiers & 0x00000001:
        names.append("shift")
    return names


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
