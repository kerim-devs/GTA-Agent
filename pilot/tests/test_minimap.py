"""Real HUD regressions, with visually chosen expectations and angular tolerances."""

import json
import math
from pathlib import Path

import cv2
import numpy as np
import pytest

from pilot.contract import Reading
from pilot.minimap import read


@pytest.mark.parametrize(
    "name,corrupt",
    [
        ("110449-10.5", False),
        ("102851-73.6", False),
        ("104424-121.7", False),
        ("100713-179.3", True),
        ("100713-194.3", True),
        ("100713-199.5", True),
        ("100713-207.1", True),
        ("100713-217.767", True),
    ],
)
def test_recorded_route_free_roads_and_real_damage(name, corrupt):
    from pilot.minimap import _blocks

    path = Path(__file__).resolve().parents[2] / "lab/minimap/p54" / f"{name}.png"
    crop = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
    original = crop.copy()
    # Motion estimation still sees the original conservative block detector.
    assert _blocks(crop)[0] >= 2
    reading = read(crop)
    assert reading.corrupt is corrupt
    assert reading.route == "none"
    assert reading.confidence <= 0.35 if corrupt else reading.confidence > 0.35
    assert np.array_equal(crop, original)


def test_a_continuous_road_does_not_excuse_a_displaced_block():
    path = Path(__file__).resolve().parents[2] / "lab/minimap/p54/110449-10.5.png"
    crop = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
    crop[46:62, 130:146] = 0
    reading = read(crop)
    assert reading.corrupt
    assert reading.confidence <= 0.35


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


P59 = Path(__file__).resolve().parents[2] / "lab/minimap/p59"
NIGHT_TOWN = ("142428-168.2", "142428-192.2", "142428-220.2", "142428-236.2")


def night_town(name):
    return cv2.cvtColor(cv2.imread(str(P59 / f"{name}.png")), cv2.COLOR_BGR2RGB)


@pytest.mark.parametrize("name", NIGHT_TOWN)
def test_a_clean_night_town_map_with_a_route_is_not_damaged(name):
    # 20261112-142428: the buggy stood still, the thin roads and the car park polygons of a dimmed map
    # lay on 16 px borders for seventy seconds, and every tick was called damaged.
    from pilot.minimap import _blocks

    crop = night_town(name)
    assert _blocks(crop, route_strokes=True)[0] >= 2  # the pieces are there, the question is what they are
    reading = read(crop)
    assert reading.route == "purple"
    assert reading.minimap == "tilted"
    assert reading.corrupt is False
    assert reading.confidence > 0.5


def invert(crop, y=62, x=146):
    crop[y : y + 16, x : x + 16] = 255 - crop[y : y + 16, x : x + 16]


@pytest.mark.parametrize(
    "damage",
    [
        lambda crop: crop.__setitem__((slice(46, 62), slice(130, 146)), 0),
        lambda crop: crop.__setitem__((slice(62, 78), slice(146, 162)), 230),
        lambda crop: invert(crop),
        lambda crop: invert(crop, 94, 66),
        lambda crop: crop.__setitem__((slice(62, 78), slice(146, 162)), crop[2:18, 2:18].copy()),
    ],
    ids=["black", "white", "inverted", "inverted-low", "tile-from-outside-the-map"],
)
@pytest.mark.parametrize("name", NIGHT_TOWN)
def test_a_displaced_block_in_a_clean_night_town_map_is_still_damage(name, damage):
    crop = night_town(name)
    damage(crop)
    reading = read(crop)
    assert reading.corrupt
    assert reading.confidence <= 0.35
