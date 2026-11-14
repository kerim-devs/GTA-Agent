"""P100 recorded decisions and bounded obstacle recovery, without a console."""

import importlib.util
import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_vehicle_entry import FAR, NEAR, EntryGame, obs, px

from pilot.contract import NEUTRAL_PAD, Detection
from pilot.vehicle_entry import EnterVehicle

LAB = Path(__file__).resolve().parents[2] / "lab/enter"
SPEC = importlib.util.spec_from_file_location("p100_replay", LAB / "p100_replay.py")
REPLAY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPLAY)
RUNS = json.loads((LAB / "p100-recorded.json").read_text())["runs"]


def hospital(attempt):
    return next(r for r in RUNS if r["session"] == "20261113-230030" and r["attempt"] == attempt)


@pytest.mark.parametrize("attempt", [3, 9])
def test_recorded_hospital_approaches_run_instead_of_walking_the_whole_budget(attempt):
    run = hospital(attempt)
    assert not run["sprint_ticks"]
    skill = EnterVehicle({"duration": 25, "kind": "car", "occupied": "allow"})
    results = [skill.step(REPLAY.observation(s)) for s in run["samples"]]
    assert any("cross" in r.pad.buttons and r.pad.left[1] < -0.5 for r in results)
    assert all(not ({"cross", "triangle"} <= set(r.pad.buttons)) for r in results)


@pytest.mark.parametrize("attempt", [7, 9])
def test_recorded_long_hospital_search_returns_before_the_old_late_press(attempt):
    run = hospital(attempt)
    skill = EnterVehicle({"duration": 25, "kind": "car", "occupied": "allow"})
    results = [(s["play"]["t"], skill.step(REPLAY.observation(s))) for s in run["samples"]]
    presses = [t for t, r in results if "triangle" in r.pad.buttons]
    assert not presses
    ended = next((t, r) for t, r in results if r.status == "failed")
    assert ended[0] - results[0][0] <= 8.6
    assert "no car in reach" in ended[1].reason
    assert ended[1].pad == NEUTRAL_PAD


def test_small_nearness_changes_do_not_change_the_car_being_approached():
    left = Detection("car", px(0.30, 0.4, 0.42, 0.54), 0.9)
    right = Detection("car", px(0.58, 0.4, 0.70, 0.535), 0.9)
    skill = EnterVehicle({})
    skill.step(obs(0, (left, right)))
    chosen = skill.target
    for tick in range(1, 20):
        other = replace(right, box=px(0.58, 0.4, 0.70, 0.56))
        skill.step(obs(tick * 0.05, (other, left)))
        assert skill.target is chosen


def test_an_unreachable_target_is_replaced_by_the_next_visible_car():
    alternate = Detection("car", px(0.70, 0.42, 0.80, 0.50), 0.9)
    skill = EnterVehicle({})
    skill.step(obs(0, (FAR, alternate)))
    first = skill.target
    escaped = False
    for tick in range(1, 81):
        result = skill.step(replace(obs(tick / 10, (FAR, alternate)), moving=False))
        escaped |= abs(result.pad.left[0]) > 0.7
        if skill.target is not None and skill.target is not first:
            break
    assert escaped, "try a way around the obstacle before abandoning the car"
    assert first.rejected and skill.target is not None and skill.target is not first
    assert tick / 10 <= 7
    assert skill.last_problem is None or "approach blocked" in skill.last_problem
    terminal = skill.step(obs(45.1, (FAR, alternate)))
    assert terminal.status == "failed" and terminal.pad == NEUTRAL_PAD
    assert "tried=" in terminal.reason and "switches=" in terminal.reason


def test_one_still_tick_does_not_detour_and_detector_gap_releases_the_run():
    skill = EnterVehicle({})
    for tick in range(10):
        result = skill.step(replace(obs(tick / 10), moving=tick != 5))
        assert abs(result.pad.left[0]) < 0.1
    assert skill.step(obs(1.5, delivered=False)).pad == NEUTRAL_PAD
    assert skill.stop().pad == NEUTRAL_PAD


def test_a_way_around_a_pole_reaches_the_door_without_cancelling_entry():
    game = EntryGame(distance=6, blocked=True)
    skill = EnterVehicle({})
    around = False
    for tick in range(300):
        t = tick / 10
        reading = replace(game.observation(t), moving=not game.blocked)
        result = skill.step(reading)
        if abs(result.pad.left[0]) > 0.7:
            game.blocked = False
            around = True
        game.apply(t, result.pad)
        if result.status != "running":
            break
    assert around and game.seated and result.status == "done"
    assert game.cancelled == 0 and result.pad == NEUTRAL_PAD


def test_a_failed_late_press_cannot_open_another_animation_budget():
    skill = EnterVehicle({"duration": 1})
    skill.step(obs(0, ()))
    skill.step(obs(0.9, (NEAR,)))
    assert skill.step(obs(0.95, (NEAR,))).pad.buttons == ("triangle",)
    for tick in range(11, 100):
        result = skill.step(obs(tick / 10, (NEAR,)))
        if result.status != "running":
            break
    assert result.status == "failed" and skill.attempts == 1
    assert result.pad == NEUTRAL_PAD and tick / 10 <= 9


def test_a_late_press_never_extends_the_absolute_skill_cap():
    skill = EnterVehicle({"duration": 45})
    skill.step(obs(0, (NEAR,)))
    assert skill.step(obs(0.05, (NEAR,))).pad.buttons == ("triangle",)
    assert skill.step(obs(44.5, (), minimap="tilted")).status == "running"
    result = skill.step(obs(45.01, (NEAR,)))
    assert result.status == "failed" and result.pad == NEUTRAL_PAD


def test_a_missed_box_does_not_transfer_the_last_walk_to_a_new_target():
    skill = EnterVehicle({})
    skill.step(obs(0))
    assert skill.step(obs(0.3, ())).pad == NEUTRAL_PAD
    assert skill.target is not None
    skill.step(obs(1.4, ()))
    assert skill.target is None
    skill.step(obs(1.5, (NEAR,)))
    assert skill.step(obs(1.55, (NEAR,))).pad.buttons == ("triangle",)
