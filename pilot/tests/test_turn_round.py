"""A detached route ahead is joined; a route behind gets an actual moving turn."""

import importlib.util
import json
from dataclasses import replace
from pathlib import Path

import pytest

from pilot.cli import drive_config
from pilot.contract import NEUTRAL_PAD, Observation, Reading
from pilot.drive import Driver
from pilot.sim import CAR_PROFILES, Simulator
from pilot.skills import DriveRoute

LAB = Path(__file__).resolve().parents[2] / "lab" / "drive"
SPEC = importlib.util.spec_from_file_location("p99_evaluate", LAB / "p99_evaluate.py")
BENCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BENCH)


def picture(near=170, far=None, **changes):
    return replace(Reading("tilted", "purple", near, near if far is None else far, 0, False, 1), **changes)


def driver():
    return Driver(drive_config(["style=bold"]))


def test_recorded_trip_moves_on_instead_of_counting_motionless_turns_as_success():
    car = driver()
    rows = json.loads((LAB / "p99-readings.json").read_text())
    commands = []
    for row in rows:
        reading = Reading(**{**row["reading"], "blips": ()})
        command = car.step(reading, row["t"], row["moving"], speed=reading.gps_speed)
        commands.append(command)
        assert command.state not in {"failed-recovery", "dead-or-held", "turn-reverse", "turn-forward"}
    assert rows[0]["t"] < 9.75 and rows[-1]["t"] > 31.6
    assert commands[0].state == "turn-join" and commands[0].throttle >= 0.4 and commands[0].brake == 0
    assert any(c.state == "turn-along" and c.throttle >= 0.4 for c in commands)


@pytest.mark.parametrize("profile", CAR_PROFILES)
def test_every_car_faces_a_wholly_behind_route_within_the_p80_bound(profile):
    row = BENCH.trial(Driver, profile, "behind")
    assert row["aligned_at"] is not None and row["aligned_at"] <= 7.4 + 1 / 30
    assert row["travel"] > 5 and row["reverse_seconds"] > 0


@pytest.mark.parametrize("profile", CAR_PROFILES)
def test_every_car_joins_the_parallel_road_over_free_ground_without_reversing(profile):
    row = BENCH.trial(Driver, profile, "join")
    assert row["joined_at"] is not None and row["joined_at"] < 20
    assert row["reverse_seconds"] == row["collisions"] == 0


@pytest.mark.parametrize("profile", CAR_PROFILES)
def test_every_car_continues_on_its_own_side_of_the_rail(profile):
    row = BENCH.trial(Driver, profile, "rail")
    assert row["joined_at"] is None and row["x"] > -12
    assert row["speed"] > 1 and row["y"] > 40
    assert row["state"] == "turn-along"


def test_a_changed_far_bearing_cannot_finish_a_turn_without_movement():
    car = driver()
    car.step(picture(), 0, False, speed=0)
    states = []
    for tick in range(1, 500):
        command = car.step(picture(170, 20), tick / 10, False, speed=0)
        states.append(command.state)
    assert "follow" not in states
    assert states[-1] == "dead-or-held"
    assert command.steer == command.throttle == command.brake == 0


def test_no_path_and_disagreeing_bearings_do_not_start_a_turn():
    assert driver().step(picture(170, 20), 0, False, speed=0).state == "follow"
    assert driver().step(picture(20, 170), 0, False, speed=0).state == "follow"


def test_one_spurious_motion_tick_cannot_finish_the_turn():
    car = driver()
    car.step(picture(), 0, False, speed=0)
    for tick in range(1, 31):
        command = car.step(picture(170, 20), tick / 10, tick == 28, speed=0)
        assert command.state != "follow"


@pytest.mark.parametrize("phase", ["turn-join", "turn-clear", "turn-along"])
def test_missing_or_damaged_evidence_and_external_stop_release_each_join_phase(phase):
    skill = DriveRoute({"style": "bold"})
    reading, _ = BENCH.world("nominal", "join").observe()
    skill.step(Observation(reading, False, 0))
    skill.driver._phase = phase
    for kwargs in ({"boxes_fresh": False}, {}):
        bad = reading if kwargs else replace(reading, corrupt=True)
        command = skill.driver.step(bad, 0.1, False, **kwargs)
        assert command.steer == command.throttle == command.brake == 0
    result = skill.stop("operator-stop")
    assert result.pad == NEUTRAL_PAD and result.status == "failed"
    assert skill.step(Observation(reading, False, 1)) == result


def test_a_held_car_cannot_cycle_the_join_clearance_forever():
    car = driver()
    reading, _ = BENCH.world("nominal", "join").observe()
    for tick in range(700):
        command = car.step(reading, tick / 10, False, speed=0)
    assert command.state == "dead-or-held"
    assert command.steer == command.throttle == command.brake == 0


def test_a_car_held_again_backs_off_for_longer_each_time():
    # 20261114-061504: a metre back and into the same wall again, for a minute.
    car = driver()
    reading, _ = BENCH.world("nominal", "join").observe()
    legs, last = [], None
    for tick in range(700):
        state = car.step(reading, tick / 10, False, speed=0).state
        if state == "turn-clear" and last != "turn-clear":
            legs.append(0)
        if state == "turn-clear":
            legs[-1] += 1
        last = state
    assert len(legs) >= 3 and legs[0] < legs[1] < legs[2]


def test_a_car_that_moved_but_could_not_join_reports_failed_recovery_instead_of_dead():
    car = driver()
    skill = DriveRoute({"style": "bold", "duration": 120}, driver=car)
    reading, _ = BENCH.world("nominal", "join").observe()
    for tick in range(700):
        result = skill.step(Observation(reading, tick < 15, tick / 10))
        if result.status != "running":
            break
    assert result.reason == "failed-recovery" and result.status == "failed"
    assert result.pad == NEUTRAL_PAD


@pytest.mark.parametrize("rail", [False, True])
def test_join_and_clearance_also_work_with_the_road_to_the_right(rail):
    left = BENCH.world("nominal", "rail" if rail else "join")
    sim = Simulator(
        [(-x, y) for x, y in left.route],
        position=(0, 0),
        config=left.config,
        walls=tuple(tuple((-x, y) for x, y in wall) for wall in left.walls),
    )
    car = driver()
    reverse = 0
    while sim.time < 30:
        reading, moving = sim.observe()
        command = car.step(reading, sim.time, moving, speed=sim.observed_speed)
        reverse += command.brake > 0
        sim.advance(command)
    assert sim.speed > 1 and sim.y > 40
    if rail:
        assert sim.x < 12 and command.state == "turn-along"
    else:
        assert reverse == 0 and abs(sim.x - 24) < 2
