"""Number-format options for the readout.

This module is free of any Qt imports so it stays unit-testable and
portable. The readout can show a value several ways: plain decimals,
scientific notation (m x 10^n), engineering notation (exponent a
multiple of 3), E notation (ASCII, the computer friendly form), or SI
prefixes (12.3 k). "auto" shows plain for everyday magnitudes and
switches to scientific only for very large or very small values.

precision: a linear axis carries positional precision (how many decimal
places are meaningful); a log axis carries relative precision (how many
significant figures). The axis computes both from a pixel-error model and
hands them in, so this module never has to know about the calibration.
"""

from math import floor, isfinite, log10

# The format choices, ordered for the tray menu and the number-key
# shortcuts. These strings are the persistent config keys.
AUTO = "auto"
PLAIN = "plain"
SCIENTIFIC = "scientific"
ENGINEERING = "engineering"
E = "e"
SI = "si"

OPTIONS = (AUTO, PLAIN, SCIENTIFIC, ENGINEERING, E, SI)

NAMES = {
    AUTO: "Auto",
    PLAIN: "Plain",
    SCIENTIFIC: "Scientific",
    ENGINEERING: "Engineering",
    E: "E notation",
    SI: "SI prefixes",
}

# A value at or above this magnitude (or below its reciprocal) is "huge"
# (or "tiny") enough that auto switches to scientific notation.
_HIGH = 1e6
_LOW = 1e-4

# Cap on significant figures for the exponent styles when the precision
# comes from a linear axis's positional model (see render()).
_MAX_SIG_FIGS = 3

# ASCII superscript digits and minus, used to render the exponent in the
# "x 10^n" styles. Qt renders these as real superscripts.
_SUPERSCRIPT = {
    "0": "\u2070",
    "1": "\u00b9",
    "2": "\u00b2",
    "3": "\u00b3",
    "4": "\u2074",
    "5": "\u2075",
    "6": "\u2076",
    "7": "\u2077",
    "8": "\u2078",
    "9": "\u2079",
    "-": "\u207b",
}

# SI prefix symbols keyed by the exponent they represent (a multiple of 3).
_SI_PREFIXES = {
    30: "Q",
    27: "R",
    24: "Y",
    21: "Z",
    18: "E",
    15: "P",
    12: "T",
    9: "G",
    6: "M",
    3: "k",
    0: "",
    -3: "m",
    -6: "\u00b5",  # micro sign
    -9: "n",
    -12: "p",
    -15: "f",
    -18: "a",
    -21: "z",
    -24: "y",
    -27: "r",
    -30: "q",
}


def is_valid(fmt):
    """True if fmt is one of the known format keys."""
    return fmt in OPTIONS


def superscript(exponent):
    """Return an integer exponent as superscript digits, e.g. -3 -> ⁻³."""
    sign = "" if exponent >= 0 else "\u207b"
    digits = "".join(_SUPERSCRIPT[d] for d in str(abs(exponent)))
    return sign + digits


def _times_ten(exponent):
    """Render ' x 10^exponent' using the Unicode superscript form."""
    return " \u00d7 10" + superscript(exponent)


def _sig_figs_for_decimals(value, decimals):
    """Significant figures of a value rounded to `decimals` places.

    The number of significant figures is the span from the most
    significant digit to the least significant (which sits at the
    `decimals` place). This lets a positional-precision axis (linear)
    report equivalent significant figures for the exponent styles.
    """
    if decimals is None:
        return None
    if value == 0:
        return 1
    rounded = round(value, decimals)
    if rounded == 0:
        return 1
    most_sig = floor(log10(abs(rounded)))
    return max(1, min(15, most_sig + decimals + 1))


def _sig(value, sig_figs):
    """Round value to a number of significant figures as a plain decimal.

    This must never resort to the 'g' format specifier: for a mantissa
    like 490 with 2 significant figures, '%.2g' yields '4.9e+02', which
    leaks scientific notation into SI prefixes or engineering mantissas.
    Instead, compute how many decimal places a value rounded to sig_figs
    needs and render with a plain fixed-point format.
    """
    if value == 0 or not isfinite(value):
        return str(value)
    digits = sig_figs - 1 - floor(log10(abs(value)))
    if digits < 0:
        digits = 0
    return f"{value:.{digits}f}"


def _plain(value, decimals, sig_figs):
    """Render a value without scaling, honoring positional or relative
    precision whichever the axis supplied."""
    if decimals is not None:
        return f"{value:.{decimals}f}"
    return _sig(value, sig_figs)


def _strip_zeros(text):
    """Remove trailing zeros and a trailing point from a mantissa string."""
    if "." not in text:
        return text
    text = text.rstrip("0").rstrip(".")
    return text or "0"


def _scientific(value, sig_figs):
    """Render value as m x 10^n with 1 <= |m| < 10."""
    if value == 0 or not isfinite(value):
        return _plain(value, 0, sig_figs) if value == 0 else str(value)
    sign = "-" if value < 0 else ""
    mant = abs(value)
    exponent = floor(log10(mant))
    scaled = mant / (10**exponent)
    text = _strip_zeros(_sig(scaled, sig_figs))
    if float(text) >= 10:  # rounding pushed the mantissa into the next decade
        scaled = mant / (10 ** (exponent + 1))
        text = _strip_zeros(_sig(scaled, sig_figs))
        exponent += 1
    return f"{sign}{text}{_times_ten(exponent)}"


def _engineering(value, sig_figs):
    """Render value as m x 10^n with n a multiple of 3 and 1 <= |m| < 1000."""
    if value == 0 or not isfinite(value):
        return _plain(value, 0, sig_figs) if value == 0 else str(value)
    sign = "-" if value < 0 else ""
    mant = abs(value)
    exponent = 3 * floor(floor(log10(mant)) / 3)
    scaled = mant / (10**exponent)
    text = _strip_zeros(_sig(scaled, sig_figs))
    if float(text) >= 1000:  # rounding overflowed the mantissa past 1000
        exponent += 3
        scaled = mant / (10**exponent)
        text = _strip_zeros(_sig(scaled, sig_figs))
    return f"{sign}{text}{_times_ten(exponent)}"


def _e_notation(value, sig_figs):
    """Render value as the ASCII E form, e.g. 1.23e4."""
    if value == 0 or not isfinite(value):
        return _plain(value, 0, sig_figs) if value == 0 else str(value)
    sign = "-" if value < 0 else ""
    mant = abs(value)
    exponent = floor(log10(mant))
    scaled = mant / (10**exponent)
    text = _strip_zeros(_sig(scaled, sig_figs))
    if float(text) >= 10:
        scaled = mant / (10 ** (exponent + 1))
        text = _strip_zeros(_sig(scaled, sig_figs))
        exponent += 1
    return f"{sign}{text}e{exponent}"


def _si_prefix(value, sig_figs):
    """Render value with an SI prefix from the SI-prefix table."""
    if value == 0 or not isfinite(value):
        return _plain(value, 0, sig_figs) if value == 0 else str(value)
    mant = abs(value)
    exponent = 3 * floor(floor(log10(mant)) / 3)
    prefix = _SI_PREFIXES.get(exponent, "")
    scaled = mant / (10**exponent)
    text = _strip_zeros(_sig(scaled, sig_figs))
    if float(text) >= 1000:  # rounding spilled into the next prefix band
        exponent += 3
        prefix = _SI_PREFIXES.get(exponent, "")
        scaled = mant / (10**exponent)
        text = _strip_zeros(_sig(scaled, sig_figs))
    suffix = (" " + prefix) if prefix else ""
    return f"{text}{suffix}"


def _auto_choose(value):
    """Pick the format for 'auto': plain unless the value is huge/tiny."""
    if value == 0:
        return PLAIN
    magnitude = abs(value)
    if magnitude >= _HIGH or magnitude < _LOW:
        return SCIENTIFIC
    return PLAIN


def render(value, fmt, decimals, sig_figs):
    """Return value as a string in the given format.

    decimals is the positional precision (None for a log axis); sig_figs
    is the relative precision (None for a linear axis). One of the two is
    always provided. An unknown fmt falls back to plain.
    """
    if fmt == AUTO:
        fmt = _auto_choose(value)
    if fmt == PLAIN or fmt not in NAMES:
        return _plain(value, decimals, sig_figs)
    if decimals is not None and sig_figs is None:
        # A linear axis has positional precision, which for a large value
        # would balloon into many significant figures (e.g. a whole number
        # to 1 decimal is ~9 sig figs). That is honest but unreadable, so
        # clamp the exponent styles to a few figures like a hand readout.
        sig_figs = _sig_figs_for_decimals(value, decimals)
        sig_figs = max(2, min(sig_figs, _MAX_SIG_FIGS))
    if sig_figs is None:
        sig_figs = _sig_figs_for_decimals(value, decimals) or 3
    if fmt == SCIENTIFIC:
        return _scientific(value, sig_figs)
    if fmt == ENGINEERING:
        return _engineering(value, sig_figs)
    if fmt == E:
        return _e_notation(value, sig_figs)
    if fmt == SI:
        return _si_prefix(value, sig_figs)
    return _plain(value, decimals, sig_figs)
