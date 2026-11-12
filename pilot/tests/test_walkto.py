"""Behaviour tests for walking to a point on foot."""

import math
from dataclasses import replace
from types import SimpleNamespace

import pytest

from pilot.contract import NEUTRAL_PAD, Blip, Observation, Reading
from pilot.walkto import WalkTo


def observation(time, x=20, y=30, *, border=False, color="purple", moving=True, **kw):
    reading = Reading("flat", "none", None, None, 0, False, 1.0, blips=(Blip(color, x, y, border),))
    return Observation(replace(reading, **kw), moving, time)


def test_direct_direction_default_waypoint_and_nearest_colour():
    skill = WalkTo({})
    result = skill.step(observation(0, 30, 40))
    assert result.pad.left == pytest.approx((0.6, -0.8))
    skill = WalkTo({"color": "yellow"})
    obs = observation(0, blips=(Blip("purple", 1, 1), Blip("yellow", -20, 0), Blip("yellow", 0, 40)))
    assert skill.step(obs).pad.left == (-1, 0)


def test_arrival_needs_stable_interior_blip_and_neutral_pads():
    skill = WalkTo({})
    for time in (0, 0.3):
        result = skill.step(observation(time, 2, 1))
        assert result.status == "running"
        assert result.pad == NEUTRAL_PAD
    result = skill.step(observation(0.7, 2, 1))
    assert result.status == "done"
    assert "start=2.24px" in result.reason and "end=2.24px" in result.reason
    assert result.pad == NEUTRAL_PAD
    assert skill.step(observation(1, 50, 50)) == result


def test_rim_is_never_arrival_or_metric_distance():
    skill = WalkTo({})
    for time in (0, 0.5, 1, 1.5):
        result = skill.step(observation(time, 1, 1, border=True))
        assert result.status == "running"
        assert "direction only" in result.reason
    assert "metres" in result.reason


@pytest.mark.parametrize("bad", ["corrupt", "missing", "stale", "gap"])
def test_bad_tick_breaks_arrival_evidence(bad):
    skill = WalkTo({})
    skill.step(observation(0, 2, 0))
    tick = observation(0.4, 2, 0)
    if bad == "corrupt":
        tick = replace(tick, reading=replace(tick.reading, corrupt=True))
    elif bad == "missing":
        tick = replace(tick, reading=None)
    elif bad == "stale":
        tick = replace(tick, time=0)
    else:
        tick = replace(tick, time=1.1)
    result = skill.step(tick)
    assert result.pad == NEUTRAL_PAD and result.status == "running"
    result = skill.step(observation(tick.time + 0.3, 2, 0))
    assert result.status == "running"


def test_no_blip_and_lost_blip_have_distinct_neutral_failures():
    for initially_present in (False, True):
        skill = WalkTo({})
        skill.step(observation(0, blips=(Blip("purple", 60, 0),) if initially_present else ()))
        for time in (0.5, 1, 1.5, 2, 2.5, 3.1):
            result = skill.step(observation(time, blips=()))
        assert result.status == "failed" and result.pad == NEUTRAL_PAD
        assert ("blip lost" if initially_present else "no matching blip") in result.reason
        assert "start=" in result.reason and "end=" in result.reason


def test_vehicle_transition_never_receives_walk_input_and_one_odd_tick_recovers():
    skill = WalkTo({})
    skill.step(observation(0))
    assert skill.step(replace(observation(0.2), mode="vehicle")).pad == NEUTRAL_PAD
    assert skill.step(observation(0.4)).pad.left != (0, 0)
    for time in (0.6, 1, 1.3):
        result = skill.step(replace(observation(time), mode="vehicle"))
        assert result.pad == NEUTRAL_PAD
    assert result.status == "failed" and "no longer on foot" in result.reason


def test_real_guard_exhaustion_and_sprint_only_while_walking():
    skill = WalkTo({"sprint": True})
    states = set()
    for tick in range(200):
        result = skill.step(observation(tick / 10, moving=False))
        states.add(skill.guard.state)
        if skill.guard.state == "escape":
            assert result.pad.buttons == ()
        if result.status != "running":
            break
    assert "escape" in states
    assert result.status == "failed" and "guard exhausted" in result.reason
    assert result.pad == NEUTRAL_PAD


def test_hard_limit_stop_and_replacement_are_neutral():
    skill = WalkTo({"duration": 1})
    skill.step(observation(0))
    result = skill.step(observation(1))
    assert result.status == "failed" and result.pad == NEUTRAL_PAD
    assert "time limit" in result.reason
    assert WalkTo({}).stop("replaced").pad == NEUTRAL_PAD


def test_road_fallback_requires_two_blocks_and_leaves_road_away(monkeypatch):
    road = SimpleNamespace(along=45, bearing=45, distance=2)
    monkeypatch.setattr("pilot.walkto.road_position", lambda _: road)
    skill = WalkTo({})
    skill.guard.failures = 1
    skill.step(observation(0, 20, 30))
    assert not skill.road_mode
    skill.guard.failures = 2
    skill.step(observation(0.2, 20, 30))
    assert skill.road_mode
    skill.step(observation(0.4, 40, 60))
    assert not skill.road_mode


@pytest.mark.parametrize(
    "args",
    [
        {"duration": True},
        {"radius": "4"},
        {"duration": math.inf},
        {"radius": math.nan},
        {"color": "pink"},
        {"sprint": 1},
        {"x": 1},
        None,
    ],
)
def test_invalid_arguments(args):
    with pytest.raises(ValueError):
        WalkTo(args)


def test_clamped_limits_and_bounded_prompt():
    skill = WalkTo({"duration": 1000, "radius": -1})
    assert skill.duration == 180 and skill.radius == 1
    assert len(skill.prompt) <= 400


def test_unfitted_road_tangent_keeps_safe_direct_walking(monkeypatch):
    monkeypatch.setattr("pilot.walkto.road_position", lambda _: SimpleNamespace(along=None))
    skill = WalkTo({})
    skill.guard.failures = 2
    assert skill.step(observation(0, 30, 40)).pad.left == pytest.approx((0.6, -0.8))


def test_persistent_nonfoot_reading_fails_without_pressing():
    skill = WalkTo({})
    for time in (0, 0.3, 0.7):
        result = skill.step(observation(time, minimap="none"))
        assert result.pad == NEUTRAL_PAD
    assert result.status == "failed" and "no longer on foot" in result.reason


def test_low_confidence_is_nondecisive_and_breaks_arrival():
    skill = WalkTo({})
    skill.step(observation(0, 1, 0))
    result = skill.step(observation(0.7, 1, 0, confidence=0.1))
    assert result.pad == NEUTRAL_PAD and result.status == "running"
    assert skill.step(observation(0.8, 1, 0)).status == "running"


def test_purple_route_without_blip_is_not_a_waypoint_arrival():
    skill = WalkTo({})
    for tick in range(32):
        result = skill.step(observation(tick / 10, blips=(), route="purple", bearing=0))
    assert result.status == "failed" and "no matching blip" in result.reason
    assert result.pad == NEUTRAL_PAD


def test_model_town_fallback_improves_arrivals_and_safe_failures():
    import runpy
    from pathlib import Path

    model = runpy.run_path(str(Path(__file__).parents[2] / "lab/walkto/model.py"))
    results = {
        name: [model["run_case"](case, fallback) for fallback in (False, True)]
        for name, case in model["CASES"].items()
    }
    direct = sum(pair[0]["status"] == "done" for pair in results.values())
    road = sum(pair[1]["status"] == "done" for pair in results.values())
    assert road > direct
    for name in ("vanishing blip", "enters car"):
        assert all(result["status"] == "failed" for result in results[name])


def test_frozen_picture_with_new_timestamp_cannot_prove_arrival():
    import numpy as np

    skill = WalkTo({})
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    skill.step(replace(observation(0, 1, 0), frame=frame))
    result = skill.step(replace(observation(0.7, 1, 0), frame=frame))
    assert result.status == "running" and result.pad == NEUTRAL_PAD
    assert skill.step(replace(observation(0.8, 1, 0), frame=frame + 1)).status == "running"


def test_the_waypoint_marker_is_read_from_the_frame_when_the_reading_has_no_purple_blip():
    from pathlib import Path

    import cv2
    import numpy as np

    hud = cv2.cvtColor(
        cv2.imread(str(Path(__file__).parents[2] / "lab/walkto/hud-waypoint-corner-day.png")),
        cv2.COLOR_BGR2RGB,
    )
    frame = np.zeros((720, 1280, 3), np.uint8)
    frame[530:700, 30:290] = hud
    skill = WalkTo({})
    result = skill.step(replace(observation(0, blips=()), frame=frame))
    assert result.status == "running" and "rim" in result.reason
    assert result.pad.left == pytest.approx((0.71, -0.70), abs=0.03)
    # Another colour is never taken from the frame.
    skill = WalkTo({"color": "yellow"})
    assert skill.step(replace(observation(0, blips=()), frame=frame)).pad == NEUTRAL_PAD


def test_a_near_waypoint_the_game_takes_off_the_map_is_reached_and_a_far_one_is_lost():
    for x, status, word, last in (
        (33, "done", "took the near waypoint", 6.0),
        (60, "failed", "blip lost", 3.0),
    ):
        skill = WalkTo({})
        skill.step(observation(0, x, 0))
        pads = {}
        for tick in range(1, 14):
            time = min(tick * 0.5, last)
            result = skill.step(observation(time, blips=()))
            pads[time] = result.pad
            if result.status != "running":
                break
        assert time == last and result.status == status and word in result.reason
        assert result.pad == NEUTRAL_PAD
        # A near marker that goes is walked on to; a far one only as long as an icon may hide it.
        assert (pads[2.5] != NEUTRAL_PAD) == (x == 33) and pads[1.5] != NEUTRAL_PAD
    # A marker on the rim that goes is never an arrival, however short its line to the arrow.
    skill = WalkTo({})
    skill.step(observation(0, 10, 0, border=True))
    for time in (0.9, 1.8, 2.7, 3.1):
        result = skill.step(observation(time, blips=()))
    assert result.status == "failed"


def test_roads_first_follows_the_way_on_the_map_and_goes_straight_for_the_last_steps(monkeypatch):
    import pilot.walkto as walkto

    asked = []
    monkeypatch.setattr(walkto, "way_by_road", lambda crop, x, y: asked.append((x, y)) or (90.0, True))
    skill = WalkTo({"roads": True})
    result = skill.step(observation(0, 0, 60))
    assert asked == [(0, 60)]
    assert result.pad.left == pytest.approx((1, 0), abs=1e-6)
    assert "following road" in result.reason and "on a road" in result.reason
    # Within the last pixels the map is not asked any more.
    result = skill.step(observation(0.2, 0, 10))
    assert len(asked) == 1 and result.pad.left == pytest.approx((0, -1), abs=1e-6)
    # Without the switch the map is never asked.
    plain = WalkTo({})
    assert plain.step(observation(0, 0, 60)).pad.left == pytest.approx((0, -1), abs=1e-6)
    assert len(asked) == 1 and "on a road" not in plain.step(observation(0.1, 0, 60)).reason


def test_roads_first_walks_straight_where_the_map_gives_no_way(monkeypatch):
    import pilot.walkto as walkto

    monkeypatch.setattr(walkto, "way_by_road", lambda crop, x, y: None)
    result = WalkTo({"roads": True}).step(observation(0, 30, 40))
    assert result.pad.left == pytest.approx((0.6, -0.8))
    assert result.reason.startswith("walking")


def test_another_way_is_taken_only_after_it_was_found_several_times_running(monkeypatch):
    import pilot.walkto as walkto

    ways = iter([0.0, 180.0, 0.0, 180.0, 180.0, 180.0, 180.0, 180.0, 180.0, 180.0])
    monkeypatch.setattr(walkto, "way_by_road", lambda crop, x, y: (next(ways), True))
    skill = WalkTo({"roads": True})
    sticks = [skill.step(observation(tick * 0.2, 60, 60)).pad.left[1] for tick in range(10)]
    # Up for as long as the other way only flickers, and through its first five looks in a row.
    assert sticks[:8] == pytest.approx([-1.0] * 8)
    assert sticks[8:] == pytest.approx([1.0, 1.0])


def test_roads_must_be_a_boolean():
    with pytest.raises(ValueError):
        WalkTo({"roads": "yes"})
    assert WalkTo.name == "walk_to_point" and len(WalkTo.prompt) <= 400


def test_the_walk_keeps_its_direction_for_a_moment_while_the_marker_is_hidden():
    skill = WalkTo({})
    pushed = skill.step(observation(0, 60, 0)).pad.left
    assert pushed == pytest.approx((1, 0))
    assert skill.step(observation(0.5, blips=())).pad.left == pytest.approx((1, 0))
    assert skill.step(observation(1.4, blips=())).pad.left == pytest.approx((1, 0))
    assert skill.step(observation(2.2, blips=())).pad == NEUTRAL_PAD
    # Nothing is pushed for a marker that has never been seen.
    assert WalkTo({}).step(observation(0, blips=())).pad == NEUTRAL_PAD


def test_a_tick_that_says_nothing_does_not_stop_a_running_figure():
    skill = WalkTo({"sprint": True})
    pushed = skill.step(observation(0, 60, 0)).pad
    assert pushed.left == pytest.approx((1, 0))
    damaged = observation(0.1, 60, 0, corrupt=True)
    assert skill.step(damaged).pad == pushed
    assert skill.step(replace(observation(0.2, 60, 0), reading=None)).pad == pushed
    # Not for longer than half a second, and never before anything was pushed.
    assert skill.step(observation(0.8, 60, 0, corrupt=True)).pad == NEUTRAL_PAD
    assert WalkTo({}).step(observation(0, 60, 0, corrupt=True)).pad == NEUTRAL_PAD
