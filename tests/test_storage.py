"""Tests for plotruler.storage — calibration and config persistence."""

import os

from plotruler import storage
from plotruler.core import AxisCalibration, Calibration


def _make_calibration():
    x = AxisCalibration(150, 0, 450, 10)
    y = AxisCalibration(100, 20, 400, 0)
    return Calibration(x, y)


def test_calibration_round_trips_through_dict(tmp_path):
    """A Calibration must survive a dict round-trip with exact values, so
    a saved calibration reads back identically after a restart."""
    original = _make_calibration()
    restored = storage.calibration_from_dict(
        storage.calibration_to_dict(original)
    )
    assert restored is not None
    assert restored.x.value(300) == original.x.value(300)
    assert restored.y.value(250) == original.y.value(250)


def test_save_and_load_calibration(tmp_path):
    """save() must write a calibration that calibration() reads back."""
    path = os.path.join(tmp_path, "config", "settings.json")
    storage.save(path, calibration=_make_calibration())
    restored = storage.calibration(path)
    assert restored is not None
    assert restored.x.p1 == 150.0 and restored.y.v2 == 0.0


def test_save_and_load_geometry(tmp_path):
    """Geometry must round-trip as a four-element int list."""
    path = os.path.join(tmp_path, "settings.json")
    storage.save(path, geometry=[10, 20, 800, 600])
    assert storage.geometry(path) == [10, 20, 800, 600]


def test_save_preserves_preexisting_fields(tmp_path):
    """save() must merge, not overwrite: passing calibration when geometry
    already exists must leave the geometry intact."""
    path = os.path.join(tmp_path, "settings.json")
    storage.save(path, geometry=[30, 40, 500, 400])
    storage.save(path, calibration=_make_calibration())
    assert storage.geometry(path) == [30, 40, 500, 400]
    assert storage.calibration(path) is not None


def test_missing_file_returns_empty(tmp_path):
    """A missing config file must yield an empty dict and None values, not
    raise, so a first run starts cleanly."""
    path = os.path.join(tmp_path, "does-not-exist.json")
    assert storage.load(path) == {}
    assert storage.calibration(path) is None
    assert storage.geometry(path) is None


def test_corrupt_file_returns_empty(tmp_path):
    """Corrupt JSON must not crash; calibration() and geometry() return
    None so the overlay starts uncalibrated."""
    path = os.path.join(tmp_path, "settings.json")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("{not valid json")
    assert storage.load(path) == {}
    assert storage.calibration(path) is None
    assert storage.geometry(path) is None


def test_malformed_calibration_returns_none(tmp_path):
    """A calibration with missing or non-numeric fields must yield None
    rather than raising when constructing AxisCalibration."""
    path = os.path.join(tmp_path, "settings.json")
    storage.save(path, geometry=[0, 0, 100, 100])
    data = storage.load(path)
    data["calibration"] = {"x": {"p1": "bad"}, "y": {}}
    import json

    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    assert storage.calibration(path) is None


def test_save_creates_parent_directory(tmp_path):
    """save() must create missing parent directories of the config path."""
    path = os.path.join(tmp_path, "deeply", "nested", "settings.json")
    storage.save(path, geometry=[1, 2, 3, 4])
    assert os.path.exists(path)
