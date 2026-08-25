"""Pixel-to-value math for PlotRuler.

This module is deliberately free of any Qt imports so it stays
unit-testable and portable. The overlay layer passes coordinates in
one consistent space (physical screen pixels); this module turns them
into data values.

Each axis is a linear (affine) map: two screen anchor points with known
values define a line, and any screen coordinate is interpolated (or
extrapolated) along it. X and Y are independent, so a full calibration
is just two such lines.
"""

from math import floor, log10


class AxisCalibration:
    """Maps one screen axis to values using two (coordinate, value) anchors.

    The anchors may be supplied in either order; a line is fit through
    both. Screen coordinates normally grow toward the lower right while
    data values may grow in either direction, so an inverted axis
    (screen down = value up, the usual graph layout) is handled
    naturally by the line fit.
    """

    def __init__(self, p1, v1, p2, v2):
        if p1 == p2:
            raise ValueError("calibration anchors must be distinct")
        self.p1 = float(p1)
        self.v1 = float(v1)
        self.p2 = float(p2)
        self.v2 = float(v2)

    def value(self, p):
        """Return the data value at screen coordinate p.

        Interpolates between the anchors, or extrapolates past them so
        the readout stays sensible just outside the calibrated region.
        """
        return self.v1 + (p - self.p1) / (self.p2 - self.p1) * (
            self.v2 - self.v1
        )

    def scale(self):
        """Return units per pixel for this axis (always positive)."""
        return abs((self.v2 - self.v1) / (self.p2 - self.p1))

    def decimals(self, pixel_error=1.0):
        """Return how many decimals to display given click precision.

        A pixel_error-pixel click error becomes scale() * pixel_error
        units of uncertainty on the readout; we display just enough
        decimals that the rounding unit is no finer than that
        uncertainty, so the readout never over-claims precision.
        """
        uncertainty = self.scale() * pixel_error
        if uncertainty <= 0:
            return 0
        return max(0, -floor(log10(uncertainty)))

    def format(self, value, pixel_error=1.0):
        """Return value as a string rounded to the display precision."""
        return "{:.{}f}".format(value, self.decimals(pixel_error))

    def __repr__(self):
        return f"AxisCalibration({self.p1}, {self.v1}, {self.p2}, {self.v2})"


class Calibration:
    """Two AxisCalibrations, one per screen axis, forming a full 2-D map."""

    def __init__(self, x, y):
        self.x = x
        self.y = y

    def xy(self, px, py):
        """Return the (x, y) data values at the screen point (px, py)."""
        return self.x.value(px), self.y.value(py)

    def __repr__(self):
        return f"Calibration(x={self.x}, y={self.y})"


class CalibrationSession:
    """Guides the four click-and-type steps that build a calibration.

    The user calibrates the X axis first (two points), then the Y axis
    (two points). Each point is a screen position; immediately after
    clicking it the user types the value that the position represents.
    The session is a small state machine over that fixed sequence so the
    overlay can paint a prompt for the step it is waiting on and can
    undo steps or cancel cleanly.

    Positions are in the same coordinate space the rest of the math
    uses (physical screen pixels); the session does not care what units
    they are in.
    """

    # The whole flow as a fixed sequence of micro-steps: each point is a
    # click followed by a value. A plain pointer into this list is the
    # entire state, which makes undo trivial (step back and drop the
    # stored data for the step we return to).
    _STEPS = (
        ("click", "x", 0),
        ("value", "x", 0),
        ("click", "x", 1),
        ("value", "x", 1),
        ("click", "y", 0),
        ("value", "y", 0),
        ("click", "y", 1),
        ("value", "y", 1),
    )

    def __init__(self):
        self._step = 0
        self._points = {}
        self._values = {}

    @property
    def active(self):
        """True while a calibration is still being entered."""
        return self._step < len(self._STEPS)

    @property
    def expecting_click(self):
        """True when the next step needs a point click."""
        return self.active and self._STEPS[self._step][0] == "click"

    @property
    def expecting_value(self):
        """True when the next step needs a typed value."""
        return self.active and self._STEPS[self._step][0] == "value"

    def prompt(self):
        """Return the instruction for the step currently being waited on."""
        if not self.active:
            return "Calibration complete"
        kind, axis, index = self._STEPS[self._step]
        name = "X" if axis == "x" else "Y"
        if kind == "value":
            return f"Type the value at this {name} point, then press Enter"
        which = "first" if index == 0 else "second"
        return f"Click the {which} {name} point"

    def record_point(self, px, py):
        """Record a clicked screen position for the current step."""
        if not self.active:
            raise ValueError("calibration is already complete")
        kind, axis, index = self._STEPS[self._step]
        if kind != "click":
            raise ValueError("a value is being requested, not a click")
        self._points[(axis, index)] = (px, py)
        self._step += 1

    def record_value(self, value):
        """Attach a numeric value to the point that was just clicked."""
        if not self.active:
            raise ValueError("calibration is already complete")
        kind, axis, index = self._STEPS[self._step]
        if kind != "value":
            raise ValueError("a click is being requested, not a value")
        self._values[(axis, index)] = float(value)
        self._step += 1

    def undo(self):
        """Undo the most recent step, clearing its stored data.

        After a value is typed, undo returns to the value prompt with the
        point still marked. After a click, undo removes the point too.
        """
        if self._step == 0:
            return
        self._step -= 1
        kind, axis, index = self._STEPS[self._step]
        if kind == "click":
            self._points.pop((axis, index), None)
        else:
            self._values.pop((axis, index), None)

    def anchors(self):
        """Return the points entered so far, oldest first.

        Each item is (axis, index, px, py, value); value is None until
        the point's value has been typed. The overlay uses this to paint
        the anchor markers.
        """
        result = []
        for key, (px, py) in sorted(self._points.items()):
            axis, index = key
            result.append((axis, index, px, py, self._values.get(key)))
        return result

    def calibration(self):
        """Return the Calibration for the entered anchors, or None.

        A calibration only exists once every point has a value. A
        degenerate axis (both clicks at the same coordinate) cannot form
        a line, so it yields None too.
        """
        if self.active:
            return None
        try:
            x = self._axis_calibration("x")
            y = self._axis_calibration("y")
        except ValueError:
            return None
        return Calibration(x, y)

    def _axis_calibration(self, axis):
        def coord(key):
            px, py = self._points[key]
            return (px if axis == "x" else py), self._values[key]

        p0, v0 = coord((axis, 0))
        p1, v1 = coord((axis, 1))
        return AxisCalibration(p0, v0, p1, v1)
