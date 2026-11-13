import json
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
import pytest

from pilot import terrain
from pilot.contract import Detection, Hud, Observation, Pad, Reading
from pilot.driveon import DriveOn
from pilot.skills import REGISTRY

FIXTURE = Path(__file__).parent / "fixtures" / "driveon"


def observation(t, **changes):
    return replace(
        Observation(
            Reading("tilted", "none", None, None, 0.0, False, 0.9),
            moving=True,
            time=t,
            hud=Hud(wanted=0),
            mode="vehicle",
        ),
        **changes,
    )


def ticks(skill, count, **changes):
    start = 0.0 if skill.last_time is None else skill.last_time + 0.1
    results = []
    for i in range(count):
        results.append(skill.step(observation(round(start + i * 0.1, 6), **changes)))
        if results[-1].status != "running":
            break
    return results


def test_recorded_tunnel_road_then_recorded_route_returns():
    fixture = json.loads((FIXTURE / "readings.json").read_text())
    skill = DriveOn({})
    start = fixture["tunnel"][0]["t"]
    for sample in fixture["tunnel"]:
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        bgr = cv2.imread(str(FIXTURE / sample["crop"]))
        frame[530:700, 30:290] = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        result = skill.step(
            observation(sample["t"] - start, reading=Reading(**sample["reading"]), frame=frame)
        )
        assert result.status == "running"
        assert skill.state == "drive-road"
        assert result.pad.left[0] < 0
        assert result.pad.r2 == 0.5
    # The earlier route-bearing recording section follows with its original relative timing.
    # This is an input replay, not a claim that the new skill drove the recorded vehicle.
    resumed = skill.last_time + 0.1
    route_start = fixture["route"][0]["t"]
    for sample in fixture["route"]:
        result = skill.step(
            observation(resumed + sample["t"] - route_start, reading=Reading(**sample["reading"]))
        )
        if result.status != "running":
            break
    assert (result.status, result.reason, result.pad) == ("done", "route-back", Pad())
    assert skill.last_time - resumed >= 1.0


def test_registered_with_valid_contract():
    assert REGISTRY["drive_on"] is DriveOn
    assert len(DriveOn.prompt) <= 400
    assert DriveOn({"duration": -1}).limit == 10
    assert DriveOn({"duration": 999}).limit == 120


def test_half_throttle_follows_road_and_slows_for_turn(monkeypatch):
    land = terrain.Terrain(((40.0, 20.0), (180.0, 20.0)), True, (None,) * 36, False)
    monkeypatch.setattr(terrain, "read", lambda crop: land)
    skill = DriveOn({})
    result = skill.step(observation(0, frame=np.zeros((720, 1280, 3), dtype=np.uint8)))
    assert result.status == "running"
    assert skill.state == "drive-road"
    assert result.pad.left[0] > 0
    assert 0.3 <= result.pad.r2 < 0.5


def test_fresh_traffic_reduces_pedal_and_stale_detections_do_not():
    traffic = (Detection("car", (500, 350, 780, 600), 0.8),)
    clear = DriveOn({}).step(observation(2))
    fresh = DriveOn({}).step(observation(2, objects=traffic, objects_time=1.9))
    stale = DriveOn({}).step(observation(2, objects=traffic, objects_time=0))
    assert fresh.pad.r2 < clear.pad.r2
    assert stale.pad == clear.pad


@pytest.mark.parametrize("color", ["yellow", "purple"])
def test_route_must_be_sound_for_one_second(color):
    skill = DriveOn({})
    route = replace(observation(0).reading, route=color, bearing=20.0)
    assert all(r.status == "running" for r in ticks(skill, 10, reading=route))
    result = ticks(skill, 1, reading=route)[-1]
    assert (result.status, result.reason, result.pad) == ("done", "route-back", Pad())
    assert skill.step(observation(2)) == result


@pytest.mark.parametrize(
    "changes",
    [
        {"corrupt": True},
        {"confidence": 0.49},
        {"confidence": 1.1},
        {"confidence": float("nan")},
        {"bearing": None},
        {"bearing": float("inf")},
        {"route": "none"},
        {"arrow": None},
        {"minimap": "flat"},
    ],
)
def test_invalid_route_breaks_confirmation(changes):
    skill = DriveOn({})
    route = replace(observation(0).reading, route="yellow", bearing=0.0)
    ticks(skill, 9, reading=route)
    assert skill.step(observation(0.9, reading=replace(route, **changes))).status == "running"
    assert all(r.status == "running" for r in ticks(skill, 10, reading=route))
    assert ticks(skill, 1, reading=route)[-1].reason == "route-back"


def test_gap_does_not_count_as_observed_route():
    skill = DriveOn({})
    route = replace(observation(0).reading, route="yellow", bearing=0.0)
    skill.step(observation(0, reading=route))
    assert skill.step(observation(2, reading=route)).status == "running"
    assert skill.route_since == 2


@pytest.mark.parametrize(
    "changes,reason,count",
    [
        ({"mode": "foot"}, "on-foot", 16),
        ({"hud": Hud(wanted=1)}, "stars-lit", 6),
        ({"hud": Hud(wanted=0, screen="map")}, "screen-map", 11),
        ({"hud": Hud(wanted=0, screen="wasted")}, "wasted", 6),
        ({"hud": Hud(wanted=0, screen="busted")}, "busted", 6),
        ({"hud": None}, "no-hud; the stars cannot be read", 21),
    ],
)
def test_safety_waits_for_confirmation_then_stops(changes, reason, count):
    skill = DriveOn({})
    results = ticks(skill, count, **changes)
    assert all(r.pad == Pad() for r in results)
    assert all(r.status == "running" for r in results[:-1])
    assert (results[-1].status, results[-1].reason) == ("failed", reason)


def test_water_stops_neutrally(monkeypatch):
    land = terrain.Terrain((), False, (None,) * 36, True)
    monkeypatch.setattr(terrain, "read", lambda crop: land)
    results = ticks(DriveOn({}), 11, frame=np.zeros((720, 1280, 3), dtype=np.uint8))
    assert all(r.pad == Pad() for r in results)
    assert (results[-1].status, results[-1].reason) == ("failed", "water")


def test_held_car_recovers_then_fails():
    results = ticks(DriveOn({"duration": 120}), 500, moving=False)
    assert any(r.pad.l2 > 0 for r in results)
    assert max(r.pad.r2 for r in results) <= 0.5
    assert (results[-1].status, results[-1].reason, results[-1].pad) == ("failed", "vehicle-held", Pad())


def test_default_limit_is_done_and_neutral():
    skill = DriveOn({})
    assert skill.step(observation(0)).pad.r2 == 0.5
    result = skill.step(observation(30))
    assert (result.status, result.reason, result.pad) == ("done", "time-limit", Pad())


@pytest.mark.parametrize(
    "changes",
    [
        {"reading": None},
        {"mode": "unknown"},
        {"hud": Hud(wanted=None)},
        {"hud": Hud(wanted=True)},
        {"reading": replace(observation(0).reading, corrupt=True)},
    ],
)
def test_uncertain_tick_is_neutral_and_does_not_decide(changes):
    skill = DriveOn({})
    result = skill.step(observation(0, **changes))
    assert (result.status, result.pad) == ("running", Pad())
    assert skill.step(observation(0.1)).pad.r2 > 0


@pytest.mark.parametrize(
    "args", [None, {"other": 1}, {"duration": True}, {"duration": float("nan")}, {"duration": "30"}]
)
def test_invalid_arguments(args):
    with pytest.raises(ValueError):
        DriveOn(args)


def test_stop_releases_controls():
    skill = DriveOn({})
    skill.step(observation(0))
    result = skill.stop()
    assert result.pad == Pad()
    assert result.status == "failed"
    assert skill.step(observation(1)) == result
