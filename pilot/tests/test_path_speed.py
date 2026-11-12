"""Behavioral acceptance of local route geometry and noisy speed feedback."""

from dataclasses import replace
from itertools import pairwise
from math import hypot

import numpy as np
import pytest

from pilot.contract import Reading
from pilot.drive import DriveConfig, Driver
from pilot.loop import Pipeline
from pilot.minimap import _XF, _YF, RH, RW, _trace
from pilot.motion import map_speed
from pilot.sim import SimConfig, Simulator

GOOD = Reading("tilted", "yellow", 0, 0, 0, False, 0.95)
STRAIGHT = tuple((0.0, float(y)) for y in range(12, 70, 3))
CORNER = ((0.0, 12.0), (0.0, 15.0), (0.0, 18.0), (3.0, 18.0), (6.0, 18.0), (9.0, 18.0))


def test_short_path_drives_direction_and_bearing_fallback_survives():
    path = tuple((-float(x), 6.0) for x in range(12, 33, 3))
    assert Driver().step(replace(GOOD, bearing=50, path=path), 0).steer < 0
    assert Driver().step(replace(GOOD, bearing=50), 0).steer > 0
    assert Driver().step(replace(GOOD, bearing=50, path=((float("nan"), 12),)), 0).steer > 0
    assert Driver().step(replace(GOOD, minimap="flat", path=path), 0).throttle == 0


def test_speed_planning_lifts_before_steering_and_brakes_only_when_rolling():
    straight = Driver().step(replace(GOOD, path=STRAIGHT), 0, speed=6)
    bend = Driver().step(replace(GOOD, path=CORNER), 0, speed=6)
    assert bend.throttle < straight.throttle
    assert bend.brake > 0 and abs(bend.steer) < 0.01
    assert Driver().step(replace(GOOD, path=CORNER), 0, speed=0).brake == 0
    unknown = Driver().step(replace(GOOD, path=CORNER), 0)
    assert unknown.brake == 0 and 0 < unknown.throttle <= DriveConfig().unknown_throttle
    driver = Driver()
    driver.step(replace(GOOD, path=CORNER), 0, speed=20)
    stopped = driver.step(replace(GOOD, path=CORNER), 0.033, speed=0)
    assert stopped.brake == 0


@pytest.mark.parametrize("value", [None, -1, True, float("nan"), float("inf"), "2"])
def test_invalid_speed_is_unknown(value):
    command = Driver().step(GOOD, 0, speed=value)
    assert command.brake == 0 and command.throttle <= DriveConfig().unknown_throttle


def test_speed_uses_actual_elapsed_time_and_abstains():
    assert map_speed(3, 0.15) == pytest.approx(20)
    for displacement, elapsed in ((None, 0.2), (2, 0), (2, -0.1), (float("nan"), 0.2)):
        assert map_speed(displacement, elapsed) is None
    observed = []

    class Capture:
        def step(self, reading, t, moving, speed=None):
            observed.append((moving, speed))

    pipeline = Pipeline(reader=lambda _: GOOD, motion=lambda a, b: 3, driver=Capture())
    crop = np.zeros((170, 260, 3), np.uint8)
    pipeline.step(crop, 1)
    pipeline.step(crop, 1.16, feedback=False)
    assert observed[-1][0] is None
    assert observed[-1][1] is None  # Map pixels must never be fed as metres per second.
    pipeline.step(crop, 0.5)
    assert observed[-1] == (None, None)


def test_route_samples_follow_visible_l_shape_and_do_not_fill_arrow_gap():
    x, y = _XF.reshape(RH, RW), -_YF.reshape(RH, RW)
    route = (((abs(x) <= 1) & (y >= 11) & (y <= 45)) | ((x >= 0) & (x <= 50) & (abs(y - 45) <= 1))).astype(
        np.uint8
    ) * 255
    traced = _trace(route, route, np.full((RH, RW), 100, np.uint8))
    assert traced is not None
    path = traced["path"]
    assert 11 <= hypot(*path[0]) <= 15
    assert path[-1][0] >= 45
    assert all(abs(px) <= 1 or abs(py - 45) <= 1 for px, py in path)
    assert all(b[0] + b[1] >= a[0] + a[1] - 1 for a, b in pairwise(path))


def test_intermittent_unknown_motion_pauses_stuck_evidence():
    driver = Driver()
    for i in range(120):
        command = driver.step(GOOD, i / 30, None if i % 5 == 0 else False)
        if command.state == "recovery-reverse":
            break
    assert command.state == "recovery-reverse"
    driver = Driver()
    assert all(driver.step(GOOD, i / 30).state == "follow" for i in range(120))


def test_sensor_occlusion_missing_values_delay_and_grip():
    config = SimConfig(path_noise=0, path_missing=0, damage_probability=0, speed_missing=1)
    sim = Simulator([(0, 0), (0, 100)], config=config)
    reading, moving = sim.observe()
    assert all(hypot(*p) >= config.path_hidden for p in reading.path)
    assert moving is None and sim.observed_speed is None
    assert Simulator([(0, 0), (0, 100)], config=replace(config, path_missing=1)).observe()[0].path == ()
    from pilot.contract import Command

    low = Simulator([(0, 0), (0, 100)], config=replace(config, grip=1, delay=0))
    high = Simulator([(0, 0), (0, 100)], config=replace(config, grip=20, delay=0))
    for car in (low, high):
        car.speed = 10
        car.advance(Command(1, 0, 0, "follow"))
    assert abs(high.heading) > abs(low.heading) * 3


def test_route_gone_does_not_reverse_a_measured_stopped_car():
    driver = Driver()
    driver.step(GOOD, 0, moving=True, speed=0)
    for i in range(1, 91):
        command = driver.step(replace(GOOD, route="none"), i / 30, moving=True, speed=0)
    assert command.state == "route-gone" and command.brake == command.throttle == 0


def test_slow_measured_motion_clears_recovery_across_sensor_gaps():
    cfg = DriveConfig(
        stuck_time=0.1, reverse_time=0.1, forward_time=1.0, recovery_clear_time=0.3, max_recoveries=1
    )
    driver = Driver(cfg)
    driver.step(GOOD, 0, moving=False, speed=0)
    driver.step(GOOD, 0.1, moving=False, speed=0)
    assert driver.step(GOOD, 0.21, moving=False, speed=0).state == "recovery-reverse"
    for i in range(10, 60):
        missing = i % 7 == 0
        command = driver.step(GOOD, i / 30, moving=None if missing else False, speed=None if missing else 0.9)
    assert command.state == "follow"
    # One more genuine standstill must still permit an escape after the successful one.
    states = [driver.step(GOOD, 2 + i / 30, moving=False, speed=0).state for i in range(25)]
    assert "recovery-reverse" in states
    assert "failed-recovery" not in states[:5]


def test_speed_filter_does_not_brake_from_a_stale_high_sample():
    driver = Driver()
    reading = replace(GOOD, path=STRAIGHT)
    driver.step(reading, 0, speed=20)
    for i in range(1, 61):
        driver.step(reading, i / 30, speed=None)
    command = driver.step(reading, 61 / 30, speed=2)
    assert command.brake == 0 and command.throttle > 0
