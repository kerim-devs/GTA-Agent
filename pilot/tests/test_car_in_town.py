"""P103 street acquisition: bounded decisions, not counterfactual GTA travel."""

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import cv2
import pytest
from test_foot import road_frame
from test_vehicle_entry import FAR, NEAR, obs, px

from pilot.contract import NEUTRAL_PAD, Detection, Reading
from pilot.errands import Trip
from pilot.vehicle_entry import EnterVehicle, Vehicle, choose_vehicle


@pytest.mark.parametrize("objects", [(), (FAR,)])
def test_no_reachable_car_returns_search_within_eight_seconds(objects):
    skill = EnterVehicle({"duration": 25})
    for tick in range(81):
        result = skill.step(replace(obs(tick / 10, objects), moving=True))
        if result.status != "running":
            break
    assert result.status == "failed" and tick / 10 <= 8
    assert "no car in reach" in result.reason
    assert result.pad == NEUTRAL_PAD


def test_unresponsive_door_is_left_within_four_seconds_and_not_pressed_twice():
    skill = EnterVehicle({"duration": 25})
    presses = []
    previous = False
    for tick in range(60):
        result = skill.step(obs(tick / 10, (NEAR,)))
        pressed = "triangle" in result.pad.buttons
        if pressed and not previous:
            presses.append(tick / 10)
        previous = pressed
        if result.status != "running":
            break
    assert len(presses) == 1
    assert result.status == "failed" and tick / 10 - presses[0] <= 4
    assert "door locked or blocked" in result.reason and "presses=1" in result.reason
    assert result.pad == NEUTRAL_PAD


def test_rejected_door_is_not_the_next_trips_target():
    trip = Trip("Ammu-Nation")
    trip.start(100)
    trip.step, trip.game_since = "car", 100
    first = trip.decide(SimpleNamespace(time=101, last_skill=None)).plan[0]
    skill = EnterVehicle(first.args)
    for tick in range(50):
        result = skill.step(obs(101 + tick / 10, (NEAR,)))
        if result.status != "running":
            break
    assert result.status == "failed"
    ended = 101 + tick / 10
    trip.accept(
        {
            "name": "enter_vehicle",
            "args": first.args,
            "status": result.status,
            "reason": result.reason,
            "attempt_id": 1,
        },
        ended,
    )
    second = trip.decide(SimpleNamespace(time=ended + 0.05, last_skill=None)).plan[0]
    assert second.name == "enter_vehicle"
    next_skill = EnterVehicle(second.args)
    alternate = Detection("car", px(0.73, 0.42, 0.91, 0.64), 0.95)
    for tick in range(7):
        result = next_skill.step(obs(ended + 0.05 + tick / 10, (NEAR, alternate)))
    assert next_skill.target is not None
    assert next_skill.target.obj.box[0] > 0.7
    assert not next_skill.target.rejected
    assert ended - 101.1 < 4


def test_failed_try_with_cars_stays_at_the_street():
    trip = Trip("Ammu-Nation")
    trip.start(0)
    trip.step, trip.game_since = "car", 0
    trip.car_seen = (FAR, 10)
    trip.retry = "road"
    result = trip.decide(SimpleNamespace(time=10, last_skill=None))
    assert result.plan[0].name == "wait"
    assert result.plan[0].args["duration"] <= 2


def test_map_line_without_traffic_never_starts_a_walk():
    skill = EnterVehicle({"duration": 25})
    for tick in range(50):
        result = skill.step(replace(obs(tick / 10, ()), frame=road_frame(25)))
        assert result.pad.left == (0, 0)
        if result.status != "running":
            break
    assert result.status == "failed"


def test_distant_passing_car_is_observed_without_chasing_then_stopped_car_is_taken():
    skill = EnterVehicle({"duration": 25, "occupied": "allow"})
    for tick in range(7):
        t = tick / 10
        passing = Detection("car", px(0.3 + t * 0.2, 0.4, 0.4 + t * 0.2, 0.52), 0.95)
        result = skill.step(obs(t, (passing,)))
        assert result.pad.left == (0, 0)
        assert "triangle" not in result.pad.buttons
    for tick in range(7, 14):
        result = skill.step(obs(tick / 10, (NEAR,)))
        if "triangle" in result.pad.buttons:
            break
    assert "triangle" in result.pad.buttons


def test_traffic_that_has_stopped_beside_the_figure_beats_a_distant_parked_car():
    near = replace(NEAR, box=(0.30, 0.45, 0.70, 0.90))
    far = replace(FAR, box=(0.43, 0.42, 0.57, 0.52))
    stopped = Vehicle(near, 0, near, 0, motion="standing", occupancy="occupied", moved=True)
    parked = Vehicle(far, 0, far, 0, motion="standing", occupancy="parked-candidate")
    assert choose_vehicle([parked, stopped], "allow") is stopped


def test_door_animation_motion_preserves_the_seven_second_grace():
    skill = EnterVehicle({"duration": 2})
    for tick in range(70):
        t = tick / 10
        observation = obs(t, (NEAR,))
        if 0.4 < t < 5.5:
            observation = replace(observation, figure=Detection("person", px(0.5, 0.5, 0.58, 0.9), 0.9))
        if t >= 5.5:
            observation = obs(t, (), minimap="tilted")
        result = skill.step(observation)
        if result.status != "running":
            break
    assert result.status == "done" and result.pad == NEUTRAL_PAD


def test_one_bad_pose_does_not_buy_an_unresponsive_door_seven_seconds():
    skill = EnterVehicle({"duration": 25})
    for tick in range(45):
        observation = obs(tick / 10, (NEAR,))
        if tick == 10:
            observation = replace(observation, figure=Detection("person", px(0.7, 0.5, 0.9, 0.9), 0.9))
        result = skill.step(observation)
        if result.status != "running":
            break
    assert result.status == "failed" and tick / 10 <= 4.1
    assert result.pad == NEUTRAL_PAD


def recorded(sample):
    return replace(
        obs(sample["t"], tuple(Detection(**d) for d in sample["objects"])),
        reading=Reading(**sample["reading"]),
        figure=Detection(**sample["figure"]) if sample["figure"] else None,
    )


@pytest.mark.parametrize("start", [278, 290, 316])
def test_recorded_cutting_map_does_not_send_the_figure_further_along_the_tracks(start):
    folder = Path(__file__).resolve().parents[2] / "lab/enter"
    samples = json.loads((folder / "p103-cutting.json").read_text())
    skill = EnterVehicle({"duration": 25, "kind": "car", "occupied": "allow"})
    for sample in samples:
        if not start <= sample["t"] <= start + 3.1:
            continue
        frame = cv2.cvtColor(cv2.imread(str(folder / sample["image"])), cv2.COLOR_BGR2RGB)
        result = skill.step(replace(recorded(sample), frame=frame))
        assert result.pad.left == (0, 0)
        assert "triangle" not in result.pad.buttons


def test_recorded_wreck_is_left_after_one_ineffective_press():
    folder = Path(__file__).resolve().parents[2] / "lab/enter"
    samples = json.loads((folder / "p103-detections.json").read_text())
    skill = EnterVehicle({"duration": 25, "kind": "car", "occupied": "allow"})
    pressed = None
    for sample in samples:
        if sample["session"] != "20261114-004115":
            continue
        result = skill.step(recorded(sample))
        if "triangle" in result.pad.buttons:
            assert pressed is None
            pressed = sample["t"]
        if result.status != "running":
            break
    assert pressed is not None and result.status == "failed"
    assert sample["t"] - pressed <= 4
    assert "presses=1" in result.reason and result.pad == NEUTRAL_PAD
