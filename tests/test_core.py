"""Tests for plotruler.core — the Qt-free pixel-to-value math."""

import pytest

from plotruler.core import AxisCalibration, Calibration


def test_interpolates_midpoint():
    """A 100..200 px axis mapped to 0..10 must read 5 exactly at the
    midpoint (150 px)."""
    cal = AxisCalibration(100, 0, 200, 10)
    assert cal.value(150) == pytest.approx(5.0)


def test_inverted_y_axis_maps_screen_down_to_value_up():
    """Screen y grows downward but graph y usually grows upward; the line
    fit through two anchors must invert correctly so a low screen point
    (large py) reads a small value and a high screen point a large one."""
    cal = AxisCalibration(100, 10, 200, 0)
    assert cal.value(100) == pytest.approx(10.0)
    assert cal.value(200) == pytest.approx(0.0)
    assert cal.value(150) == pytest.approx(5.0)


def test_reverse_anchor_order_gives_same_result():
    """The user may click the two calibration points in any order; the
    fitted line must be identical either way."""
    forward = AxisCalibration(100, 0, 200, 10)
    reversed_ = AxisCalibration(200, 10, 100, 0)
    for p in (120, 150, 180, 250):
        assert forward.value(p) == pytest.approx(reversed_.value(p))


def test_extrapolates_beyond_anchors():
    """Reading just outside the calibrated region must extrapolate rather
    than clamp, so the readout stays continuous at the edges."""
    cal = AxisCalibration(100, 0, 200, 10)
    assert cal.value(50) == pytest.approx(-5.0)
    assert cal.value(250) == pytest.approx(15.0)


def test_fractional_values_interpolate():
    """Non-integer anchor values must interpolate linearly, not snap to
    the nearest anchor."""
    cal = AxisCalibration(100, 0.5, 200, 2.5)
    assert cal.value(150) == pytest.approx(1.5)


def test_xy_combines_both_axes():
    """A full calibration maps a screen point to an independent (x, y)
    pair, each axis through its own two anchors."""
    x = AxisCalibration(100, 0, 200, 10)
    y = AxisCalibration(100, 10, 200, 0)
    cal = Calibration(x, y)
    assert cal.xy(150, 150) == pytest.approx((5.0, 5.0))
    assert cal.xy(100, 200) == pytest.approx((0.0, 0.0))


def test_region_bounds_ignore_click_order():
    """region() must span the calibrated pixels regardless of the order
    the anchors were clicked, so the guide box always encloses the graph."""
    forward = Calibration(
        AxisCalibration(100, 0, 400, 10),
        AxisCalibration(200, 20, 50, 0),
    )
    assert forward.region() == (100, 50, 400, 200)
    # Same anchors, reversed on both axes: identical bounds.
    reversed_ = Calibration(
        AxisCalibration(400, 10, 100, 0),
        AxisCalibration(50, 0, 200, 20),
    )
    assert reversed_.region() == forward.region()


def test_degenerate_axis_raises():
    """Clicking the same coordinate for both anchors is a user error with
    no defined line; it must be rejected loudly, not divide by zero."""
    with pytest.raises(ValueError):
        AxisCalibration(150, 0, 150, 10)


@pytest.mark.parametrize(
    ("slope", "expected_decimals"),
    [
        (0.3, 1),  # 1 px error is 0.3 units, so tenths are the finest digit
        (3.0, 0),  # 1 px error is 3 units, so whole numbers are honest
        (
            0.03,
            2,
        ),  # 1 px error is 0.03 units, so hundredths are the finest digit
        (0.0, 0),  # constant axis: nothing to claim
        (0.1, 1),  # exactly one unit per ten pixels: tenths are exact
    ],
)
def test_decimals_match_click_precision(slope, expected_decimals):
    """The number of displayed decimals must track the axis scale so the
    readout never over-claims precision: a slope of s units/px with a 1 px
    click error should round at the place of s, not finer."""
    # Build an axis with the requested slope (any anchor positions work).
    cal = AxisCalibration(0, 0, 100, slope * 100)
    assert cal.decimals() == expected_decimals


def test_format_rounds_to_precision():
    """format() must round to the decimals computed from the scale, so
    e.g. a 0.3 units/px axis shows 12.3 rather than 12.30."""
    cal = AxisCalibration(100, 0, 200, 30)
    assert cal.format(12.34) == "12.3"


def test_scale_is_positive():
    """scale() is used for precision and must be a magnitude, so an
    inverted axis reports the same units-per-pixel as its mirror."""
    up = AxisCalibration(100, 0, 200, 10)
    down = AxisCalibration(100, 10, 200, 0)
    assert up.scale() == down.scale() == 0.1
