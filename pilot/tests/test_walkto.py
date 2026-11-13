"""Behaviour tests for walking to a point on foot."""

import math
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from pilot.contract import NEUTRAL_PAD, Blip, Observation, Reading
from pilot.walkto import WalkTo
from pilot.waymark import find_waypoint


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
    # A figure knocked down is called anything but on foot and is up again in a few seconds: with
    # the map still on the screen the walk waits four, the stick let go, and then ends.
    for tick in range(6, 50):
        result = skill.step(replace(observation(tick / 10), mode="vehicle"))
        assert result.pad == NEUTRAL_PAD
        if result.status != "running":
            break
    assert result.status == "failed" and "no longer on foot" in result.reason
    assert tick / 10 == pytest.approx(0.6 + WalkTo.KNOCKED, abs=0.15)
    # Up again within that time, it walks on.
    skill = WalkTo({})
    skill.step(observation(0))
    for tick in range(1, 30):
        assert skill.step(replace(observation(tick / 10), mode="vehicle")).status == "running"
    assert skill.step(observation(3.0)).pad.left != (0, 0)
    # With no map on the screen it is a menu or a cutscene, and the walk ends at once.
    skill = WalkTo({})
    skill.step(observation(0))
    for tick in range(1, 12):
        result = skill.step(observation(tick / 10, minimap="none"))
        assert result.pad == NEUTRAL_PAD
        if result.status != "running":
            break
    assert result.status == "failed" and "no longer on foot" in result.reason and tick / 10 < 0.8


def test_a_figure_that_gets_nowhere_climbs_then_goes_round_and_gives_up_with_both_sides_closed():
    skill = WalkTo({"sprint": True})
    states, pressed = [], {}
    for tick in range(200):
        result = skill.step(observation(tick / 10, moving=False))
        state = skill.guard.state
        if not states or states[-1] != state:
            states.append(state)
        pressed.setdefault(state, set()).update(result.pad.buttons)
        if result.status != "running":
            break
    assert states == ["go", "climb", "round", "failed"]
    # The climb is one press of Square and no sprint; the way round is run like the way itself.
    assert pressed["climb"] == {"square"} and pressed["round"] == {"cross"}
    assert result.status == "failed" and "guard exhausted" in result.reason
    # Climb, both sides, back out: nothing moved, and after nine seconds the walk says so.
    assert result.pad == NEUTRAL_PAD and tick / 10 < 10


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
    skill = WalkTo({"roads": False})
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
    for time in (0, 0.3, 0.7, 1.5, 2.3, 3.1):
        result = skill.step(observation(time, minimap="none"))
        assert result.pad == NEUTRAL_PAD
    assert result.status == "failed" and "no longer on foot" in result.reason


def test_a_map_misread_before_the_first_step_is_waited_out():
    # Right after the camera is touched the reader may call the map tilted while the figure stands.
    skill = WalkTo({})
    for tick in range(60):
        result = skill.step(observation(tick / 30, 60, 0, minimap="tilted"))
        assert result.status == "running" and result.pad == NEUTRAL_PAD
    assert skill.step(observation(2.0, 60, 0)).pad.left != (0, 0)
    # Once the walk has stepped, the same reading is waited out for four seconds and no longer.
    for tick in range(1, 150):
        result = skill.step(observation(2.0 + tick / 30, 60, 0, minimap="tilted"))
        assert result.pad == NEUTRAL_PAD
        if result.status != "running":
            break
    assert result.status == "failed" and "no longer on foot" in result.reason
    assert tick / 30 == pytest.approx(WalkTo.KNOCKED, abs=0.1)


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
    skill = WalkTo({"roads": False})
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
    monkeypatch.setattr(walkto, "way_by_road", lambda crop, x, y, **kw: asked.append((x, y)) or (90.0, True))
    skill = WalkTo({"roads": True})
    result = skill.step(observation(0, 0, 60))
    assert asked == [(0, 60)]
    assert result.pad.left == pytest.approx((1, 0), abs=1e-6)
    assert "following road" in result.reason and "on a road" in result.reason
    # Within the last pixels the map is not asked any more.
    result = skill.step(observation(0.4, 0, 10))
    assert len(asked) == 1 and result.pad.left == pytest.approx((0, -1), abs=1e-6)
    # With the switch off the map is never asked.
    plain = WalkTo({"roads": False})
    assert plain.step(observation(0, 0, 60)).pad.left == pytest.approx((0, -1), abs=1e-6)
    assert len(asked) == 1 and "on a road" not in plain.step(observation(0.1, 0, 60)).reason


def test_roads_first_walks_straight_where_the_map_gives_no_way(monkeypatch):
    import pilot.walkto as walkto

    monkeypatch.setattr(walkto, "way_by_road", lambda crop, x, y, **kw: None)
    result = WalkTo({"roads": True}).step(observation(0, 30, 40))
    assert result.pad.left == pytest.approx((0.6, -0.8))
    assert result.reason.startswith("walking")


def test_another_way_is_taken_only_after_it_was_found_several_times_running(monkeypatch):
    import pilot.walkto as walkto

    ways, kept = iter([0.0, 180.0, 0.0, *[180.0] * 9]), []

    def planner(crop, x, y, *, side=False, keep=None):
        kept.append(keep)
        return next(ways), True

    monkeypatch.setattr(walkto, "way_by_road", planner)
    skill = WalkTo({"roads": True})
    sticks = [skill.step(observation(tick * 0.2, 60, 60)).pad.left[1] for tick in range(12)]
    # Up for as long as the other way only flickers, and until it was found five times running.
    assert sticks[:7] == pytest.approx([-1.0] * 7)
    # Then the stick comes round to it as a thumb does, in three fifths of a second, and stays.
    assert -1.0 < sticks[7] < sticks[8] < 1.0 and sticks[9:] == pytest.approx([1.0, 1.0, 1.0])
    # The first look has no way to keep; every later one is told the way being walked.
    assert kept[0] is None and kept[1:8] == pytest.approx([0.0] * 7) and kept[-1] == pytest.approx(180.0)


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
    assert skill.step(damaged).pad.left == pushed.left
    assert skill.step(observation(0.2, 60, 0, confidence=0.3)).pad.left == pushed.left
    # Not for longer than a second, and never before anything was pushed.
    assert skill.step(observation(0.8, 60, 0, corrupt=True)).pad.left == pushed.left
    assert skill.step(observation(1.3, 60, 0, corrupt=True)).pad == NEUTRAL_PAD
    assert WalkTo({}).step(observation(0, 60, 0, corrupt=True)).pad == NEUTRAL_PAD
    # Not into a screen without a map, not without a reading, and not on a tick out of its order.
    for bad in (
        observation(0.2, 60, 0, minimap="none", confidence=0.0),
        replace(observation(0.2, 60, 0), reading=None),
        observation(0.05, 60, 0, corrupt=True),
    ):
        skill = WalkTo({})
        skill.step(observation(0, 60, 0))
        skill.step(observation(0.1, 60, 0))
        assert skill.step(bad).pad == NEUTRAL_PAD


def test_a_tick_that_says_nothing_never_sends_again_what_the_walk_has_let_go_of():
    # The figure is taken into a car: the walk stands, and a damaged tick after it stays neutral.
    skill = WalkTo({})
    skill.step(observation(0, 60, 0))
    skill.step(observation(0.03, 60, 0))
    assert skill.step(observation(0.07, blips=(), minimap="tilted")).pad == NEUTRAL_PAD
    assert skill.step(observation(0.10, blips=(), minimap="tilted", corrupt=True)).pad == NEUTRAL_PAD
    # Inside the radius the walk stands, and stays standing over a damaged tick.
    skill = WalkTo({})
    assert skill.step(observation(0, 6, 0)).pad != NEUTRAL_PAD
    assert skill.step(observation(0.03, 3, 0)).pad == NEUTRAL_PAD
    assert skill.step(observation(0.07, 3, 0, corrupt=True)).pad == NEUTRAL_PAD


def test_damaged_ticks_between_do_not_put_off_no_longer_on_foot():
    skill = WalkTo({})
    skill.step(observation(0, 30, 0))
    for tick in range(1, 60):
        result = skill.step(observation(tick / 30, blips=(), minimap="none", corrupt=tick % 2 == 0))
        if result.status != "running":
            break
    assert result.status == "failed" and "no longer on foot" in result.reason and tick / 30 < 0.8


def test_time_without_a_readable_picture_is_no_proof_that_the_waypoint_was_reached():
    # Eight seconds with no map on the screen after a near marker, then one tick on foot without it.
    skill = WalkTo({})
    skill.step(observation(0, 35, 0))
    for tick in range(1, 240):
        result = skill.step(observation(tick / 30, blips=(), minimap="none", confidence=0.0))
        assert result.pad == NEUTRAL_PAD
    assert result.status == "failed" and "no longer on foot" in result.reason
    # The same with damaged pictures only: the walk gives up, it does not arrive.
    skill = WalkTo({})
    skill.step(observation(0, 35, 0))
    for tick in range(1, 240):
        result = skill.step(observation(tick / 30, 35, 0, corrupt=True))
        if result.status != "running":
            break
    assert result.status == "failed" and "nothing readable" in result.reason


def test_after_a_gap_in_the_ticks_nothing_old_is_pushed_and_nothing_old_counts_as_reached():
    skill = WalkTo({})
    assert skill.step(observation(0, 30, 0)).pad != NEUTRAL_PAD
    assert skill.step(observation(4.0, blips=())).pad == NEUTRAL_PAD
    for tick in range(1, 100):
        result = skill.step(observation(4.0 + tick / 30, blips=()))
        assert result.pad == NEUTRAL_PAD
        if result.status != "running":
            break
    assert result.status == "failed" and "blip lost" in result.reason


def test_the_camera_is_touched_first_where_the_figure_is_not_seen_in_its_place():
    from pilot.contract import Detection

    hidden = replace(observation(0, 60, 0), objects_time=0.0)
    skill = WalkTo({})
    first = skill.step(hidden)
    assert first.pad.left == (0.0, 0.0) and first.pad.right[0] > 0 and first.pad.buttons == ()
    assert skill.step(replace(observation(0.3, 60, 0), objects_time=0.3)).pad == NEUTRAL_PAD
    assert skill.step(replace(observation(0.5, 60, 0), objects_time=0.5)).pad.left == pytest.approx((1, 0))
    # With the figure in its place, and where no detector runs, the walk sets off on its first tick.
    figure = Detection("person", (600.0, 300.0, 680.0, 520.0), 0.9)
    seen = replace(observation(0, 60, 0), objects_time=0.0, figure=figure)
    assert WalkTo({}).step(seen).pad.left == pytest.approx((1, 0))
    assert WalkTo({}).step(observation(0, 60, 0)).pad.left == pytest.approx((1, 0))


def test_a_way_is_kept_as_its_angle_to_the_target_so_a_turning_camera_does_not_make_it_another(monkeypatch):
    import pilot.walkto as walkto

    # The camera turns by 80 degrees between two looks: the target and the way turn with it.
    looks = iter([(20.0, True), (100.0, True)])
    monkeypatch.setattr(walkto, "way_by_road", lambda crop, x, y, **kw: next(looks))
    skill = WalkTo({})
    first = skill.step(observation(0, 0, 60)).pad.left
    second = skill.step(observation(0.3, 59.09, 10.42)).pad.left
    assert first == pytest.approx((math.sin(math.radians(20)), -math.cos(math.radians(20))))
    assert second == pytest.approx((math.sin(math.radians(100)), -math.cos(math.radians(100))), abs=1e-3)


def test_what_the_skill_does_unless_told_otherwise_and_what_the_runner_is_told():
    skill = WalkTo({})
    assert (skill.sprint, skill.roads, skill.side, skill.exact) == (True, True, False, True)
    assert WalkTo({"duration": 10}).limit == 10
    pressed = {skill.step(observation(tick / 30, 60, 0)).pad.buttons for tick in range(30)}
    assert pressed == {(), ("cross",)}
    assert WalkTo({"sprint": False}).step(observation(0, 60, 0)).pad.buttons == ()
    with pytest.raises(ValueError):
        WalkTo({"side": 1})


def test_beside_a_purple_route_the_frame_is_not_searched_for_a_marker():
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
    assert skill.step(replace(observation(0, blips=(), route="purple"), frame=frame)).pad == NEUTRAL_PAD


def test_a_figure_out_of_breath_jogs_on_without_the_sprint_button():
    import cv2
    import numpy as np

    lab = Path(__file__).parents[2] / "lab/walkto"

    def picture(name, shade):
        frame = np.full((720, 1280, 3), shade, np.uint8)
        frame[670:684, 64:244] = cv2.cvtColor(cv2.imread(str(lab / f"bars-{name}.png")), cv2.COLOR_BGR2RGB)
        return frame

    skill = WalkTo({"roads": False})
    pressed = {"green": 0, "red": 0}
    for tick in range(150):
        name = "green-49s" if tick < 60 else "red-55s"
        result = skill.step(replace(observation(tick / 30, 60, 0), frame=picture(name, tick % 7)))
        assert result.status == "running" and result.pad.left == pytest.approx((1.0, 0.0))
        if tick < 60 or tick >= 90:
            pressed[name.split("-")[0]] += "cross" in result.pad.buttons
    assert pressed["green"] > 10 and pressed["red"] == 0
    assert "out of breath" in result.reason


def test_after_a_gap_in_the_ticks_the_guard_starts_afresh():
    skill = WalkTo({"roads": False})
    skill.step(observation(0, 60, 0))
    guard = skill.guard
    skill.step(observation(20, 60, 0))
    assert skill.guard is not guard and skill.guard.push_since is None


def place_frame(tick, symbol=None):
    """A frame whose map is bare ground, with a place's symbol at (x, y) from the arrow where given."""
    import numpy as np

    frame = np.zeros((720, 1280, 3), np.uint8)
    frame[0, 0] = tick % 251  # no two frames alike: a repeated frame says nothing
    hud = np.full((170, 260, 3), 100, np.uint8)
    if symbol is not None:
        cx, cy = 123 + round(symbol[0]), 117 - round(symbol[1])
        hud[cy - 5 : cy + 6, cx - 5 : cx - 1] = 0
        hud[cy + 2 : cy + 6, cx - 5 : cx + 6] = 0
    frame[530:700, 30:290] = hud
    return frame


def walk_to_a_place(symbol_at, args=None, ticks=80):
    """The marker stands 30 pixels ahead for three ticks and is then taken off the map by the game."""
    skill = WalkTo({"roads": False, **(args or {})})
    skill.guard._evidence = lambda observation: "going"
    results = {}
    for tick in range(ticks):
        time = tick / 10
        blips = (Blip("purple", 0, 30),) if tick < 3 else ()
        frame = place_frame(tick, symbol_at(time))
        results[time] = skill.step(replace(observation(time, blips=blips), frame=frame))
        if results[time].status != "running":
            break
    return skill, results


def test_the_walk_goes_on_to_the_symbol_under_a_waypoint_the_game_has_removed():
    # The map moves five pixels a second under a sprint, and the symbol with it.
    skill, results = walk_to_a_place(lambda time: (0, max(0.0, 30 - 5 * time)))
    last = max(results)
    assert results[last].status == "done" and results[last].pad == NEUTRAL_PAD
    assert "arrived; at the symbol under the waypoint" in results[last].reason
    # Not by the clock: it ends when the symbol is at the arrow, 21 pixels on at five a second,
    # and two more for what the map moved before the marker was known to be gone.
    assert last == pytest.approx(4.5, abs=0.4) and skill.end_distance <= WalkTo.AT_PLACE
    assert all(
        results[time].pad.left == pytest.approx((0, -1), abs=0.05) for time in results if 1 < time < last
    )


def test_a_symbol_the_arrow_comes_to_cover_is_reached_as_well():
    # The arrow hides what it stands on: ten pixels off, the symbol is seen for the last time.
    skill, results = walk_to_a_place(lambda time: (0, 30 - 5 * time) if 30 - 5 * time > 9.6 else None)
    last = max(results)
    assert results[last].status == "done" and "on the symbol under the waypoint" in results[last].reason
    assert last == pytest.approx(4.0 + WalkTo.SPOT_LOST / 10, abs=0.3)
    assert WalkTo.AT_PLACE < skill.end_distance <= WalkTo.AT_WALL
    # And it walked on until then.
    assert results[last - 0.3].pad.left == pytest.approx((0, -1), abs=0.05)


def test_a_waypoint_on_no_place_and_a_walk_told_not_to_look_for_one_go_by_the_clock():
    for symbol_at, args in ((lambda time: None, {}), (lambda time: (0, 30 - 5 * time), {"exact": False})):
        skill, results = walk_to_a_place(symbol_at, args)
        last = max(results)
        assert results[last].status == "done" and "took the near waypoint off the map" in results[last].reason
        assert not skill.spot_on and skill.spot_tries == (0 if args else WalkTo.SPOT_TRIES)


def test_held_up_a_few_steps_from_the_places_symbol_the_figure_is_there():
    # The place's own wall: the symbol stops eleven pixels off and the figure gets no nearer.
    def held(symbol_at, args=None):
        skill = WalkTo({"roads": False, **(args or {})})
        skill.guard._evidence = lambda observation: "going" if observation.time < 3.9 else "still"
        results = {}
        for tick in range(110):
            time = tick / 10
            blips = (Blip("purple", 0, 30),) if tick < 3 else ()
            frame = place_frame(tick, symbol_at(time))
            results[time] = skill.step(replace(observation(time, blips=blips), frame=frame))
            if results[time].status != "running":
                break
        return skill, results

    skill, results = held(lambda time: (0, max(10.5, 30 - 5 * time)))
    last = max(results)
    assert results[last].status == "done" and "arrived; held up" in results[last].reason
    assert "px from the place" in results[last].reason and results[last].pad == NEUTRAL_PAD
    # Not on the first sign of it: Square is tried first, and only when that takes nothing is the
    # figure at the place, a second and a half and a climb after it stopped.
    pressed = [time for time, result in results.items() if "square" in result.pad.buttons]
    assert pressed and last == pytest.approx(3.9 + 1.5 + 1.6, abs=0.4)
    # Further off it is an obstacle like another, and the walk goes round it. The symbol, which
    # stands still with the figure, is kept for when it is free again.
    skill, results = held(lambda time: (0, max(18.0, 30 - 5 * time)))
    assert all(result.status == "running" for result in results.values())
    assert skill.guard.state == "round" or skill.guard.rounds
    assert skill.spot_on and skill.followed


def test_what_stops_the_figure_short_of_a_marker_that_is_still_there_is_not_the_place():
    # A parked car thirteen pixels before a blip: the walk climbs and goes round, and ends nowhere.
    for args in ({"roads": False}, {"roads": False, "color": "yellow"}):
        skill = WalkTo(args)
        states = set()
        for tick in range(60):
            result = skill.step(
                observation(tick / 10, 0, 10, color=args.get("color", "purple"), moving=False)
            )
            states.add(skill.guard.state)
            assert result.status == "running"
        assert {"climb", "round"} <= states


def test_with_the_side_of_the_road_asked_for_the_walk_ends_off_the_carriageway(monkeypatch):
    import pilot.walkto as walkto

    lane = SimpleNamespace(position="lane", outward=90.0)
    beside = SimpleNamespace(position="side", outward=90.0)
    for ends, word, last in ((1.4, "; off the carriageway", 1.4), (99, "; still on the carriageway", 3.2)):
        now = {}
        monkeypatch.setattr(
            walkto, "road_position", lambda _, ends=ends, now=now: lane if now["t"] < ends else beside
        )
        skill = WalkTo({"side": True})
        pads = {}
        for tick in range(40):
            now["t"] = tick / 10
            result = skill.step(observation(tick / 10, 2, 1))
            pads[tick / 10] = result
            if result.status != "running":
                break
        assert result.status == "done" and result.pad == NEUTRAL_PAD
        assert "arrived; stable interior blip" + word in result.reason
        assert tick / 10 == pytest.approx(last, abs=0.15)
        # Arrived after 0.6 s, and from then on straight out of the lane, without the sprint.
        assert pads[1.0].reason == "stepping off the carriageway"
        assert pads[1.0].pad.left == pytest.approx((1.0, 0.0)) and not pads[1.0].pad.buttons
    # Where the figure already stands beside the road, or the side was not asked for, it ends at once.
    for args, road in (({"side": True}, beside), ({}, lane)):
        monkeypatch.setattr(walkto, "road_position", lambda _, road=road: road)
        skill = WalkTo(args)
        for time in (0, 0.3, 0.7):
            result = skill.step(observation(time, 2, 1))
        assert result.status == "done" and result.reason.startswith("arrived; stable interior blip; start=")


def turned(skill, bearing_at, until, *, hidden=()):
    """Steps a walk whose target stands at a map bearing that the test moves as the camera turns."""
    results = {}
    for tick in range(round(until * 10) + 1):
        time = tick / 10
        bearing = math.radians(bearing_at(time, results))
        blips = () if time in hidden else (Blip("purple", 60 * math.sin(bearing), 60 * math.cos(bearing)),)
        results[time] = skill.step(observation(time, blips=blips))
    return results


def test_a_target_behind_the_figure_is_brought_before_the_camera_before_the_first_step():
    # The camera turns 100 degrees a second while the right stick is out.
    def bearing_at(time, results):
        return 150.0 - 10.0 * sum(result.pad.right[0] > 0 for result in results.values())

    skill = WalkTo({"roads": False})
    results = turned(skill, bearing_at, 2.5)
    turning = [time for time, result in results.items() if result.pad.right != (0.0, 0.0)]
    assert turning[0] == 0.0 and turning == pytest.approx([tick / 10 for tick in range(len(turning))])
    for time in turning:
        assert results[time].pad.left == (0.0, 0.0) and not results[time].pad.buttons
        assert results[time].pad.right[0] > 0 and results[time].reason == "turning the camera to the target"
    # It ends with the target within 25 degrees of straight ahead, and the walk begins there.
    first = results[turning[-1] + 0.1]
    assert first.pad.right == (0.0, 0.0) and first.pad.left[1] < -0.9 and abs(first.pad.left[0]) < 0.45
    # Once it walks, the camera is the game's: a target that comes to lie behind is walked to.
    for tick in range(26, 36):
        behind = skill.step(observation(tick / 10, 0, -60))
        assert behind.pad.right == (0.0, 0.0) and math.hypot(*behind.pad.left) == pytest.approx(1.0)
    assert behind.pad.left == pytest.approx((0.0, 1.0), abs=1e-6)


def test_the_turn_is_to_the_targets_side_goes_on_while_the_marker_is_hidden_and_has_an_end():
    # To the left for a target behind on the left; on the lower rim the marker goes unread.
    results = turned(WalkTo({"roads": False}), lambda time, results: -150.0, 1.0, hidden=(0.3, 0.4, 0.5))
    assert all(result.pad.right == (-1.0, 0.0) for result in results.values())
    assert all(result.pad.left == (0.0, 0.0) for result in results.values())
    # A camera that does not come round is not waited for: after two and a half seconds it walks.
    results = turned(WalkTo({"roads": False}), lambda time, results: 170.0, 3.0)
    assert results[2.4].pad.right == (1.0, 0.0) and results[2.6].pad.right == (0.0, 0.0)
    assert results[2.6].pad.left == pytest.approx((math.sin(math.radians(170)), 0.985), abs=0.01)
    # A target at the side or ahead is walked to at once.
    results = turned(WalkTo({"roads": False}), lambda time, results: 95.0, 0.2)
    assert results[0.0].pad.right == (0.0, 0.0) and results[0.0].pad.left[0] > 0.9


def test_the_stick_comes_round_to_a_new_direction_and_does_not_jump_there():
    skill = WalkTo({"roads": False})
    assert skill.step(observation(0, 0, 60)).pad.left == pytest.approx((0.0, -1.0))
    # The target is suddenly at the right: 300 degrees a second, ten for a tick of a thirtieth.
    lefts = [skill.step(observation(tick / 30, 60, 0)).pad.left for tick in range(1, 12)]
    bearings = [math.degrees(math.atan2(left[0], -left[1])) for left in lefts]
    assert bearings[:9] == pytest.approx([10.0 * tick for tick in range(1, 10)], abs=0.5)
    assert bearings[9:] == pytest.approx([90.0, 90.0], abs=1e-6)
    assert all(math.hypot(*left) == pytest.approx(1.0) for left in lefts)
    # After a gap in the ticks nothing old is turned from: the first direction is the wanted one.
    skill.step(observation(20, 0, 60))
    assert skill.step(observation(20.1, -60, 0)).pad.left == pytest.approx((-1.0, 0.0))


def test_a_walk_under_way_goes_on_through_a_picture_called_damaged_while_it_finds_its_marker_there():
    import cv2
    import numpy as np

    hud = cv2.cvtColor(
        cv2.imread(str(Path(__file__).parents[2] / "lab/walkto/hud-waypoint-corner-day.png")),
        cv2.COLOR_BGR2RGB,
    )

    def tick(time, *, marked, corrupt=True):
        frame = np.zeros((720, 1280, 3), np.uint8)
        frame[0, 0] = round(time * 30) % 251
        frame[530:700, 30:290] = hud if marked else 70
        reading = {"corrupt": corrupt, "confidence": 0.3 if corrupt else 1.0}
        return replace(observation(time, blips=(), **reading), frame=frame)

    # Six seconds of a map the reader calls damaged, with the marker plain on it: the walk walks.
    skill = WalkTo({"roads": False})
    skill.guard._evidence = lambda observation: "going"
    first = skill.step(tick(0, marked=True, corrupt=False))
    assert first.pad.left == pytest.approx((0.71, -0.70), abs=0.03)
    for index in range(1, 181):
        result = skill.step(tick(index / 30, marked=True))
        assert result.status == "running" and result.pad.left == pytest.approx(first.pad.left, abs=0.03)
    # Without the marker such a picture says nothing: a second of the old direction, then the stick
    # is let go, and after five seconds the walk ends.
    skill = WalkTo({"roads": False})
    skill.step(tick(0, marked=True, corrupt=False))
    lefts = {index: skill.step(tick(index / 30, marked=False)) for index in range(1, 156)}
    assert lefts[20].pad.left != (0.0, 0.0) and lefts[45].pad == NEUTRAL_PAD
    assert lefts[155].status == "failed" and "nothing readable" in lefts[155].reason
    # And no walk begins on one: before the first step the damaged picture is waited out.
    skill = WalkTo({"roads": False})
    assert all(skill.step(tick(index / 30, marked=True)).pad == NEUTRAL_PAD for index in range(60))


def test_a_waypoint_that_is_nowhere_on_the_map_at_the_start_is_looked_for_by_turning_the_camera():
    # Straight behind the figure the marker is under the bars: nothing for half a second, then the
    # camera turns, here by 100 degrees a second, and the marker comes up the right side.
    def bearing_at(time, results):
        return 180.0 - 10.0 * sum(result.pad.right[0] > 0 for result in results.values())

    skill = WalkTo({"roads": False})
    hidden = tuple(tick / 10 for tick in range(12))
    results = turned(skill, bearing_at, 3.5, hidden=hidden)
    assert all(results[tick / 10].pad == NEUTRAL_PAD for tick in range(5))
    turning = [time for time, result in results.items() if result.pad.right != (0.0, 0.0)]
    assert turning[0] == pytest.approx(0.5) and all(results[time].pad.right[0] > 0 for time in turning)
    assert all(results[time].pad.left == (0.0, 0.0) for time in turning)
    # Found, it is brought before the camera as any target behind, and then walked to.
    first = results[turning[-1] + 0.1]
    assert first.status == "running" and first.pad.left[1] < -0.9 and first.pad.right == (0.0, 0.0)
    # A waypoint that is not set is not found by looking either: three seconds, and the walk ends.
    skill = WalkTo({"roads": False})
    for tick in range(32):
        result = skill.step(observation(tick / 10, blips=()))
    assert result.status == "failed" and "no matching blip" in result.reason and result.pad == NEUTRAL_PAD
    # Another colour is the minimap reader's to find, and is not looked for.
    skill = WalkTo({"roads": False, "color": "yellow"})
    assert all(skill.step(observation(tick / 10, blips=())).pad == NEUTRAL_PAD for tick in range(20))


def test_a_followed_symbol_that_comes_no_nearer_is_let_go_and_the_clock_decides():
    # Whatever stays where it is while the figure runs is part of the screen and not of the map.
    skill, results = walk_to_a_place(lambda time: (0, 26), ticks=140)
    last = max(results)
    assert results[last].status == "done" and "took the near waypoint off the map" in results[last].reason
    assert not skill.spot_on and skill.spot_tries == WalkTo.SPOT_TRIES
    # The clock has run since the marker went, thirty pixels short at five a second: the four
    # seconds spent on what did not move are not walked a second time.
    assert last == pytest.approx(0.3 + min(WalkTo.CARRY_MAX, 30 / WalkTo.SPRINT_PACE), abs=0.3)
    assert results[last - 0.3].pad.left == pytest.approx((0, -1), abs=0.05)


def damaged(time, hud, *, corrupt=True, mode=None):
    import numpy as np

    frame = np.zeros((720, 1280, 3), np.uint8)
    frame[0, 0] = round(time * 30) % 251
    frame[530:700, 30:290] = hud
    reading = {"corrupt": corrupt, "confidence": 0.3 if corrupt else 1.0}
    return replace(observation(time, blips=(), **reading), frame=frame, mode=mode)


def corner_hud():
    import cv2

    path = Path(__file__).parents[2] / "lab/walkto/hud-waypoint-corner-day.png"
    return cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)


def test_damaged_pictures_carry_a_walk_for_a_quarter_of_a_minute_and_never_to_an_arrival():
    hud = corner_hud()
    skill = WalkTo({"roads": False})
    skill.guard._evidence = lambda observation: "going"
    skill.step(damaged(0, hud, corrupt=False))
    ended = None
    for index in range(1, 30 * 22):
        result = skill.step(damaged(index / 30, hud))
        if result.status != "running":
            ended = index / 30
            break
    # Fifteen seconds by its own marker, a second of the old direction, and five of nothing.
    assert result.status == "failed" and "nothing readable" in result.reason
    assert ended == pytest.approx(WalkTo.DAMAGED_MAX + WalkTo.BLIND, abs=0.2)
    # A marker read near the arrow in a damaged picture is not walked to and not arrived at.
    near = hud.copy()
    near[87:107, 123:143] = hud[20:40, 202:222]
    near[20:40, 202:222] = hud[20:40, 180:200]
    read = find_waypoint(near)
    assert not read.border and math.hypot(read.x, read.y) < WalkTo.GONE_WITHIN
    skill = WalkTo({"roads": False})
    skill.guard._evidence = lambda observation: "going"
    skill.step(damaged(0, hud, corrupt=False))
    results = [skill.step(damaged(index / 30, near)) for index in range(1, 120)]
    assert all(result.status == "running" for result in results)
    assert results[10].pad.left != (0.0, 0.0) and all(result.pad == NEUTRAL_PAD for result in results[40:])


def test_nothing_is_kept_going_on_a_tick_that_says_nothing_while_the_figure_is_not_called_on_foot():
    hud = corner_hud()
    for kind in ("repeated", "damaged"):
        skill = WalkTo({"roads": False})
        first = damaged(0, hud, corrupt=False)
        assert skill.step(first).pad.left != (0.0, 0.0)
        tick = replace(first, time=0.05, mode="vehicle")
        if kind == "damaged":
            tick = replace(damaged(0.05, hud), mode="vehicle")
        assert skill.step(tick).pad == NEUTRAL_PAD


def test_a_way_that_is_neither_found_again_nor_replaced_is_not_kept_for_ever(monkeypatch):
    import pilot.walkto as walkto

    # Looks that agree neither with the way walked nor with each other.
    looks = iter([110.0, *[40.0, -40.0] * 20])
    monkeypatch.setattr(walkto, "way_by_road", lambda crop, x, y, **kw: (next(looks), True))
    skill = WalkTo({"roads": True})
    bearings = []
    for index in range(16):
        left = skill.step(observation(index * 0.2, 0, 60)).pad.left
        bearings.append(math.degrees(math.atan2(left[0], -left[1])))
    assert bearings[:10] == pytest.approx([110.0] * 10) and abs(bearings[-1]) == pytest.approx(40.0, abs=1)


def test_the_opening_turn_keeps_its_side_while_the_marker_flickers_straight_behind():
    results = turned(
        WalkTo({"roads": False}), lambda time, results: 179.0 if round(time * 10) % 2 else -179.0, 2.0
    )
    sides = {result.pad.right[0] for result in results.values()}
    assert sides == {-1.0} and all(result.pad.left == (0.0, 0.0) for result in results.values())


def test_the_step_off_the_carriageway_keeps_its_side_and_an_arrival_stays_one_at_the_time_limit(monkeypatch):
    import pilot.walkto as walkto

    # On the band's middle line the nearer edge is the left on one tick and the right on the next.
    flip = {"n": 0}

    def road(_):
        flip["n"] += 1
        return SimpleNamespace(position="lane", outward=90.0 if flip["n"] % 2 else -90.0)

    monkeypatch.setattr(walkto, "road_position", road)
    skill = WalkTo({"side": True, "duration": 2.0})
    lefts = []
    for index in range(40):
        result = skill.step(observation(index / 10, 2, 1))
        if result.reason == "stepping off the carriageway":
            lefts.append(result.pad.left)
        if result.status != "running":
            break
    assert len(lefts) > 5 and all(left == pytest.approx(lefts[0]) for left in lefts)
    # The walk's two seconds ran out while it stepped aside: it had arrived, and says so.
    assert result.status == "done" and result.reason.startswith("arrived; stable interior blip; still on")
