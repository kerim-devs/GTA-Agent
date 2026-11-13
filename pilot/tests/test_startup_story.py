"""Offline regressions for the mission lost to an unreadable pause map."""

import importlib.util
import json
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
import pytest

from pilot.camera import StartupCamera
from pilot.contract import Hud, Observation, Pad, Reading
from pilot.head import HeadRequest
from pilot.mission import MissionHead
from pilot.scene import SceneText, TextLine
from pilot.waypoint import SetWaypoint, read_map

FIXTURES = Path(__file__).parent / "fixtures/startup-story"
SPEC = importlib.util.spec_from_file_location(
    "startup_replay", Path(__file__).resolve().parents[2] / "lab/camera/startup_replay.py"
)
REPLAY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPLAY)


def request(t=0, *, last=None, blips=(), vehicle=False):
    return HeadRequest(
        events=[],
        help="",
        objective="",
        subtitle="",
        banner="",
        notebook="",
        jpeg_path="",
        minimap={"minimap": "tilted" if vehicle else "flat", "route": "none", "blips": list(blips)},
        hud={"screen": "game", "wanted": 0, "mode": "vehicle" if vehicle else "on_foot"},
        objects=[],
        last_skill=last,
        time=t,
        judgment={"mode": "vehicle" if vehicle else "foot"},
    )


def result(name, status="done", reason="time-limit"):
    return {"name": name, "status": status, "reason": reason}


def test_story_relocates_before_one_retry_and_keeps_the_goal_after_another_failure():
    head = MissionHead(goal_seed=3)
    first = head.decide(request())
    assert first.goal["name"] == "story"
    failure = result("set_waypoint", "failed", "player-marker-unreadable; gameplay observed")
    moved = head.decide(request(5, last=failure))
    assert moved.goal["name"] == "story"
    assert [c.name for c in moved.plan] == ["walk_road"]
    retry = head.decide(request(11, last=result("walk_road")))
    assert [c.name for c in retry.plan] == ["set_waypoint"]
    assert retry.plan[0].args["target"] == "mission"
    second = head.decide(request(18, last=failure))
    assert second.goal["name"] == "story"
    assert all(c.name != "set_waypoint" for c in second.plan)
    # The map is left alone for a while of walking and then tried again from another spot.
    walking = head.decide(request(30, last=result("walk_road")))
    assert walking.goal["name"] == "story"
    assert all(c.name != "set_waypoint" for c in walking.plan)
    again = head.decide(request(64, last=result("walk_road", reason="time-limit; second leg")))
    assert again.goal["name"] == "story"
    assert [c.name for c in again.plan] == ["set_waypoint"]
    assert not any(h["outcome"] == "gave_up" for h in head.goals.history)
    # The goal ends at its limit like any other: no figure waits for a map for good.
    head.decide(request(500, last=failure))
    assert any(h["name"] == "story" and h["reason"] == "limit" for h in head.goals.history)


def test_story_uses_a_stable_mission_blip_after_two_map_failures():
    for vehicle, expected in ((False, "walk_to"), (True, "drive_to_blip")):
        head = MissionHead(goal_seed=3)
        head.decide(request(vehicle=vehicle))
        failure = result("set_waypoint", "failed", "player-marker-unreadable")
        head.decide(request(5, last=failure, vehicle=vehicle))
        head.decide(request(11, last=result("walk_road"), vehicle=vehicle))
        blips = [{"color": "yellow", "x": 10, "y": 10}]
        head.decide(request(18, last=failure, blips=blips, vehicle=vehicle))
        answer = head.decide(request(25, last=result("walk_road"), blips=blips, vehicle=vehicle))
        assert answer.goal["name"] == "story"
        assert [c.name for c in answer.plan] == [expected]
        assert answer.plan[0].args["color"] == "yellow"


def test_a_failed_relocation_does_not_reopen_the_map():
    head = MissionHead(goal_seed=3)
    head.decide(request())
    head.decide(request(5, last=result("set_waypoint", "failed", "player-marker-unreadable")))
    answer = head.decide(request(12, last=result("walk_road", "failed", "blocked")))
    assert answer.goal["name"] == "story"
    assert all(c.name != "set_waypoint" for c in answer.plan)


def test_a_verified_absent_mission_can_release_the_goal_after_relocation():
    head = MissionHead(goal_seed=3)
    head.decide(request())
    failure = result("set_waypoint", "failed", "place-not-in-legend")
    head.decide(request(5, last=failure))
    head.decide(request(11, last=result("walk_road")))
    head.decide(request(18, last=failure))
    assert any(h["reason"] == "no mission in the readable map or radar" for h in head.goals.history)


def test_recorded_first_45_seconds_keep_the_same_story_after_both_map_failures():
    rows = REPLAY.head_replay()
    story = rows[1]["goal"]
    for row in rows[2:]:
        assert row["goal"]["name"] == "story"
        assert row["goal"]["started"] == story["started"]
        assert row["goal"]["place"] is None
        assert all(call["args"].get("place") != "Discount Store" for call in row["plan"])
    assert rows[2]["step"] == "story_relocate"
    assert rows[5]["step"] == "story_radar"


def test_recorded_camera_frames_do_not_level_an_already_level_view():
    measured = REPLAY.camera_measurement()
    assert measured["total"] == 29
    assert measured["correct"] >= 18
    for row in measured["frames"]:
        if row["label"] == "level":
            assert "level_camera" not in row["plan"]
    sky = [r for r in measured["frames"] if r["session"] == "20261113-163218" and r["label"] == "sky"]
    assert len(sky) == 5
    assert all(r["plan"] == ["level_camera"] for r in sky)


def test_recorded_level_far_session_plans_no_camera_skill():
    rows = json.loads((FIXTURES / "camera.json").read_text())
    skill = StartupCamera({})
    selected = [r for r in rows if r["session"] == "20261113-163218" and r["asked_t"] in {2, 3, 3.4}]
    for i, row in enumerate(selected):
        # Replay the three captured views at the detector's normal sampling cadence.
        result = skill.step(replace(REPLAY.camera_observation(row), time=i * 0.3, objects_time=i * 0.3))
        assert result.pad == Pad()
    assert result.status == "done"
    assert skill.planned == []


@pytest.mark.parametrize("row", json.loads((FIXTURES / "maps.json").read_text()), ids=lambda r: r["case"])
def test_failed_map_frames_use_the_open_legend_or_fail_once_without_reopening(row):
    frame = cv2.cvtColor(cv2.imread(str(FIXTURES / row["file"])), cv2.COLOR_BGR2RGB)
    text = SceneText(tuple(TextLine(**line) for line in row["ocr"]))
    picture = read_map(frame, text)
    assert picture.screen == "map" and picture.cursor == (640, 360)
    assert picture.player is None  # the recorded rotated/occluded player icon

    class FrozenReader:
        def read(self, frame):
            return text

    skill = SetWaypoint({})
    skill.reader = FrozenReader()
    game = np.full((720, 1280, 3), 20, np.uint8)
    pads = []
    back = False
    for tick in range(451):
        now = tick / 10
        gameplay = tick == 0 or back
        observation = Observation(
            Reading("flat" if gameplay else "none", "none", None, None, None, False, 1),
            False,
            now,
            game if gameplay else frame,
            hud=Hud(screen="game" if gameplay else "map"),
        )
        result = skill.step(observation)
        pads.append(result.pad)
        back |= "circle" in result.pad.buttons
        if result.status != "running":
            break
    assert skill.legend is not None and skill.legend.kind == "mission"
    assert skill.legend.destination != "Discount Store"
    assert skill.legend.observed_places.get("Fremde und Freaks") == "mission"
    assert result.status == "failed" and result.pad == Pad()
    assert "player-marker-unreadable" in result.reason
    presses = sum(
        "options" in pad.buttons and (i == 0 or "options" not in pads[i - 1].buttons)
        for i, pad in enumerate(pads)
    )
    assert presses == 1
    # A frozen capture cannot prove that a menu command took effect. It must
    # terminate neutrally, rather than blindly confirming a place or reopening.
    assert all("cross" not in pad.buttons for pad in pads)
    assert skill.step(observation).status == "failed"


def test_a_walk_that_ended_stuck_is_not_planned_again_from_the_same_spot():
    """13 November, 17:49: a garden wall between the figure and the road, and the same walk planned
    eight times in a row, each ending stuck after eleven seconds."""
    head = MissionHead(goal_seed=3)
    assert head.decide(request()).goal["name"] == "story"
    placed = result("set_waypoint", "done", "waypoint set: Fremde und Freaks (2911m); gameplay observed")
    walk = head.decide(request(29, last=placed))
    assert [c.name for c in walk.plan] == ["walk_road"]
    turns = []
    for i in range(4):
        stuck = result("walk_road", "failed", "stuck")
        again = head.decide(request(40 + 11 * i, last={**stuck, "at": i}))
        assert again.goal["name"] == "story"
        assert [c.name for c in again.plan] == ["look", "walk", "walk_road"]
        turns.append(again.plan[0].args["angle"])
    assert turns == [120, -120, 180, 120]
