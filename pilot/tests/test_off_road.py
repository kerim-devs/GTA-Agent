"""P50: evidence from the countryside, hospital corner and pier railing."""

import math
from pathlib import Path
from types import SimpleNamespace

import cv2
import pytest

from pilot.contract import Observation, Reading
from pilot.foot import FootGuard, Road, Steer, WalkRoad, north_bearing, world_shift, world_view
from pilot.minimap import read

EVIDENCE = Path(__file__).resolve().parents[2] / "lab/foot/p50"
FLAT = Reading("flat", "none", None, None, 0.0, False, 0.9)


def image(name):
    return cv2.cvtColor(cv2.imread(str(EVIDENCE / (name + ".png"))), cv2.COLOR_BGR2RGB)


@pytest.mark.parametrize(
    "name,kind", [("hill-a", "going"), ("hill-b", "going"), ("hospital", "still"), ("pier", "still")]
)
def test_world_evidence_on_recorded_walking_and_obstacles(monkeypatch, name, kind):
    a, b = image(name + "-a"), image(name + "-b")
    shift = world_shift(world_view(a), world_view(b))
    assert shift is not None
    assert (shift >= 0.65) if kind == "going" else (shift < 0.25)
    monkeypatch.setattr("pilot.foot.map_shift", lambda *_: None)
    guard = FootGuard()
    guard.step(Observation(FLAT, None, 0, frame=a), (0, -1))
    guard.step(Observation(FLAT, None, 0.5, frame=b), (0, -1))
    assert guard.evidence[-1][1] == kind


@pytest.mark.parametrize(
    "name",
    [
        "20261112-100318-blip-8",
        "20261112-100318-blip-9",
        "20261112-100318-blip-24",
        "20261112-100713-blip-5",
        "20261112-100713-blip-7",
        "20261112-100713-blip-15",
        "20261112-100713-blip-16",
        "20261112-100713-blip-25",
        "20261112-100713-blip-35",
        "20261112-100713-blip-36",
        "20261112-100713-blip-37",
        "20261112-100713-blip-38",
    ],
)
def test_ground_and_overlay_fragments_are_not_targets(name):
    assert read(image(name)).blips == ()


@pytest.mark.parametrize(
    "name,angle",
    [
        ("20261112-100318-blip-8", 119),
        ("20261112-100713-blip-5", -154),
        ("20261112-100713-blip-16", 46),
        ("20261112-100713-blip-37", -107),
    ],
)
def test_north_disc_at_top_and_bottom_edges(name, angle):
    assert north_bearing(image(name)) == pytest.approx(angle, abs=4)


def test_no_road_keeps_compass_heading_across_camera_turns(monkeypatch):
    crop = image("20261112-100713-blip-16")
    monkeypatch.setattr("pilot.foot.hud_crop", lambda _: crop)
    monkeypatch.setattr("pilot.foot.find_road", lambda _: None)
    compass = [30.0]
    monkeypatch.setattr("pilot.foot.north_bearing", lambda _: compass[0])
    skill = WalkRoad({"duration": 30})
    skill.guard = SimpleNamespace(step=lambda observation, want: Steer(want))
    for t, north in [(0, 30), (4, 80), (12, -170), (28, -60)]:
        compass[0] = north
        result = skill.step(Observation(FLAT, None, t, frame=crop))
        assert result.status == "running"
        assert skill.compass_heading == -30
        bearing = math.degrees(math.atan2(result.pad.left[0], -result.pad.left[1]))
        assert (bearing - north + 180) % 360 - 180 == pytest.approx(-30)
    assert skill.step(Observation(FLAT, None, 30, frame=crop)).reason == "time-limit"


def test_road_direction_survives_road_loss_and_missing_compass(monkeypatch):
    crop = image("20261112-100713-blip-16")
    monkeypatch.setattr("pilot.foot.hud_crop", lambda _: crop)
    road, north = [Road(70, 40, None)], [20.0]
    monkeypatch.setattr("pilot.foot.find_road", lambda _: road[0])
    monkeypatch.setattr("pilot.foot.north_bearing", lambda _: north[0])
    skill = WalkRoad({"duration": 30})
    skill.guard = SimpleNamespace(step=lambda observation, want: Steer(want))
    skill.step(Observation(FLAT, None, 0, frame=crop))
    road[0] = None
    for t, value, expected in [(1, 60, 110), (6, None, 110), (18, -90, -40)]:
        north[0] = value
        assert skill.step(Observation(FLAT, None, t, frame=crop)).status == "running"
        assert skill.compass_heading == 50
        assert skill.heading == expected
