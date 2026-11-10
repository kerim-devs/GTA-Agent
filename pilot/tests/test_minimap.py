"""Real HUD regressions, with visually chosen expectations and angular tolerances."""

import json
import math
from pathlib import Path

import cv2
import numpy as np
import pytest

from pilot.contract import Reading
from pilot.minimap import read

FIXTURES = Path(__file__).parent / "fixtures"
CASES = json.loads((FIXTURES / "expectations.json").read_text())["minimap"]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_real_reading(case):
    crop = cv2.cvtColor(cv2.imread(str(FIXTURES / case["file"])), cv2.COLOR_BGR2RGB)
    before = crop.copy()
    result = read(crop)
    assert isinstance(result, Reading)
    assert result.minimap == case["minimap"]
    assert result.route == case["route"]
    if result.route == "none":
        assert result.bearing is None
        assert result.far_bearing is None
    for field in ("bearing", "arrow"):
        if field in case:
            actual = getattr(result, field)
            assert actual is not None
            error = abs((actual - case[field] + 180) % 360 - 180)
            assert error <= case[f"{field}_tolerance"]
    if "corrupt" in case:
        assert result.corrupt is case["corrupt"]
    if "confidence_max" in case:
        assert result.confidence <= case["confidence_max"]
    # The reader is stateless and must not damage the runtime's shared crop.
    read(np.zeros_like(crop))
    assert read(crop) == result
    np.testing.assert_array_equal(crop, before)


@pytest.mark.parametrize("seed", range(10))
def test_noise_never_raises_and_returns_finite_contract(seed):
    crop = np.random.default_rng(seed).integers(0, 256, (170, 260, 3), dtype=np.uint8)
    result = read(crop)
    assert isinstance(result, Reading)
    assert result.minimap in {"none", "flat", "tilted"}
    assert result.route in {"none", "yellow", "purple"}
    assert math.isfinite(result.confidence) and 0 <= result.confidence <= 1
    for value in (result.bearing, result.far_bearing, result.arrow):
        assert value is None or (math.isfinite(value) and -180 < value <= 180)


@pytest.mark.parametrize("value", [0, 255])
def test_uniform_input_has_no_map_or_route(value):
    result = read(np.full((170, 260, 3), value, np.uint8))
    assert result.minimap == result.route == "none"
    assert result.bearing is result.far_bearing is result.arrow is None


@pytest.mark.parametrize("crop", [None, np.zeros((10, 10, 3), np.uint8), np.zeros((170, 260, 3))])
def test_invalid_input_is_unknown(crop):
    result = read(crop)
    assert result.minimap == result.route == "none"
    assert result.confidence == 0


@pytest.mark.parametrize("case", [c for c in CASES if c["route"] != "none"], ids=lambda case: case["name"])
def test_path_starts_where_the_route_is_visible(case):
    crop = cv2.cvtColor(cv2.imread(str(FIXTURES / case["file"])), cv2.COLOR_BGR2RGB)
    radii = [math.hypot(x, y) for x, y in read(crop).path]
    assert radii
    # The arrow hides the route below 11 px, and the driver drops a path with a point nearer than 10.
    assert min(radii) >= 11
    assert radii[0] <= 16
