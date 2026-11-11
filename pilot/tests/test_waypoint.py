"""Safety boundaries and delayed visual feedback for the standalone waypoint skill."""

import importlib.util
import json
from dataclasses import replace
from itertools import pairwise
from pathlib import Path

import cv2
import numpy as np
import pytest

from pilot.contract import NEUTRAL_PAD, Hud, Reading
from pilot.scene import SceneText, TextLine
from pilot.skills import Observation
from pilot.waypoint import MapPicture, SetWaypoint, map_screen, read_map

FIXTURES = Path(__file__).parent / "fixtures" / "waypoint"
FRAMES = json.loads((FIXTURES / "frames.json").read_text())
spec = importlib.util.spec_from_file_location(
    "sim_waypoint", Path(__file__).parents[1] / "tools" / "sim_waypoint.py"
)
sim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sim)


def observation(time=0, screen="game", frame=None, route="none", corrupt=False):
    if frame is None:
        frame = np.full((720, 1280, 3), 20 if screen == "game" else 40, np.uint8)
    reading = Reading("tilted" if screen == "game" else "none", route, None, None, None, corrupt, 1.0)
    return Observation(reading, False, time, frame, hud=Hud(screen=screen))


@pytest.mark.parametrize("row", FRAMES, ids=lambda row: f"{row['recording']}-{row['i']}")
def test_recorded_map_and_other_screens(row):
    frame = cv2.cvtColor(cv2.imread(str(FIXTURES / row["file"])), cv2.COLOR_BGR2RGB)
    text = SceneText(tuple(TextLine(**line) for line in row["text"]))
    assert bool(map_screen(frame, text)) == (row["label"] == "map")
    if row["i"] in {8252, 8286, 8305}:
        picture = read_map(frame, text)
        assert picture.cursor == (640, 360)
        assert picture.waypoint == (row["i"] == 8305)
    if row["i"] == 8221:
        assert map_screen(frame, text) == "transition"


def test_other_selected_pause_tab_does_not_authorise_cross():
    frame = np.zeros((720, 1280, 3), np.uint8)
    frame[123:145, 355:490] = 240
    assert map_screen(frame, sim.map_text("overview")) is None
    assert map_screen(frame, SceneText()) is None


@pytest.mark.parametrize(
    "args",
    [
        None,
        [],
        {"extra": 1},
        {"target": []},
        {"target": "store"},
        {"duration": True},
        {"duration": "10"},
        {"duration": None},
        {"duration": float("inf")},
        {"duration": float("nan")},
    ],
)
def test_arguments_reject_non_contract_values(args):
    with pytest.raises(ValueError):
        SetWaypoint(args)


def test_metadata_clamping_and_stop_are_terminal():
    assert SetWaypoint({"duration": 100}).limit == 45
    assert SetWaypoint({"duration": -10}).limit == 1
    assert len(SetWaypoint.prompt) <= 400
    skill = SetWaypoint({})
    assert skill.step(observation()).pad.buttons == ("options",)
    result = skill.stop("replaced")
    assert result.status == "failed" and result.pad == NEUTRAL_PAD
    assert skill.step(observation(0.05)) == result


@pytest.mark.parametrize("target", ["mission", "away"])
@pytest.mark.parametrize("delay", [0.14, 0.6, 1.1])
def test_delayed_map_reaches_target_and_observes_game(target, delay):
    result = sim.simulate(target=target, delay=delay)
    assert result["status"] == "done", result["reason"]
    assert result["seconds"] <= 45
    assert result["trace"][-1]["screen"] == "game"
    presses = [row["pad"]["buttons"] for row in result["trace"]]
    options_edges = sum(
        "options" in p and (i == 0 or "options" not in presses[i - 1]) for i, p in enumerate(presses)
    )
    assert options_edges == 1
    assert all(set(p) <= {"options", "cross", "circle"} for p in presses)
    assert all(
        row["screen"] in {"map", "overview"} for row in result["trace"] if "cross" in row["pad"]["buttons"]
    )


@pytest.mark.parametrize("phase", sim.PHASES)
@pytest.mark.parametrize("screen", sim.WRONG_SCREENS)
def test_wrong_screen_at_every_step_fails_and_only_backs_out(phase, screen):
    result = sim.simulate(wrong_at=phase, wrong_screen=screen)
    assert result["injected"]
    assert result["status"] == "failed"
    assert result["seconds"] <= 45 and result["exits"] <= 3
    assert result["trace"][-1]["pad"] == {"buttons": (), "left": (0, 0), "right": (0, 0), "l2": 0, "r2": 0}


@pytest.mark.parametrize("phase", sim.PHASES)
def test_backout_that_does_not_work_is_bounded(phase):
    result = sim.simulate(wrong_at=phase, exit_works=False)
    assert result["injected"] and result["status"] == "failed"
    if phase == "open":
        # Nothing was opened, so nothing is backed out of.
        assert result["exits"] == 0 and "start-screen-unverified" in result["reason"]
        return
    assert result["exits"] == 3
    assert "not observed" in result["reason"]


def test_timeout_releases_a_held_button_and_never_retries_options():
    skill = SetWaypoint({"duration": 1})
    assert skill.step(observation()).pad.buttons == ("options",)
    assert skill.step(observation(0.05)).pad.buttons == ("options",)
    result = skill.step(observation(1))
    assert result.status == "failed" and result.pad == NEUTRAL_PAD
    assert "time-limit" in result.reason
    assert skill.step(observation(2)) == result


def test_clock_reversal_releases_pad():
    skill = SetWaypoint({})
    skill.step(observation(10))
    result = skill.step(observation(9.9))
    assert result.status == "failed" and result.pad == NEUTRAL_PAD


@pytest.mark.parametrize("screen", sim.WRONG_SCREENS)
def test_explicit_wrong_screen_releases_an_active_pulse(screen):
    if screen == "pause":
        return  # A selected map tab is a pause screen; its picture is checked at the next boundary.
    skill = SetWaypoint({})
    skill.step(observation())
    result = skill.step(observation(0.05, screen))
    assert result.pad == NEUTRAL_PAD and skill.failure.startswith("wrong-screen-during-input")


def test_identical_stale_frame_never_proves_return_to_game():
    skill = SetWaypoint({})
    original = observation()
    skill.step(original)
    result = skill.step(replace(original, time=1.5))
    assert result.pad == NEUTRAL_PAD and skill.failure.startswith("picture-unchanged")
    for now in np.arange(1.6, 8, 0.1):
        result = skill.step(replace(original, time=float(now)))
        assert set(result.pad.buttons) <= {"circle"}
    assert result.status == "failed" and result.pad == NEUTRAL_PAD
    assert "gameplay not observed" in result.reason


@pytest.mark.parametrize("frame,corrupt", [(None, False), (np.zeros((720, 1280, 3), np.uint8), True)])
def test_missing_or_damaged_picture_only_allows_backout(frame, corrupt):
    skill = SetWaypoint({})
    skill.step(observation())
    bad = replace(
        observation(1.5, "map"), frame=frame, reading=replace(observation().reading, corrupt=corrupt)
    )
    result = skill.step(bad)
    assert result.pad == NEUTRAL_PAD
    result = skill.step(replace(bad, time=1.6))
    assert result.pad.buttons == ("circle",)


def test_ocr_failure_does_not_leave_any_control_held():
    skill = SetWaypoint({})
    skill.step(observation())

    def broken(_):
        raise RuntimeError("OCR unavailable")

    skill._picture = broken
    result = skill.step(observation(1.5, "map"))
    assert result.pad == NEUTRAL_PAD and "picture-error" in skill.failure
    assert skill.step(observation(1.6, "map")).pad.buttons == ("circle",)


@pytest.mark.parametrize(
    "picture,reason",
    [
        (MapPicture("map"), "cursor"),
        (MapPicture("map", (640, 360)), "player"),
        (MapPicture("map", (640, 360), (640, 360)), "no-visible-mission"),
        (MapPicture("transition"), "map-check"),
    ],
)
def test_unverified_cursor_player_or_target_never_gets_a_forward_input(picture, reason):
    skill = SetWaypoint({})
    skill.phase = "acquire"
    skill._picture = lambda _: picture
    result = skill.step(observation(0, "map"))
    assert result.pad == NEUTRAL_PAD and reason in skill.failure
    assert skill.step(observation(0.1, "map")).pad.buttons == ("circle",)


def test_done_requires_new_waypoint_picture_and_purple_gameplay():
    skill = SetWaypoint({})
    skill.phase = "confirm"
    skill._picture = lambda _: MapPicture("map", (640, 360), waypoint=False)
    result = skill.step(observation(0, "map"))
    assert result.pad == NEUTRAL_PAD and skill.failure == "waypoint-not-visible-after-cross"
    skill = SetWaypoint({})
    skill.phase = "exit"
    result = skill.step(observation(route="purple"))
    assert result.status == "failed" and result.pad == NEUTRAL_PAD
    for route, seen in (("none", "no route yet"), ("purple", "route on the minimap")):
        skill = SetWaypoint({})
        skill.phase = "exit"
        skill.proved_waypoint = True
        result = skill.step(observation(route=route))
        assert result.status == "done" and seen in result.reason and result.pad == NEUTRAL_PAD


@pytest.mark.parametrize(
    "start",
    [observation(screen="failed"), observation(corrupt=True), replace(observation(), frame=None)],
    ids=["failed-screen", "damaged", "no-frame"],
)
def test_nothing_is_pressed_when_it_does_not_start_from_the_game(start):
    skill = SetWaypoint({})
    results = [skill.step(replace(start, time=tick / 10)) for tick in range(60)]
    assert all(result.pad == NEUTRAL_PAD for result in results)
    assert results[0].status == "failed" and "start-screen-unverified" in results[0].reason


def aiming(monkeypatch, points, waypoint=False):
    skill = SetWaypoint({})
    skill.phase, skill.point, skill.template = "aim", points[0], np.zeros((25, 25, 3), np.uint8)
    queue = iter(points)
    monkeypatch.setattr("pilot.waypoint._track", lambda *_: [next(queue)])
    skill._picture = lambda _: MapPicture("map", (640, 360), waypoint=waypoint)
    results = []
    for tick in range(450):
        frame = np.full((720, 1280, 3), 40 + tick % 200, np.uint8)
        results.append(skill.step(observation(tick / 10, "map", frame)))
        if results[-1].status != "running":
            break
    return skill, results


def pushes(results):
    held = [False, *(result.pad.left != (0.0, 0.0) for result in results)]
    return sum(now and not before for before, now in pairwise(held))


def test_a_cursor_that_does_not_approach_gets_one_push_and_no_cross(monkeypatch):
    skill, results = aiming(monkeypatch, [(740.0, 360.0)] * 40)
    assert pushes(results) == 1 and skill.failure.startswith("cursor-did-not-approach")
    assert all("cross" not in result.pad.buttons for result in results)


def test_cursor_moves_are_bounded(monkeypatch):
    skill, results = aiming(monkeypatch, [(900.0 - 3 * step, 360.0) for step in range(60)])
    assert pushes(results) == 16 and skill.failure == "cursor-move-limit"


def test_a_waypoint_already_under_the_cursor_is_not_toggled_off(monkeypatch):
    skill, results = aiming(monkeypatch, [(645.0, 360.0)] * 40, waypoint=True)
    assert skill.failure.startswith("existing-waypoint")
    assert all("cross" not in result.pad.buttons for result in results)


@pytest.mark.parametrize("phase", ["enter", "acquire", "aim", "confirm"])
def test_a_damaged_map_picture_is_not_acted_on(phase):
    skill = SetWaypoint({})
    skill.phase, skill.point, skill.template = phase, (700.0, 360.0), np.zeros((25, 25, 3), np.uint8)
    skill._picture = lambda _: MapPicture("map", (640, 360), waypoint=True)
    frame = np.full((720, 1280, 3), 40, np.uint8)
    result = skill.step(observation(0, "map", frame, corrupt=True))
    assert result.pad == NEUTRAL_PAD and skill.failure == "map-picture-missing-or-damaged"
    assert not skill.proved_waypoint


@pytest.mark.parametrize("key", ["direction", "distance"])
@pytest.mark.parametrize("value", [None, [], True, 1, "unknown"])
def test_away_arguments_reject_invalid_values(key, value):
    with pytest.raises(ValueError):
        SetWaypoint({"target": "away", key: value})


def test_any_rotates_without_changing_explicit_direction_or_mission():
    skills = [SetWaypoint({"target": "away"}) for _ in range(8)]
    assert all(a.direction != b.direction for a, b in pairwise(skills))
    assert set(skill.direction for skill in skills) == {"north", "east", "south", "west"}
    for name in SetWaypoint.directions:
        assert SetWaypoint({"target": "away", "direction": name}).direction == name
    assert SetWaypoint({}).target == "mission"


def away_picture_step(skill, world, now, corrupt=False):
    frame = world.frame()
    skill._picture = lambda image: read_map(image, sim.map_text("map"))
    return skill.step(observation(now, "map", frame, corrupt=corrupt))


@pytest.mark.parametrize("shift", [12, 30, 60])
def test_away_stops_on_measured_distance_without_player_or_fixed_push_count(shift):
    skill = SetWaypoint({"target": "away", "direction": "east"})
    skill.phase = "acquire"
    world = sim.MapWorld(markers=False)
    world.screen = "map"
    result = away_picture_step(skill, world, 0)
    assert result.pad.left == (0.65, 0)
    count = 0
    while "cross" not in result.pad.buttons:
        count += 1
        world.offset[0] -= shift
        result = away_picture_step(skill, world, count * 1.8)
        assert skill.failure is None
        if count * shift < skill.distance:
            assert "cross" not in result.pad.buttons
    assert count == int(np.ceil(skill.distance / shift))
    assert np.linalg.norm(skill.displacement) >= skill.distance


def test_unmoved_map_gets_exactly_one_different_direction_and_no_cross():
    skill = SetWaypoint({"target": "away", "direction": "east"})
    skill.phase = "acquire"
    world = sim.MapWorld(markers=False)
    world.screen = "map"
    first = away_picture_step(skill, world, 0)
    second = away_picture_step(skill, world, 1.5)
    failed = away_picture_step(skill, world, 3)
    assert first.pad.left == (0.65, 0)
    assert second.pad.left == (0, 0.65)
    assert failed.pad == NEUTRAL_PAD and skill.failure.startswith("map-unmoved-after-alternate")
    assert skill.moves == 2
    assert away_picture_step(skill, world, 3.1).pad.buttons == ("circle",)


@pytest.mark.parametrize("when", [0, 0.05, 0.5, 1.5])
def test_damaged_before_during_or_after_push_never_authorises_cross(when):
    skill = SetWaypoint({"target": "away", "direction": "east"})
    skill.phase = "acquire"
    world = sim.MapWorld(markers=False)
    world.screen = "map"
    if when:
        away_picture_step(skill, world, 0)
        world.offset[0] = -140
    result = away_picture_step(skill, world, when, corrupt=True)
    assert result.pad == NEUTRAL_PAD and skill.failure == "map-picture-missing-or-damaged"
    assert not skill.proved_waypoint


def test_unflagged_damage_or_textureless_map_cannot_count_as_motion():
    from pilot.waypoint import map_shift

    world = sim.MapWorld(markers=False)
    world.screen = "map"
    before = world.frame()
    world.offset[0] = -30
    after = world.frame()
    assert map_shift(before, after) == pytest.approx((-30, 0), abs=1)
    after[170:560, 240:980] = np.random.default_rng(4).integers(0, 256, (390, 740, 3), dtype=np.uint8)
    assert map_shift(before, after) is None
    assert map_shift(after, before) is None
    assert map_shift(np.zeros_like(before), before) is None


def test_sea_gets_one_inland_look_then_only_backout():
    result = sim.simulate(target="away", sea=True)
    assert result["status"] == "failed" and "sea" in result["reason"]
    assert not any("cross" in row["pad"]["buttons"] and row["screen"] == "map" for row in result["trace"])
    assert result["trace"][-1]["pad"]["left"] == (0, 0)
    directions = {row["pad"]["left"] for row in result["trace"] if row["pad"]["left"] != (0, 0)}
    assert directions == {(0.65, 0), (-0.65, 0)}


@pytest.mark.parametrize("case", [{"edge": True}, {"damaged": True}])
def test_away_faults_finish_neutral_after_circle_only_escape(case):
    result = sim.simulate(target="away", delay=1.1, **case)
    assert result["status"] == "failed"
    assert result["trace"][-1]["screen"] == "game"
    assert result["trace"][-1]["pad"]["buttons"] == ()
    assert not any("cross" in row["pad"]["buttons"] and row["screen"] == "map" for row in result["trace"])


def test_inland_second_look_can_set_on_land_after_reaching_requested_distance():
    skill = SetWaypoint({"target": "away", "direction": "east"})
    skill.phase = "acquire"
    world = sim.MapWorld(markers=False)
    world.screen = "map"
    away_picture_step(skill, world, 0)
    world.offset[0], world.sea = -120, True
    result = away_picture_step(skill, world, 1.5)
    assert result.pad.left == (-0.65, 0) and skill.inland_used
    world.offset[0], world.sea = -90, False
    result = away_picture_step(skill, world, 3)
    assert result.pad.buttons == ("cross",)
    assert np.linalg.norm(skill.displacement) == pytest.approx(90, abs=1)


def test_recorded_road_shift_excludes_fixed_scene_and_cursor():
    from pilot.waypoint import map_shift

    before = cv2.cvtColor(cv2.imread(str(FIXTURES / "20261110-093238-8252.png")), cv2.COLOR_BGR2RGB)
    after = cv2.cvtColor(cv2.imread(str(FIXTURES / "map-8255.png")), cv2.COLOR_BGR2RGB)
    assert map_shift(before, after) == pytest.approx((10.77, 2.26), abs=0.5)
    assert map_shift(after, before) == pytest.approx((-10.77, -2.26), abs=0.5)


def test_a_map_that_runs_the_other_way_turns_the_stick_once():
    skill = SetWaypoint({"target": "away", "direction": "east"})
    skill.phase = "acquire"
    world = sim.MapWorld(markers=False)
    world.screen = "map"
    assert away_picture_step(skill, world, 0).pad.left == (0.65, 0)
    world.offset[0] += 12
    result = away_picture_step(skill, world, 1.8)
    assert skill.failure is None and result.pad.left == (-0.65, 0)
    count = 1
    while "cross" not in result.pad.buttons:
        count += 1
        world.offset[0] -= 60
        result = away_picture_step(skill, world, count * 1.8)
        assert skill.failure is None
    assert skill.displacement[0] <= -skill.distance
    # Once the way is known, a map that turns round again is a fault and not a second guess.
    skill = SetWaypoint({"target": "away", "direction": "east"})
    skill.phase = "acquire"
    world = sim.MapWorld(markers=False)
    world.screen = "map"
    away_picture_step(skill, world, 0)
    world.offset[0] -= 12
    away_picture_step(skill, world, 1.8)
    world.offset[0] += 30
    result = away_picture_step(skill, world, 3.6)
    assert result.pad == NEUTRAL_PAD and skill.failure.startswith("map-shift-wrong-direction")


def away_at_first_push(direction="east"):
    skill = SetWaypoint({"target": "away", "direction": direction})
    skill.phase = "acquire"
    world = sim.MapWorld(markers=False)
    world.screen = "map"
    assert away_picture_step(skill, world, 0).pad.left != (0, 0)
    return skill, world


def test_a_pair_of_pictures_that_cannot_be_compared_ends_the_push_without_cross():
    skill, world = away_at_first_push()
    world.offset[0] -= 60
    frame = world.frame()
    cursor = frame[300:420, 580:700].copy()
    frame[170:560, 240:980] = np.random.default_rng(4).integers(0, 256, (390, 740, 3), dtype=np.uint8)
    frame[300:420, 580:700] = cursor  # the cursor is still read; only the map around it is gone
    skill._picture = lambda image: read_map(image, sim.map_text("map"))
    result = skill.step(observation(1.8, "map", frame))
    assert result.pad == NEUTRAL_PAD and skill.failure.startswith("map-shift-unverified")
    assert np.linalg.norm(skill.displacement) == 0


def test_a_map_that_creeps_runs_into_the_limit_of_pushes():
    skill, world = away_at_first_push()
    pushes = 1
    for step in range(1, 40):
        world.offset[0] -= 3
        result = away_picture_step(skill, world, step * 1.8)
        if skill.failure:
            break
        pushes += result.pad.left != (0, 0)
    assert pushes == 16 and skill.failure == "map-move-limit"
    assert "cross" not in result.pad.buttons


@pytest.mark.parametrize(("moved", "seconds"), [(12, 0.40), (24, 0.25), (60, 0.10)])
def test_the_next_push_is_as_long_as_the_measured_speed_asks(moved, seconds):
    skill, world = away_at_first_push()
    world.offset[0] -= moved
    result = away_picture_step(skill, world, 1.8)
    assert result.pad.left == (0.65, 0) and skill.push_seconds == pytest.approx(seconds)
    held = away_picture_step(skill, world, 1.8 + seconds - 0.02)
    released = away_picture_step(skill, world, 1.8 + seconds + 0.02)
    assert held.pad.left == (0.65, 0) and released.pad == NEUTRAL_PAD


def test_a_map_without_detail_gets_no_push():
    skill = SetWaypoint({"target": "away", "direction": "east"})
    skill.phase = "acquire"
    world = sim.MapWorld(markers=False)
    world.screen = "map"
    frame = world.frame()
    cursor = frame[300:420, 580:700].copy()
    frame[170:560, 240:980] = 90
    frame[300:420, 580:700] = cursor
    skill._picture = lambda image: read_map(image, sim.map_text("map"))
    result = skill.step(observation(0, "map", frame))
    assert result.pad == NEUTRAL_PAD and skill.failure.startswith("map-texture-unverified")
