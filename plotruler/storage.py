"""Persist a calibration and the window position to disk.

This module is deliberately free of any Qt imports so it stays
unit-testable and portable, following the same rule as the math core.
It stores a Calibration (and optional window geometry) as JSON in a
user config file; the overlay layer decides where that file lives,
so this module only deals with the data shape.

The config file is a small JSON object:

    {
        "geometry": [x, y, width, height],
        "calibration": {
            "x": {"p1": ..., "v1": ..., "p2": ..., "v2": ..., "log": false},
            "y": {"p1": ..., "v1": ..., "p2": ..., "v2": ..., "log": false}
        }
    }
"""

import json
import os

from .core import AxisCalibration, Calibration


def calibration_to_dict(calibration):
    """Return a Calibration as a nested dict."""
    return {
        "x": {
            "p1": calibration.x.p1,
            "v1": calibration.x.v1,
            "p2": calibration.x.p2,
            "v2": calibration.x.v2,
            "log": calibration.x.log,
        },
        "y": {
            "p1": calibration.y.p1,
            "v1": calibration.y.v1,
            "p2": calibration.y.p2,
            "v2": calibration.y.v2,
            "log": calibration.y.log,
        },
    }


def calibration_from_dict(data):
    """Build a Calibration from a dict, or None if it is malformed.

    A corrupted or truncated file should not crash the app; returning
    None means the overlay simply starts uncalibrated. The log flag is
    optional (defaults to linear) so configs written before the log-axis
    feature still load.
    """
    try:
        x = AxisCalibration(
            data["x"]["p1"],
            data["x"]["v1"],
            data["x"]["p2"],
            data["x"]["v2"],
            log=bool(data["x"].get("log", False)),
        )
        y = AxisCalibration(
            data["y"]["p1"],
            data["y"]["v1"],
            data["y"]["p2"],
            data["y"]["v2"],
            log=bool(data["y"].get("log", False)),
        )
    except KeyError, TypeError, ValueError:
        return None
    return Calibration(x, y)


def load(path):
    """Read the config file; returns a dict, or {} if missing/corrupt."""
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError, ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def save(path, geometry=None, calibration=None, hotkey=None):
    """Write geometry, calibration, and/or hotkey to the config file.

    Existing values not being updated are preserved, so callers only need
    to pass the fields they changed. Missing keys just keep their old
    value; a fresh save with no prior file writes whatever is provided.
    """
    data = load(path)
    if geometry is not None:
        data["geometry"] = geometry
    if calibration is not None:
        data["calibration"] = calibration_to_dict(calibration)
    if hotkey is not None:
        data["hotkey"] = hotkey
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)


def calibration(path):
    """Return the saved Calibration, or None."""
    return calibration_from_dict(load(path).get("calibration"))


def hotkey(path):
    """Return the saved hotkey config dict, or None."""
    value = load(path).get("hotkey")
    return value if isinstance(value, dict) else None


def geometry(path):
    """Return the saved geometry as a list, or None."""
    value = load(path).get("geometry")
    if (
        isinstance(value, list)
        and len(value) == 4
        and all(isinstance(v, (int, float)) for v in value)
    ):
        return [int(v) for v in value]
    return None
