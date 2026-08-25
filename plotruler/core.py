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
