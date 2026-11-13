"""Contract, sensor gaps and physical recovery tests for drive_to_blip."""

from dataclasses import replace

import pytest

from pilot import terrain
from pilot.contract import NEUTRAL_PAD, Blip, Hud, Observation, Reading
from pilot.pursuit import DriveToBlip


def observation(t=0.0, *, blips=None, moving=True, **changes):
    reading = Reading(
        "tilted",
        "none",
        None,
        None,
        0.0,
        False,
        0.9,
        blips=(Blip("blue", 0.0, 50.0),) if blips is None else blips,
    )
    return replace(Observation(reading, moving, t, hud=Hud(), mode="vehicle"), **changes)


@pytest.mark.parametrize(
    "args",
    [
        None,
        [],
        {"extra": 1},
        {"color": "green"},
        {"mode": "ram"},
        {"duration": True},
        {"duration": "3"},
        {"duration": float("nan")},
        {"duration": float("inf")},
        {"color": []},
        {"mode": None},
    ],
)
def test_reject_invalid_arguments(args):
    with pytest.raises(ValueError):
        DriveToBlip(args)


def test_descriptor_and_clamping():
    assert len(DriveToBlip.prompt) <= 400
    assert DriveToBlip({"duration": -9}).duration == 1
    assert DriveToBlip({"duration": 1e6}).duration == 300
    for name, choices in DriveToBlip.parameters.items():
        assert getattr(DriveToBlip({}), name) == (choices[-1] if name == "duration" else choices[0])


@pytest.mark.parametrize("mode", ["reach", "follow", "catch"])
@pytest.mark.parametrize("color", ["blue", "red", "yellow"])
def test_each_mode_and_color_has_complete_buttonless_pad(mode, color):
    skill = DriveToBlip({"mode": mode, "color": color, "duration": 4})
    for i in range(41):
        result = skill.step(observation(i / 10, blips=(Blip(color, 15, 60),)))
        assert not result.pad.buttons and result.pad.right == (0, 0)
        assert -1 <= result.pad.left[0] <= 1
        assert 0 <= result.pad.r2 <= 1 and 0 <= result.pad.l2 <= 1
    assert (result.status, result.reason, result.pad) == ("failed", "time-limit", NEUTRAL_PAD)
    assert skill.step(observation(9)) == result
    assert skill.stop("replacement") == result


def test_missing_marker_hold_then_pedal_up_then_failure():
    skill = DriveToBlip({"mode": "catch"})
    assert skill.step(observation()).pad.r2 > 0
    for t in (0.1, 1.0, 2.0):
        assert skill.step(observation(t, blips=())).pad.r2 > 0
    assert skill.step(observation(2.01, blips=())).pad == NEUTRAL_PAD
    assert skill.step(observation(4.99, blips=())).status == "running"
    result = skill.step(observation(5.0, blips=()))
    assert (result.status, result.reason, result.pad) == ("failed", "blip-gone", NEUTRAL_PAD)


def test_no_initial_marker_and_wrong_color():
    skill = DriveToBlip({})
    for t in (0, 1, 2, 4.9):
        assert skill.step(observation(t, blips=(Blip("red", 0, 30),))).pad == NEUTRAL_PAD
    assert skill.step(observation(5, blips=())).reason == "blip-gone"


def test_damage_holds_heading_for_two_seconds_without_refreshing_target():
    skill = DriveToBlip({"mode": "catch"})
    first = observation(blips=(Blip("blue", 20, 60),))
    skill.step(first)
    heading = skill.heading
    damaged = replace(first.reading, corrupt=True, arrow=None, blips=())
    for t in (0.1, 1.0, 2.0):
        result = skill.step(observation(t, reading=damaged))
        assert result.status == "running" and result.pad.r2 > 0
        assert skill.heading == heading
    assert skill.step(observation(2.1, reading=damaged)).pad == NEUTRAL_PAD
    result = skill.step(observation(5.0, reading=damaged))
    assert (result.reason, result.pad) == ("blip-gone", NEUTRAL_PAD)


def test_corrupt_flat_map_does_not_prove_the_driver_left():
    skill = DriveToBlip({"mode": "catch"})
    skill.step(observation())
    bad = replace(observation().reading, minimap="flat", corrupt=True, blips=())
    for t in (0.1, 1.2, 1.9):
        result = skill.step(observation(t, reading=bad, mode=None))
        assert result.status == "running" and result.pad.r2 > 0


def test_reach_does_not_report_arrival_while_still_moving():
    skill = DriveToBlip({"mode": "reach"})
    for i in range(10):
        result = skill.step(observation(i / 10, blips=(Blip("blue", 0, 3),), moving=True))
        assert result.status == "running" and result.pad.l2 > 0
    for i in range(10, 16):
        result = skill.step(observation(i / 10, blips=(Blip("blue", 0, 3),), moving=False))
    assert (result.status, result.reason, result.pad) == ("done", "reached", NEUTRAL_PAD)


def test_damaged_tick_cannot_confirm_arrival_or_extend_marker_lifetime():
    skill = DriveToBlip({})
    near = observation(blips=(Blip("blue", 0, 2),), moving=False)
    skill.step(near)
    damaged = replace(near, time=0.4, reading=replace(near.reading, corrupt=True))
    assert skill.step(damaged).pad == NEUTRAL_PAD
    assert skill.step(replace(near, time=0.5)).status == "running"
    assert skill.step(replace(near, time=0.9)).status == "running"
    result = skill.step(replace(near, time=1.0))
    assert (result.status, result.reason, result.pad) == ("done", "reached", NEUTRAL_PAD)


@pytest.mark.parametrize("mode", ["follow", "catch"])
def test_follow_and_catch_never_finish_at_marker(mode):
    skill = DriveToBlip({"mode": mode})
    for i in range(20):
        result = skill.step(observation(i / 10, blips=(Blip("blue", 0, 3),)))
        assert result.status == "running"
        if mode == "catch":
            assert result.pad.r2 > 0.9
    assert skill.stop("interrupted").pad == NEUTRAL_PAD


def test_behind_marker_uses_driver_turn():
    skill = DriveToBlip({"mode": "catch"})
    for i in range(15):
        result = skill.step(observation(i / 10, blips=(Blip("blue", 2, -23, True),)))
    assert skill.state == "turn-around"
    assert abs(result.pad.left[0]) >= 0.8
    assert result.pad.r2 > 0


@pytest.mark.parametrize(
    "screen",
    [
        "pause",
        "map",
        "weapon_wheel",
        "phone",
        "interaction_menu",
        "failed",
        "passed",
        "wasted",
        "busted",
        "loading",
    ],
)
def test_screen_requires_persistence_and_finishes_neutral(screen):
    skill = DriveToBlip({})
    bad = observation(hud=Hud(screen=screen))
    assert skill.step(bad).pad == NEUTRAL_PAD
    assert skill.step(observation(0.1)).status == "running"
    assert skill.step(replace(bad, time=0.2)).status == "running"
    result = skill.step(replace(bad, time=1.2))
    assert (result.reason, result.pad) == (f"screen-{screen}", NEUTRAL_PAD)


def test_on_foot_requires_persistence():
    skill = DriveToBlip({})
    assert skill.step(observation(mode="foot")).pad == NEUTRAL_PAD
    assert skill.step(observation(0.2)).status == "running"
    assert skill.step(observation(0.3, mode="foot")).status == "running"
    result = skill.step(observation(1.4, mode="foot"))
    assert (result.reason, result.pad) == ("on-foot", NEUTRAL_PAD)


def test_water_failure_is_neutral(monkeypatch):
    import numpy as np

    land = terrain.Terrain((), False, (None,) * 36, True)
    monkeypatch.setattr(terrain, "read", lambda crop: land)
    skill = DriveToBlip({})
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    assert skill.step(observation(frame=frame)).pad == NEUTRAL_PAD
    result = skill.step(observation(1, frame=frame))
    assert (result.reason, result.pad) == ("water", NEUTRAL_PAD)


def test_real_driver_exhausts_recovery_when_held():
    skill = DriveToBlip({"mode": "catch"})
    states = set()
    for i in range(600):
        result = skill.step(observation(i / 10, moving=False))
        states.add(skill.state)
        if result.status != "running":
            break
    assert any(s.startswith("recovery") for s in states)
    assert (result.reason, result.pad) == ("vehicle-held", NEUTRAL_PAD)


def test_clock_regression_fails_neutral():
    skill = DriveToBlip({})
    skill.step(observation(10))
    result = skill.step(observation(9))
    assert (result.reason, result.pad) == ("invalid-time", NEUTRAL_PAD)


def test_unknown_motion_cannot_confirm_arrival():
    skill = DriveToBlip({"mode": "reach"})
    marker = (Blip("blue", 0.0, 5.0),)
    assert skill.step(observation(0, blips=marker, moving=False)).status == "running"
    for t in (0.4, 0.8, 1.2):
        result = skill.step(observation(t, blips=marker, moving=None))
        assert result.status == "running"
        assert result.pad == NEUTRAL_PAD
    assert skill.step(observation(1.3, blips=marker, moving=False)).status == "running"
    assert skill.step(observation(1.7, blips=marker, moving=False)).status == "running"
    result = skill.step(observation(1.8, blips=marker, moving=False))
    assert (result.status, result.reason, result.pad) == ("done", "reached", NEUTRAL_PAD)


def test_water_without_dry_escape_fails_neutrally(monkeypatch):
    import numpy as np

    land = terrain.Terrain((), False, (10.0,) * 36, False)
    monkeypatch.setattr(terrain, "read", lambda *_: land)
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    skill = DriveToBlip({"mode": "catch"})
    for t in (0.0, 1.0, 2.0, 3.9):
        result = skill.step(observation(t, frame=frame, moving=False))
        assert result.status == "running"
        assert result.pad == NEUTRAL_PAD
    result = skill.step(observation(4.0, frame=frame, moving=False))
    assert (result.status, result.reason, result.pad) == ("failed", "vehicle-held", NEUTRAL_PAD)
    assert skill.step(observation(4.1)) is result


def test_dry_escape_resets_blocked_water_deadline(monkeypatch):
    import numpy as np

    wet = terrain.Terrain((), False, (10.0,) * 36, False)
    dry = terrain.Terrain((), False, (None,) * 36, False)
    land = wet
    monkeypatch.setattr(terrain, "read", lambda *_: land)
    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    skill = DriveToBlip({"mode": "catch"})
    assert skill.step(observation(0, frame=frame)).status == "running"
    land = dry
    assert skill.step(observation(3, frame=frame)).status == "running"
    land = wet
    assert skill.step(observation(4, frame=frame)).status == "running"
    assert skill.step(observation(7.9, frame=frame)).status == "running"
    result = skill.step(observation(8, frame=frame))
    assert (result.status, result.reason, result.pad) == ("failed", "vehicle-held", NEUTRAL_PAD)
