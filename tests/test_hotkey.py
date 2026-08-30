"""Tests for plotruler.hotkey — the key-combo model and conversions."""

from plotruler import hotkey
from plotruler.hotkey import KeyCombo, combo_from_dict


def test_default_combo_format():
    """The default Win+Alt+P combo must read back as that string."""
    assert hotkey.DEFAULT_COMBO.text() == "Win+Alt+P"


def test_combo_round_trips_through_dict():
    """A combo must survive a dict round-trip unchanged, so a saved hotkey
    reads back identically after a restart."""
    combo = KeyCombo(("win", "alt"), "G", 0x47)
    restored = combo_from_dict(combo.to_dict())
    assert restored == combo


def test_combo_to_dict_orders_modifiers():
    """Modifiers must serialize in a stable order regardless of the set."""
    combo = KeyCombo(("alt", "win"), "P", 0x50)
    assert combo.to_dict()["modifiers"] == ["win", "alt"]


def test_combo_deserialization_is_normalized():
    """A combo built from an unordered modifier set must not compare equal
    to a differently-ordered set, but must be mutually equal after
    normalization via frozenset."""
    a = KeyCombo(("win", "alt"), "P", 0x50)
    b = KeyCombo(("alt", "win"), "P", 0x50)
    # Modifiers are stored as a frozenset, so order is irrelevant.
    assert a == b
    assert hash(a) == hash(b)


def test_combo_from_dict_rejects_malformed():
    """A missing, wrong-typed, or empty combo entry must yield None, not
    raise, so a corrupt config cannot break hotkey setup."""
    assert combo_from_dict(None) is None
    assert combo_from_dict({}) is None
    assert combo_from_dict({"modifiers": [], "key": "P", "vk": 0x50}) is None
    assert (
        combo_from_dict({"modifiers": ["bogus"], "key": "P", "vk": 0x50})
        is None
    )
    assert (
        combo_from_dict({"modifiers": ["win"], "key": "P", "vk": "x"}) is None
    )


def test_combo_win32_modifier_mask():
    """win32_modifiers() must return the RegisterHotKey mask for the
    combo's modifiers."""
    assert KeyCombo(("win", "alt"), "P", 0x50).win32_modifiers() == (
        hotkey.MOD_WIN | hotkey.MOD_ALT
    )
    assert (
        KeyCombo(("ctrl",), "A", 0x41).win32_modifiers() == hotkey.MOD_CONTROL
    )


def test_qkey_to_vk_for_ascii():
    """A letter's Qt Key value is already its Win32 VK code."""
    # Qt.Key.Key_A == 0x41 == VK 'A'.
    assert hotkey.qkey_to_vk(0x41) == 0x41


def test_qkey_to_vk_maps_function_keys():
    """Qt's F1-F12 use a differing range; they must map to VK_F1..VK_F12."""
    assert hotkey.qkey_to_vk(0x01000030) == 0x70  # F1 -> VK_F1
    assert hotkey.qkey_to_vk(0x0100003B) == 0x7B  # F12 -> VK_F12


def test_qkey_to_vk_maps_special_keys():
    """Common special keys (arrows, Delete, Home) must map to their VK
    codes so a recorded shortcut actually fires."""
    assert hotkey.qkey_to_vk(0x01000013) == 0x26  # Up arrow -> VK_UP
    assert hotkey.qkey_to_vk(0x01000015) == 0x28  # Down arrow -> VK_DOWN
    assert hotkey.qkey_to_vk(0x01000007) == 0x2E  # Delete -> VK_DELETE
    assert hotkey.qkey_to_vk(0x20) == 0x20  # Space


def test_qkey_to_vk_rejects_unknown_special():
    """An unmapped special key must yield 0 (no key) rather than a bogus
    VK code that would mis-register."""
    assert hotkey.qkey_to_vk(0x01000001) == 0


def test_qmodifiers_to_names_maps_meta_to_win():
    """Qt's Meta modifier (the Windows key) must map to the 'win' name."""
    from PySide6.QtCore import Qt

    flags = Qt.KeyboardModifier
    assert hotkey.qmodifiers_to_names(
        flags.MetaModifier | flags.AltModifier
    ) == ["win", "alt"]
    assert hotkey.qmodifiers_to_names(flags.ShiftModifier) == ["shift"]


def test_registration_is_noop_off_windows():
    """register() must fail closed on non-Windows rather than calling the
    missing ctypes.windll, so the hotkey is simply unavailable. On Windows
    it returns a bool: True when the key was registered, False when the key
    is already taken (RegisterHotKey fails loudly, never crashes)."""
    combo = hotkey.GlobalHotkey(hotkey.DEFAULT_COMBO)
    try:
        registered = combo.register()
    finally:
        combo.unregister()
    if hotkey._IS_WINDOWS:
        assert registered is True or registered is False
    else:
        assert registered is False


def test_native_event_filter_is_noop_off_windows():
    """The native filter must decline every event on non-Windows instead of
    dereferencing ctypes.windll, so an unrelated platform event cannot
    crash the process. On Windows the filter requires a real MSG pointer,
    so this is only meaningful off-Windows."""
    if hotkey._IS_WINDOWS:
        return
    hk = hotkey.GlobalHotkey(hotkey.DEFAULT_COMBO)
    assert hk.nativeEventFilter(b"windows_generic_MSG", 0) == (False, 0)
