from dataclasses import replace

import cv2
import numpy as np
import pytest

from pilot.contract import NEUTRAL_PAD, Reading
from pilot.roam import DriveFree, Road, read_road
from pilot.skills import Observation

VEHICLE = Reading("tilted", "none", None, None, 0.0, False, 0.9)


def crop(*roads):
    image = np.full((170, 260, 3), 65, np.uint8)
    for points in roads:
        cv2.polylines(image, [np.array(points, np.int32)], False, (225, 225, 225), 9)
    cv2.fillPoly(image, [np.array([[123, 112], [119, 121], [127, 121]])], (255, 255, 255))
    return image


@pytest.mark.parametrize("wish,expected", [("any", 0), ("straight", 0), ("left", -1), ("right", 1)])
def test_junction_wishes(wish, expected):
    image = crop([(123, 139), (123, 30)], [(45, 80), (207, 80)])
    before = image.copy()
    road = read_road(image, wish, reading=VEHICLE)
    assert road is not None
    x, y = road.path[-1]
    assert y > 20
    assert abs(x) < 4 if not expected else x * expected > 20
    assert np.hypot(*road.path[0]) < 19
    assert image.tolist() == before.tolist()
    assert read_road(image, wish, reading=VEHICLE) == road


@pytest.mark.parametrize("wish", ["any", "straight", "left", "right"])
def test_unavailable_turn_follows_only_continuation(wish):
    road = read_road(crop([(123, 139), (123, 80), (207, 80)]), wish, reading=VEHICLE)
    assert road is not None
    assert road.path[-1][0] > 20


@pytest.mark.parametrize("image", [None, np.zeros((10, 10, 3), np.uint8), np.zeros((170, 260, 3)), crop()])
def test_invalid_or_empty_picture_has_no_road(image):
    assert read_road(image, reading=VEHICLE) is None


def test_car_park_disconnected_road_and_damaged_picture_abstain():
    assert read_road(np.full((170, 260, 3), 225, np.uint8), reading=VEHICLE) is None
    assert read_road(crop([(160, 139), (160, 30)]), reading=VEHICLE) is None
    image = crop([(123, 139), (123, 30)])
    for reading in (
        replace(VEHICLE, corrupt=True),
        replace(VEHICLE, arrow=None),
        replace(VEHICLE, minimap="flat"),
    ):
        assert read_road(image, reading=reading) is None


@pytest.mark.parametrize(
    "args",
    [
        None,
        [],
        {"seconds": True},
        {"seconds": "2"},
        {"seconds": float("nan")},
        {"seconds": float("inf")},
        {"turn": []},
        {"turn": "up"},
        {"pace": 2},
        {"unknown": 1},
    ],
)
def test_rejects_bad_arguments(args):
    with pytest.raises(ValueError):
        DriveFree(args)


def test_metadata_and_clamping():
    assert DriveFree.name == "drive_free"
    assert len(DriveFree.prompt) <= 400
    assert DriveFree({"seconds": -100}).seconds == 1
    assert DriveFree({"seconds": 500}).seconds == 120
    assert set(DriveFree.parameters) == {"seconds", "turn", "pace"}


@pytest.fixture
def observation(monkeypatch):
    road = Road(((0, 8), (0, 20), (0, 40)), 9, 0)
    monkeypatch.setattr(
        "pilot.roam.read_road", lambda _crop, _wish, *, reading: None if reading.corrupt else road
    )

    def make(t, *, moving=True, corrupt=False, frame=True):
        return Observation(
            replace(VEHICLE, corrupt=corrupt),
            moving,
            t,
            np.zeros((720, 1280, 3), np.uint8) if frame else None,
        )

    return make


def test_complete_pad_and_terminal_latch(observation):
    skill = DriveFree({"seconds": 1})
    pad = skill.step(observation(0)).pad
    assert pad.r2 > 0 and pad.l2 == 0 and pad.right == (0, 0) and not pad.buttons
    result = skill.step(observation(1))
    assert result.status == "done" and result.pad == NEUTRAL_PAD
    assert skill.step(observation(2)) == result
    assert skill.stop("replace") == result
    replacement = DriveFree({})
    replacement.step(observation(0))
    assert replacement.stop("replaced").pad == NEUTRAL_PAD
    assert replacement.step(observation(0.1)).status == "failed"


@pytest.mark.parametrize("missing", ["frame", "corrupt", "motion"])
def test_blindness_releases_immediately_and_fails_with_reason(observation, missing):
    skill = DriveFree({})
    assert skill.step(observation(0)).pad.r2 > 0
    options = (
        {"frame": False}
        if missing == "frame"
        else {"corrupt": True}
        if missing == "corrupt"
        else {"moving": None}
    )
    for i in range(1, 30):
        result = skill.step(observation(i / 10, **options))
        assert result.pad == NEUTRAL_PAD
    assert result.status == "failed" and result.reason


def test_stale_time_and_long_gap_release(observation):
    skill = DriveFree({})
    skill.step(observation(0))
    assert skill.step(observation(1)).pad == NEUTRAL_PAD
    assert skill.step(observation(1)).status == "failed"
    for t in (float("nan"), float("inf"), "later"):
        result = DriveFree({}).step(observation(t))
        assert result.status == "failed" and result.pad == NEUTRAL_PAD


def test_reverse_is_bounded_and_missing_motion_never_proves_stuck(observation):
    skill = DriveFree({"seconds": 120})
    reverse_ticks = 0
    for i in range(700):
        result = skill.step(observation(i / 30, moving=False))
        reverse_ticks += result.pad.l2 > 0
        assert not result.pad.buttons and result.pad.right == (0, 0)
        assert not (result.pad.r2 and result.pad.l2)
        if result.status != "running":
            break
    assert result.status == "failed" and "three" in result.reason
    assert result.pad == NEUTRAL_PAD and 0 < reverse_ticks <= 3 * 46
    unknown = DriveFree({})
    for i in range(100):
        assert unknown.step(observation(i / 30, moving=None)).pad == NEUTRAL_PAD


def test_damage_interrupts_reverse(observation):
    skill = DriveFree({})
    for i in range(70):
        result = skill.step(observation(i / 30, moving=False))
    assert result.pad.l2 > 0
    assert skill.step(observation(70 / 30, moving=False, corrupt=True)).pad == NEUTRAL_PAD
    assert skill.step(observation(71 / 30, moving=True)).pad.l2 > 0


def test_dead_end_coasts_then_reverses_with_fresh_stationary_evidence(observation, monkeypatch):
    monkeypatch.setattr("pilot.roam.read_road", lambda *a, **k: Road(((0, 7), (0, 10)), 8, 0, True))
    skill = DriveFree({})
    assert skill.step(observation(0, moving=True)).pad == NEUTRAL_PAD
    assert skill.step(observation(0.1, moving=False)).pad.l2 > 0
    result = skill.stop("replace")
    assert result.pad == NEUTRAL_PAD


def test_pace_caps_and_narrow_bend_reduce_throttle(observation, monkeypatch):
    pedals = [DriveFree({"pace": pace}).step(observation(0)).pad.r2 for pace in ("slow", "normal", "fast")]
    assert 0 < pedals[0] < pedals[1] < pedals[2] <= 0.6
    monkeypatch.setattr("pilot.roam.read_road", lambda *a, **k: Road(((7, 8), (15, 20), (25, 25)), 3, 0))
    pad = DriveFree({}).step(observation(0)).pad
    assert pad.left[0] > 0 and pad.r2 < pedals[0]


def test_malformed_observations_release_instead_of_raising(observation):
    for value in (None, {}, object()):
        result = DriveFree({}).step(value)
        assert result.status == "failed" and result.pad == NEUTRAL_PAD
    assert DriveFree({}).step(observation(True)).status == "failed"
    for reading in (None, {}, object()):
        skill = DriveFree({})
        skill.step(observation(0))
        for i in range(1, 30):
            result = skill.step(replace(observation(i / 10), reading=reading))
            assert result.pad == NEUTRAL_PAD
        assert result.status == "failed"
    for moving in (0, 1, "moving", [], float("nan")):
        assert DriveFree({}).step(observation(0, moving=moving)).pad == NEUTRAL_PAD


def test_fresh_crop_damage_check_cannot_be_bypassed_by_old_reading(monkeypatch):
    image = crop([(123, 139), (123, 30)])
    assert read_road(image, reading=VEHICLE) is not None
    monkeypatch.setattr("pilot.roam._blocks", lambda _crop: (2, 4))
    assert read_road(image, reading=VEHICLE) is None


def test_bad_road_metadata_abstains():
    image = crop([(123, 139), (123, 30)])
    for reading in ({}, object(), replace(VEHICLE, arrow="north"), replace(VEHICLE, arrow=True)):
        assert read_road(image, reading=reading) is None


def test_brief_blind_ticks_do_not_prevent_stuck_recovery(observation):
    skill = DriveFree({"seconds": 120})
    reversed_once = False
    for i in range(750):
        result = skill.step(observation(i / 30, moving=None if i % 20 == 17 else False, corrupt=i % 10 == 5))
        if i % 10 == 5 or i % 20 == 17:
            assert result.pad == NEUTRAL_PAD
        reversed_once |= result.pad.l2 > 0
        if result.status != "running":
            break
    assert reversed_once and result.status == "failed" and "three" in result.reason
    assert result.pad == NEUTRAL_PAD
