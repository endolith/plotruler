"""Regression tests for plotruler.win_hittest on non-Windows platforms.

The Win32 hit-test shim must be a no-op away from Windows. The old guard
was `wintypes is None`, but ctypes.wintypes imports fine on Linux, so the
frame calls would reach ctypes.windll and die with AttributeError. These
tests pin the behavior: every Win32 entry point returns its no-op value
without touching the window or ctypes.windll.

The behavior under test only exists off Windows, so the whole module is
skipped on Windows (where the shim is real, not a no-op).
"""

import pytest

from plotruler import win_hittest

pytestmark = pytest.mark.skipif(
    win_hittest._IS_WINDOWS,
    reason="Win32 shim is active on Windows; no-op is off-Windows only",
)


def test_platform_gate_false_on_non_windows():
    """The Win32 gate must be off when not actually running on Windows, so
    the shim cannot reach ctypes.windll (which does not exist off Windows)."""
    assert win_hittest._IS_WINDOWS is False


def test_apply_native_overlapped_style_is_noop():
    """apply_native_overlapped_style must return early on non-Windows rather
    than dereferencing ctypes.windll with a None window."""
    win_hittest.apply_native_overlapped_style(None)


def test_current_styles_is_noop():
    """current_styles must report no style on non-Windows instead of
    raising."""
    assert win_hittest.current_styles(None) == (None, None)


def test_window_rect_is_noop():
    """window_rect must report no rect on non-Windows instead of raising."""
    assert win_hittest.window_rect(None) is None


def test_set_window_rect_is_noop():
    """set_window_rect must return early on non-Windows instead of raising."""
    win_hittest.set_window_rect(None, (0, 0, 0, 0))


def test_handle_native_event_is_noop():
    """handle_native_event must decline every event on non-Windows, even a
    Windows-shaped event type, instead of reaching the Win32 dispatch."""
    assert win_hittest.handle_native_event(
        None, b"windows_generic_MSG", 0
    ) == (
        False,
        0,
    )
