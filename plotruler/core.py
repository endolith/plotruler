"""Pixel-to-value math for PlotRuler.

This module is deliberately free of any Qt imports so it stays
unit-testable and portable. The overlay layer passes coordinates in
one consistent space (physical screen pixels); this module turns them
into data values.

Each axis maps screen coordinate to value through two anchor points.
By default the map is linear (affine): two anchor points define a line
and any screen coordinate is interpolated (or extrapolated) along it.
A log axis instead fits the line in logarithmic space, so a fixed pixel
step yields a fixed multiplicative factor rather than a fixed additive
step. X and Y are independent, so a full calibration is just two maps.
"""

from math import floor, isfinite, log10

from .format import AUTO, render


class AxisCalibration:
    """Maps one screen axis to values using two (coordinate, value) anchors.

    The anchors may be supplied in either order; a line is fit through
    both. Screen coordinates normally grow toward the lower right while
    data values may grow in either direction, so an inverted axis
    (screen down = value up, the usual graph layout) is handled
    naturally by the line fit.

    When log is True the line is fit on log10(value) instead of value:
    value = 10**(a * coordinate + b). This requires both anchor values
    to be positive (a log scale cannot represent zero or negatives).
    """

    def __init__(self, p1, v1, p2, v2, log=False):
        if p1 == p2:
            raise ValueError("calibration anchors must be distinct")
        self.p1 = float(p1)
        self.v1 = float(v1)
        self.p2 = float(p2)
        self.v2 = float(v2)
        self.log = bool(log)
        if self.log and not (self.v1 > 0 and self.v2 > 0):
            raise ValueError("log axes require positive anchor values")

    def _log_slope(self):
        """Decades per pixel, the log-axis analog of scale()."""
        return (log10(self.v2) - log10(self.v1)) / (self.p2 - self.p1)

    def value(self, p):
        """Return the data value at screen coordinate p.

        Interpolates between the anchors, or extrapolates past them so
        the readout stays sensible just outside the calibrated region.
        """
        if self.log:
            exponent = log10(self.v1) + (p - self.p1) * self._log_slope()
            result = 10**exponent
            if not isfinite(result):
                raise ValueError("log value is out of range")
            return result
        return self.v1 + (p - self.p1) / (self.p2 - self.p1) * (
            self.v2 - self.v1
        )

    def scale(self):
        """Return units per pixel for this axis (always positive).

        Only meaningful for a linear axis; on a log axis a fixed pixel
        step gives a multiplicative factor instead, so precision is
        tracked as significant figures (see format()).
        """
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

    def _log_significant_figures(self, pixel_error=1.0):
        """Significant figures for a log axis given click precision.

        A pixel_error-pixel error moves the value by a factor of
        10**(slope * pixel_error), so the relative uncertainty is
        constant along the axis; we show just enough significant figures
        that the last one is not swamped by that uncertainty. This is
        the log analog of decimals() for a linear axis.
        """
        relative = abs(10 ** (self._log_slope() * pixel_error) - 1)
        if not isfinite(relative) or relative <= 0:
            return 1
        return max(1, -floor(log10(relative)))

    def format(self, value, pixel_error=1.0, fmt=AUTO):
        """Return value as a string using the requested number format.

        A linear axis rounds to decimals; a log axis shows a fixed
        number of significant figures because its precision is relative,
        not additive. The number format (plain, scientific, etc.) is
        applied by the formatter module; the axis only supplies the
        precision (decimals for linear, sig-figs for log) it implies.
        """
        decimals = None if self.log else self.decimals(pixel_error)
        sig = self._log_significant_figures(pixel_error) if self.log else None
        return render(value, fmt, decimals, sig)

    def __repr__(self):
        return (
            f"AxisCalibration({self.p1}, {self.v1}, {self.p2}, {self.v2}, "
            f"log={self.log})"
        )


class Calibration:
    """Two AxisCalibrations, one per screen axis, forming a full 2-D map."""

    def __init__(self, x, y):
        self.x = x
        self.y = y

    def xy(self, px, py):
        """Return the (x, y) data values at the screen point (px, py)."""
        return self.x.value(px), self.y.value(py)

    def region(self):
        """Return the calibrated pixel bounds as (left, top, right, bottom).

        The X anchors give the horizontal extent and the Y anchors the
        vertical extent, so the calibrated region is the rectangle between
        them regardless of the order the anchors were clicked. The overlay
        draws this as a guide so a misaligned graph underneath is noticed.
        """
        top, bottom = sorted((self.y.p1, self.y.p2))
        left, right = sorted((self.x.p1, self.x.p2))
        return left, top, right, bottom

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

    # The whole flow as a fixed sequence of micro-steps: for each axis a
    # click, a value, a second click, a second value, then a linear/log
    # choice. A plain pointer into this list is the entire state, which
    # makes undo trivial (step back and drop the stored data for the step
    # we return to).
    _STEPS = (
        ("click", "x", 0),
        ("value", "x", 0),
        ("click", "x", 1),
        ("value", "x", 1),
        ("mode", "x", None),
        ("click", "y", 0),
        ("value", "y", 0),
        ("click", "y", 1),
        ("value", "y", 1),
        ("mode", "y", None),
    )

    def __init__(self):
        self._step = 0
        self._points = {}
        self._values = {}
        # Axis scale mode: "lin" or "log". Set when the mode step for an
        # axis is reached. A log scale needs both values positive, so an
        # axis with a zero (or negative) anchor is forced to linear and
        # the mode step is skipped automatically.
        self._scale_mode = {"x": "lin", "y": "lin"}

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

    @property
    def expecting_mode(self):
        """True when the next step needs a linear/log choice.

        This only advances if both anchor values for the axis are
        positive; otherwise the axis cannot be logarithmic, so the mode
        step is skipped and the axis stays linear.
        """
        if not self.active:
            return False
        kind, axis, _index = self._STEPS[self._step]
        if kind != "mode":
            return False
        return self._log_permitted(axis)

    def _log_permitted(self, axis):
        """True if a log scale is possible for an axis (both values > 0)."""
        v0 = self._values.get((axis, 0))
        v1 = self._values.get((axis, 1))
        return v0 is not None and v1 is not None and v0 > 0 and v1 > 0

    @property
    def current_axis(self):
        """The axis ('x' or 'y') being calibrated right now, or None.

        Returns the axis of the current step whether it is awaiting a
        click or a value, so the overlay can draw a live guide line in
        the right orientation while the user aligns a point.
        """
        if not self.active:
            return None
        return self._STEPS[self._step][1]

    def prompt(self):
        """Return the instruction for the step currently being waited on."""
        if not self.active:
            return "Calibration complete"
        kind, axis, index = self._STEPS[self._step]
        name = "X" if axis == "x" else "Y"
        if kind == "value":
            return f"Type the value at this {name} point, then press Enter"
        if kind == "mode":
            return f"Is the {name} axis linear or log? (click a button)"
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
        self._skip_auto_mode()

    def nudge_point(self, dx, dy):
        """Shift the most recently placed point by (dx, dy) physical pixels.

        Valid only while a value is awaited for a point that was just
        clicked, so the user can nudge an anchor along the axis before
        typing its value. Returns False (and does nothing) otherwise.
        """
        if not self.active:
            return False
        kind, axis, index = self._STEPS[self._step]
        if kind != "value":
            return False
        key = (axis, index)
        if key not in self._points:
            return False
        px, py = self._points[key]
        self._points[key] = (px + dx, py + dy)
        return True

    def record_value(self, value):
        """Attach a numeric value to the point that was just clicked."""
        if not self.active:
            raise ValueError("calibration is already complete")
        kind, axis, index = self._STEPS[self._step]
        if kind != "value":
            raise ValueError("a click is being requested, not a value")
        self._values[(axis, index)] = float(value)
        self._step += 1
        self._skip_auto_mode()

    def record_mode(self, scale_mode):
        """Choose how the current axis is scaled: 'lin' or 'log'.

        Called when the session expects a mode step (see expecting_mode).
        Rejects a log scale when the axis has a non-positive anchor value.
        """
        if not self.active:
            raise ValueError("calibration is already complete")
        kind, axis, _index = self._STEPS[self._step]
        if kind != "mode":
            raise ValueError("a mode choice is not being requested")
        if scale_mode == "log" and not self._log_permitted(axis):
            raise ValueError("log scale needs positive anchor values")
        if scale_mode not in ("lin", "log"):
            raise ValueError("scale mode must be 'lin' or 'log'")
        self._scale_mode[axis] = scale_mode
        self._step += 1

    def _skip_auto_mode(self):
        """Advance past a mode step the user never has to see.

        A mode step whose axis has a zero or negative anchor cannot be
        logarithmic, so it is fixed to linear and skipped rather than
        stalling the flow waiting for a choice the user cannot make.
        """
        while self.active and self._STEPS[self._step][0] == "mode":
            axis = self._STEPS[self._step][1]
            if self._log_permitted(axis):
                break
            self._scale_mode[axis] = "lin"
            self._step += 1

    def undo(self):
        """Undo the most recent step, clearing its stored data.

        After a value is typed, undo returns to the value prompt with the
        point still marked. After a click, undo removes the point too.
        """
        if self._step == 0:
            return
        self._step -= 1
        # Skip back over a mode step the user never saw (auto-skipped
        # because log was impossible), so undo lands on a real step.
        while self._step > 0 and self._STEPS[self._step][0] == "mode":
            axis = self._STEPS[self._step][1]
            if self._log_permitted(axis):
                break
            self._step -= 1
        if self._step == 0:
            return
        kind, axis, index = self._STEPS[self._step]
        if kind == "click":
            self._points.pop((axis, index), None)
        elif kind == "value":
            self._values.pop((axis, index), None)
        else:
            # Mode step: revert the axis to linear so it can be re-picked.
            self._scale_mode[axis] = "lin"

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
        log = self._scale_mode.get(axis, "lin") == "log"
        return AxisCalibration(p0, v0, p1, v1, log=log)
