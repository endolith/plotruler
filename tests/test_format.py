"""Tests for plotruler.format — the number-format option rendering."""

# -*- coding: utf-8 -*-

import pytest

from plotruler.format import (
    AUTO,
    E,
    ENGINEERING,
    NAMES,
    OPTIONS,
    PLAIN,
    SCIENTIFIC,
    SI,
    is_valid,
    render,
    superscript,
)

_TIMES = " \u00d7 10"


def _sup(n):
    return superscript(n)


def test_superscript_renders_digits():
    """A positive exponent must render as Unicode superscript digits."""
    assert superscript(7) == "\u2077"
    assert superscript(12) == "\u00b9\u00b2"


def test_superscript_renders_negative():
    """A negative exponent needs the superscript minus glyph."""
    assert superscript(-3) == "\u207b\u00b3"


def test_auto_stays_plain_for_normal_values():
    """Auto must render everyday magnitudes as plain decimals, not flip to
    scientific notation."""
    assert render(12.34, AUTO, 1, None) == "12.3"


def test_auto_switches_on_huge_values():
    """Auto must switch to scientific notation for very large values."""
    assert render(12345678, AUTO, 1, None) == "1.23" + _TIMES + _sup(7)


def test_auto_switches_on_tiny_values():
    """Auto must switch to scientific notation for very small values."""
    assert render(4.8e-12, AUTO, 1, None) == "4.8" + _TIMES + _sup(-12)


def test_plain_uses_decimal_precision():
    """Plain must round to the positional precision supplied by the axis."""
    assert render(12.345, PLAIN, 2, None) == "12.35"


def test_scientific_normalizes_mantissa():
    """Scientific notation must put a single nonzero digit before the
    decimal point."""
    assert render(12345678, SCIENTIFIC, 1, None) == "1.23" + _TIMES + _sup(7)


def test_scientific_handles_negative_values():
    """Scientific notation must keep the sign on the mantissa."""
    assert render(-5310, SCIENTIFIC, 1, None) == "-5.31" + _TIMES + _sup(3)


def test_engineering_uses_multiple_of_three():
    """Engineering notation must force the exponent to a multiple of 3."""
    assert render(531000, ENGINEERING, 1, None) == "531" + _TIMES + _sup(3)


def test_e_notation_is_ascii():
    """E notation must be ASCII, the computer-friendly form."""
    assert render(12345678, E, 1, None) == "1.23e7"


def test_si_prefix_uses_units():
    """SI-prefix mode must emit the prefix symbol for the exponent band."""
    assert render(531000, SI, 1, None) == "531 k"
    assert render(4.8e-9, SI, 1, None) == "4.8 n"


def test_log_axis_uses_significant_figures():
    """A log axis supplies significant figures, not decimals; Auto must
    honor that precision."""
    assert render(12.34, AUTO, None, 2) == "12"


def test_unknown_format_falls_back_to_plain():
    """An unknown format key must not raise; it renders as plain."""
    assert render(12.34, "bogus", 1, None) == "12.3"


def test_options_and_names_are_consistent():
    """Every option in OPTIONS must have a display name and validate."""
    for fmt in OPTIONS:
        assert is_valid(fmt)
        assert fmt in NAMES
    assert is_valid("bogus") is False
