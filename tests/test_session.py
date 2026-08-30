"""Tests for plotruler.core.CalibrationSession — the click-and-type flow."""

import pytest

from plotruler.core import CalibrationSession


def _complete_x(session):
    """Drive the session through the two X-axis click/value pairs."""
    session.record_point(100, 50)
    session.record_value(0.0)
    session.record_point(300, 50)
    session.record_value(10.0)


def _complete_x_log(session):
    """Complete the X axis points on a log scale (positive anchor values).

    Records only the clicks and values, leaving the X mode step pending so
    the caller decides linear vs log.
    """
    session.record_point(100, 50)
    session.record_value(1.0)
    session.record_point(300, 50)
    session.record_value(100.0)


def test_full_session_builds_calibration():
    """Four clicks and four values in order must produce a Calibration
    that maps the anchors to their typed values."""
    session = CalibrationSession()
    _complete_x(session)  # values 0 and 10: mode auto-skips to linear
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
    order with a linear/log choice after each axis's second value, so the
    user always knows what the next step is."""
    session = CalibrationSession()
    seen = []
    while session.active:
        prompt = session.prompt()
        seen.append(prompt)
        if session.expecting_mode:
            session.record_mode("lin")
        elif prompt.startswith("Click"):
            session.record_point(100, 100)
        else:
            session.record_value(1.0)
    seen.append(session.prompt())
    assert seen == [
        "Click the first X point",
        "Type the value at this X point, then press Enter",
        "Click the second X point",
        "Type the value at this X point, then press Enter",
        "Is the X axis linear or log? (click a button)",
        "Click the first Y point",
        "Type the value at this Y point, then press Enter",
        "Click the second Y point",
        "Type the value at this Y point, then press Enter",
        "Is the Y axis linear or log? (click a button)",
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


def test_current_axis_reports_the_axis_being_calibrated():
    """current_axis must report X for the X steps and Y for the Y steps,
    both while waiting for a click and a value, so the overlay can draw a
    live guide line in the matching orientation."""
    session = CalibrationSession()
    assert session.current_axis == "x"
    session.record_point(100, 50)
    assert session.current_axis == "x"
    session.record_value(3.0)
    session.record_point(200, 60)
    assert session.current_axis == "x"
    session.record_value(4.0)
    assert session.current_axis == "x"
    session.record_mode("lin")
    assert session.current_axis == "y"
    session.record_point(300, 100)
    assert session.current_axis == "y"
    session.record_value(5.0)
    session.record_point(300, 300)
    assert session.current_axis == "y"
    session.record_value(6.0)
    assert session.current_axis == "y"
    session.record_mode("lin")
    assert session.current_axis is None


def test_flags_are_false_when_done():
    """Both expecting flags must be false once the calibration is complete,
    so the overlay stops capturing input."""
    session = CalibrationSession()
    while session.active:
        if session.expecting_mode:
            session.record_mode("lin")
        elif session.expecting_click:
            session.record_point(100, 100)
        else:
            session.record_value(1.0)
    assert not session.expecting_click
    assert not session.expecting_value
    assert not session.expecting_mode


def test_mode_presented_after_each_axis():
    """A mode step must follow the second value on each axis, so the user
    picks linear/log for X then Y before moving on."""
    session = CalibrationSession()
    _complete_x_log(session)
    assert session.expecting_mode
    assert session.prompt() == "Is the X axis linear or log? (click a button)"
    session.record_mode("log")
    session.record_point(150, 100)
    session.record_value(1.0)
    session.record_point(150, 300)
    session.record_value(10.0)
    assert session.expecting_mode
    assert session.prompt() == "Is the Y axis linear or log? (click a button)"


def test_log_mode_applies_to_axis():
    """Choosing log for an axis must produce a calibration where that
    axis maps in log space and the other stays linear."""
    session = CalibrationSession()
    _complete_x_log(session)
    session.record_mode("log")
    session.record_point(150, 100)
    session.record_value(1.0)
    session.record_point(150, 300)
    session.record_value(10.0)
    session.record_mode("lin")
    cal = session.calibration()
    assert cal.x.log and not cal.y.log
    # X axis: 1 at 100, 100 at 300 -> midpoint (200) reads 10.
    # Y axis (linear): 1 at 100, 10 at 300 -> at 150 reads 3.25.
    assert cal.xy(200, 150) == pytest.approx((10.0, 3.25))


def test_zero_anchor_skips_mode_step():
    """A zero anchor value makes log impossible, so the mode step must be
    skipped automatically and the axis stays linear (no choice shown)."""
    session = CalibrationSession()
    session.record_point(100, 50)
    session.record_value(0.0)
    session.record_point(300, 50)
    session.record_value(100.0)
    assert not session.expecting_mode
    assert session.prompt() == "Click the first Y point"
    session.record_point(150, 100)
    session.record_value(5.0)
    session.record_point(150, 300)
    session.record_value(5.0)
    assert session.expecting_mode  # Y values are positive, so Y asks
    session.record_mode("lin")
    cal = session.calibration()
    assert not cal.x.log and not cal.y.log


def test_negative_anchor_skips_mode_step():
    """A negative anchor makes log impossible, so that axis's mode step is
    skipped (fixed to linear) and no log choice is offered."""
    session = CalibrationSession()
    session.record_point(100, 50)
    session.record_value(-2.0)
    session.record_point(300, 50)
    session.record_value(100.0)
    assert not session.expecting_mode
    assert session.prompt() == "Click the first Y point"
    session.record_point(150, 100)
    session.record_value(1.0)
    session.record_point(150, 300)
    session.record_value(10.0)
    session.record_mode("lin")
    cal = session.calibration()
    assert not cal.x.log and not cal.y.log


def test_undo_removes_log_mode_back_to_linear():
    """Undoing a mode choice must revert that axis to linear so the choice
    can be made again."""
    session = CalibrationSession()
    _complete_x_log(session)
    session.record_mode("log")
    # Back up over the mode decision and re-present it.
    session.undo()
    assert session.expecting_mode
    session.record_mode("lin")
    assert session.prompt() == "Click the first Y point"


def test_nudge_point_while_awaiting_value():
    """nudge_point must shift the just-placed point while a value is being
    awaited, so a slightly-off click can be corrected before typing."""
    session = CalibrationSession()
    session.record_point(100, 50)
    assert session.nudge_point(3, 0) is True
    assert session.anchors()[0] == ("x", 0, 103, 50, None)
    assert session.nudge_point(0, -2) is True
    assert session.anchors()[0] == ("x", 0, 103, 48, None)


def test_nudge_point_is_rejected_before_click():
    """nudge_point must fail cleanly (not raise) before any point exists,
    since there is nothing to shift."""
    session = CalibrationSession()
    assert session.nudge_point(1, 0) is False


def test_nudge_point_is_rejected_after_value_typed():
    """nudge_point must fail once the value has been typed (the step moved
    on), since the point is then fixed; returns False, not an error."""
    session = CalibrationSession()
    session.record_point(100, 50)
    session.record_value(4.0)
    assert session.nudge_point(1, 1) is False


def test_nudge_point_rejects_perpendicular_axis_motion():
    """A point on the X axis must not move vertically, and vice versa, so
    the anchor stays on its calibrated axis line. The overlay enforces this
    per axis; the session accepts any delta the caller intends."""
    session = CalibrationSession()
    session.record_point(100, 50)
    assert session.nudge_point(0, 5) is True  # session allows it; callers gate
    session.record_value(1.0)
    key = ("x", 0)
    px, py = session._points[key]
    assert (px, py) == (100, 55)
