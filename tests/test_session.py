"""Tests for plotruler.core.CalibrationSession — the click-and-type flow."""

import pytest

from plotruler.core import CalibrationSession


def _complete_x(session):
    """Drive the session through the two X-axis click/value pairs."""
    session.record_point(100, 50)
    session.record_value(0.0)
    session.record_point(300, 50)
    session.record_value(10.0)


def test_full_session_builds_calibration():
    """Four clicks and four values in order must produce a Calibration
    that maps the anchors to their typed values."""
    session = CalibrationSession()
    _complete_x(session)
    session.record_point(150, 100)
    session.record_value(20.0)
    session.record_point(150, 300)
    session.record_value(0.0)
    cal = session.calibration()
    assert cal is not None
    assert cal.xy(100, 100) == pytest.approx((0.0, 20.0))
    assert cal.xy(300, 300) == pytest.approx((10.0, 0.0))


def test_value_before_click_is_rejected():
    """The flow is strictly click-then-value; typing a value when a click
    is expected must raise rather than silently misalign the steps."""
    session = CalibrationSession()
    with pytest.raises(ValueError):
        session.record_value(5.0)


def test_click_while_waiting_for_value_is_rejected():
    """After a point is clicked the session waits for its value; a second
    click before the value is typed must raise."""
    session = CalibrationSession()
    session.record_point(100, 50)
    with pytest.raises(ValueError):
        session.record_point(200, 60)


def test_undo_returns_to_value_then_to_click():
    """Undo must walk back one step at a time: first clearing the typed
    value, then the clicked point, so retyping is possible either way."""
    session = CalibrationSession()
    session.record_point(100, 50)
    session.record_value(3.0)
    session.undo()
    assert session.prompt() == (
        "Type the value at this X point, then press Enter"
    )
    session.undo()
    assert session.prompt() == "Click the first X point"


def test_undo_at_start_is_noop():
    """Undo on a fresh session must do nothing rather than error."""
    session = CalibrationSession()
    session.undo()
    assert session.active


def test_incomplete_session_has_no_calibration():
    """calibration() must be None until every anchor has a value."""
    session = CalibrationSession()
    assert session.calibration() is None
    _complete_x(session)
    assert session.calibration() is None


def test_degenerate_axis_has_no_calibration():
    """Two clicks with the same pixel coordinate on one axis cannot form
    a line; calibration() must return None instead of raising."""
    session = CalibrationSession()
    session.record_point(100, 50)
    session.record_value(0.0)
    session.record_point(100, 90)
    session.record_value(10.0)
    session.record_point(200, 100)
    session.record_value(5.0)
    session.record_point(300, 200)
    session.record_value(5.0)
    assert session.calibration() is None


def test_prompts_follow_axis_order():
    """Prompts must guide X axis first then Y axis, in click-then-value
    order, so the user always knows what the next step is."""
    session = CalibrationSession()
    seen = []
    while session.active:
        prompt = session.prompt()
        seen.append(prompt)
        if prompt.startswith("Click"):
            session.record_point(100, 100)
        else:
            session.record_value(1.0)
    seen.append(session.prompt())
    assert seen == [
        "Click the first X point",
        "Type the value at this X point, then press Enter",
        "Click the second X point",
        "Type the value at this X point, then press Enter",
        "Click the first Y point",
        "Type the value at this Y point, then press Enter",
        "Click the second Y point",
        "Type the value at this Y point, then press Enter",
        "Calibration complete",
    ]


def test_anchors_report_values_only_after_typing():
    """anchors() must expose each clicked point with value None until its
    value is typed, so the overlay can paint a marker without a label."""
    session = CalibrationSession()
    session.record_point(100, 50)
    assert session.anchors() == [("x", 0, 100, 50, None)]
    session.record_value(3.0)
    assert session.anchors() == [("x", 0, 100, 50, 3.0)]


def test_expecting_flags_track_the_step_kind():
    """expecting_click must be true before a click and false after it,
    expecting_value the mirror image, so the overlay knows whether to
    capture a point or typed text."""
    session = CalibrationSession()
    assert session.expecting_click and not session.expecting_value
    session.record_point(100, 50)
    assert not session.expecting_click and session.expecting_value
    session.record_value(3.0)
    assert session.expecting_click and not session.expecting_value


def test_flags_are_false_when_done():
    """Both expecting flags must be false once the calibration is complete,
    so the overlay stops capturing input."""
    session = CalibrationSession()
    while session.active:
        if session.expecting_click:
            session.record_point(100, 100)
        else:
            session.record_value(1.0)
    assert not session.expecting_click
    assert not session.expecting_value
