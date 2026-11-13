"""A car that stands behind another is waiting, not stuck: the wait is bounded and needs the detector."""

from collections import Counter
from dataclasses import replace
from math import cos, sin

import pytest

from pilot.avoid import STALE, waits_behind
from pilot.contract import Command, Detection, Observation, Reading
from pilot.drive import Driver
from pilot.sim import SimConfig, Simulator
from pilot.skills import DriveRoute

CAMERA = 5.0  # metres the camera sits behind the car's middle
CAR_WIDTH = 1.8
OWN_SHARE = 0.24  # the own car's share of the picture's width, as in avoid.py


def box(sim, rear, x=0.0, kind="car"):
    """A vehicle whose rear is at (x, rear), as the detector would draw it from a camera behind the car."""
    dx, dy = x - sim.x, rear - sim.y
    ahead = dx * sin(sim.heading) + dy * cos(sim.heading)
    side = dx * cos(sim.heading) - dy * sin(sim.heading)
    if ahead < 0.5:
        return ()
    distance = ahead + CAMERA
    pixels = OWN_SHARE * 1280 * CAMERA / distance  # per car width, and per CAR_WIDTH metres across
    width = pixels
    centre = 640 + side / CAR_WIDTH * pixels
    return (Detection(kind, (centre - width / 2, 430 - width / 1.25, centre + width / 2, 430), 0.9),)


def world(*, start=0.0, wall=None, held=False, seconds=120):
    config = SimConfig(
        acceleration=0 if held else 4.5,
        noise_degrees=0,
        noise_tail_probability=0,
        outlier_probability=0,
        damage_probability=0,
        path_noise=0,
        path_missing=0,
        speed_noise=0,
        speed_missing=0,
        gps_wrong=0,
        gps_dropout=0,
        max_time=seconds,
    )
    walls = () if wall is None else (((-3, wall), (3, wall)),)
    return Simulator([(0, 0), (0, 500)], position=(0, start), config=config, walls=walls)


def drive(sim, seconds, *, boxes=None, until=None):
    """DriveRoute in the simulator; `boxes(sim)` is what the detector says, None for no detector.

    Returns the skill's last result, the time the car first stood at the wall and the driver's states."""
    skill = DriveRoute({"duration": 120, "style": "careful"})
    states = []
    step = skill.driver.step

    def spy(*args, **kwargs):
        command = step(*args, **kwargs)
        states.append((sim.time, command.state))
        return command

    skill.driver.step = spy
    result = stood = None
    while sim.time < seconds:
        if until is not None:
            until(sim)
        reading, moving = sim.observe()
        objects = () if boxes is None else boxes(sim)
        observation = Observation(
            reading, moving, sim.time, objects=objects, objects_time=None if boxes is None else sim.time
        )
        result = skill.step(observation)
        if stood is None and moving is False and sim.y > 7:
            stood = sim.time
        if result.status != "running":
            break
        sim.advance(Command(result.pad.left[0], result.pad.r2, result.pad.l2, skill.driver._last.state))
    return result, stood, states


def first(states, name):
    return next((t for t, state in states if state == name), None)


def test_a_queue_that_moves_on_after_twenty_seconds_is_waited_out_and_the_drive_goes_on():
    sim = world(wall=8)
    lead = [10.0]

    def moves_on(sim):
        if sim.time >= 20:
            sim.walls = ()
            lead[0] += 5 * sim.config.dt

    result, stood, states = drive(sim, 60, boxes=lambda sim: box(sim, lead[0]), until=moves_on)
    assert stood is not None and stood < 12
    assert result.status == "running"
    assert Counter(state for _, state in states).keys() == {"follow"}
    assert sim._recoveries == 0
    assert sim.y > 100  # it drove on behind the car that moved


def test_a_parked_car_that_never_moves_is_waited_behind_for_thirty_seconds_and_then_met_as_before():
    sim = world(wall=8)
    result, stood, states = drive(sim, 70, boxes=lambda sim: box(sim, 10.0))
    assert stood is not None
    assert first(states, "dead-or-held") is None
    # Nothing is tried while the wait lasts; the usual two seconds of standing and the recovery follow it.
    began = first(states, "recovery-reverse")
    assert began is not None and 30 <= began - stood <= 36
    assert result.status == "running"


def test_a_held_car_is_given_up_as_before_when_the_detector_sees_an_empty_road_or_another_lane():
    for boxes in (None, lambda sim: (), lambda sim: box(sim, 30.0, x=3.6)):
        sim = world(held=True)
        result, _, states = drive(sim, 30, boxes=boxes)
        assert (result.status, result.reason) == ("failed", "dead-or-held")
        assert 6 <= sim.time <= 9
        assert first(states, "recovery-reverse") is not None


def test_a_held_car_behind_another_is_given_up_when_the_wait_is_over_and_not_before():
    sim = world(held=True)
    result, _, states = drive(sim, 60, boxes=lambda sim: box(sim, 10.0))
    assert (result.status, result.reason) == ("failed", "dead-or-held")
    assert 36 <= sim.time <= 40
    assert first(states, "recovery-reverse") >= 30


def reading(**kwargs):
    return replace(Reading("tilted", "yellow", 0.0, 0.0, 0.0, False, 0.95), **kwargs)


def stand(driver, seconds, *, ahead, moving=False, start=0.0, step=1 / 30):
    states = []
    for i in range(int(seconds / step)):
        states.append(driver.step(reading(), start + i * step, moving, ahead=ahead).state)
    return states


def test_the_wait_counts_standing_still_for_at_most_the_configured_time():
    driver = Driver()
    waited = stand(driver, 31, ahead=True)
    assert set(waited) == {"follow"}
    # The wait is over: two seconds of standing later the usual recovery begins.
    after = stand(driver, 4, ahead=True, start=31)
    assert "recovery-reverse" in after


def test_a_road_that_cleared_or_a_car_that_rolled_on_gives_a_new_queue_its_whole_wait():
    driver = Driver()
    assert set(stand(driver, 25, ahead=True)) == {"follow"}
    assert set(stand(driver, 3, ahead=False, moving=True, start=25)) == {"follow"}
    assert set(stand(driver, 25, ahead=True, start=28)) == {"follow"}


def test_standing_with_nothing_ahead_is_stuck_as_before():
    assert "recovery-reverse" in stand(Driver(), 5, ahead=False)


def vehicle(**kwargs):
    return Detection(kwargs.pop("kind", "car"), kwargs.pop("box", (570, 330, 710, 430)), 0.9)


@pytest.mark.parametrize(
    "objects,expected",
    [
        ((vehicle(),), True),
        ((vehicle(kind="truck"),), True),
        ((vehicle(box=(600, 400, 680, 430)),), False),  # a long way ahead
        ((vehicle(box=(1000, 330, 1140, 430)),), False),  # the next lane
        ((vehicle(kind="person"),), False),
        ((vehicle(box=(20, 560, 120, 700)),), False),  # the minimap taken for a car
        ((), False),
    ],
)
def test_only_a_vehicle_close_ahead_in_the_own_track_is_waited_behind(objects, expected):
    assert waits_behind(objects, 1.0, 1.0) is expected


def test_old_or_missing_detections_say_nothing():
    assert waits_behind((vehicle(),), None, 1.0) is False
    assert waits_behind((vehicle(),), 1.0, 1.0 + STALE + 0.1) is False
    assert waits_behind((vehicle(),), 1.0, 0.5) is False
