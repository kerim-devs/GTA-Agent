"""P98: carry speed on a clear road, slow for its shape and finish the exit."""

from dataclasses import replace
from math import cos, radians, sin

import pytest

from pilot.cli import drive_config
from pilot.contract import Reading
from pilot.drive import Driver
from pilot.sim import CAR_PROFILES, SimConfig, Simulator, drive_through_roads


def road(path, **changes):
    return replace(
        Reading(
            minimap="tilted",
            route="purple",
            bearing=0,
            far_bearing=0,
            arrow=0,
            corrupt=False,
            confidence=0.95,
            path=tuple(path),
        ),
        **changes,
    )


def test_heading_correction_does_not_brake_a_straight_road():
    path = [(sin(radians(15)) * y, cos(radians(15)) * y) for y in range(12, 100, 6)]
    driver = Driver(drive_config(["style=bold"]))
    commands = [driver.step(road(path), i / 30, True, speed=20) for i in range(60)]
    assert all(c.throttle >= 0.95 and c.brake == 0 for c in commands)
    assert any(c.steer > 0.3 for c in commands)


def test_curve_ahead_lifts_before_braking_is_needed():
    path = [(0, y) for y in range(12, 43, 6)] + [(-x, 42) for x in range(6, 85, 6)]
    driver = Driver(drive_config(["style=bold"]))
    commands = [driver.step(road(path), i / 30, True, speed=22) for i in range(30)]
    assert all(c.throttle == 0 and c.brake == 0 for c in commands)
    assert all(c.throttle == 0 for c in commands if c.brake)
    assert max(abs(c.steer) for c in commands) < 0.1


def test_curve_brake_never_uses_stale_speed_to_reverse_a_stopped_car():
    path = [(0, y) for y in range(12, 43, 6)] + [(-x, 42) for x in range(6, 85, 6)]
    driver = Driver(drive_config(["style=bold"]))
    driver.step(road(path), 0, True, speed=22)
    for i in range(1, 46):
        command = driver.step(road(path), i / 30, False, speed=22)
        assert command.brake == 0
    for i in range(46, 76):
        assert driver.step(road(path), i / 30, None, speed=None).brake == 0


def test_slow_car_gets_the_lock_for_a_visible_exit():
    path = [(-y * 0.6, y) for y in range(12, 100, 6)]
    driver = Driver(drive_config(["style=bold"]))
    commands = [driver.step(road(path), i / 30, True, speed=2) for i in range(30)]
    assert sum(abs(c.steer) for c in commands[-15:]) / 15 > 0.6


@pytest.mark.parametrize("name", tuple(drive_through_roads()))
@pytest.mark.parametrize("profile", tuple(CAR_PROFILES))
def test_drive_through_roads_with_the_existing_car_profiles(name, profile):
    cfg = SimConfig(
        **CAR_PROFILES[profile],
        dead_zone=0.25,
        delay=0.14,
        max_time=300,
        gps_wrong=0,
        gps_dropout=0,
        path_missing=0,
        damage_probability=0,
        outlier_probability=0,
        noise_degrees=0.5,
        path_noise=0.15,
    )
    sim = Simulator(drive_through_roads()[name], config=cfg)
    driver = Driver(drive_config(["style=bold"]))
    cruise = []
    maximum_error = 0
    while sim.time < cfg.max_time:
        reading, moving = sim.observe()
        command = driver.step(reading, sim.time, moving, speed=sim.observed_speed)
        error, progress = sim._route_position()
        maximum_error = max(maximum_error, error)
        # Every road starts with the same clear approach, before the bend is in view.
        if 80 < progress < 100:
            cruise.append(sim.speed)
            assert command.brake == 0
        if name == "kilometre" and 50 < progress < 975:
            assert command.brake == 0
        sim.advance(command)
        if progress >= sim.length - 3:
            break
    assert progress >= sim.length - 3
    assert maximum_error <= 5.0
    assert min(cruise) >= 0.95 * min(cfg.top_speed, cfg.acceleration / cfg.drag)


def test_a_short_unresolved_path_does_not_authorize_high_speed_or_braking():
    driver = Driver(drive_config(["style=bold"]))
    command = driver.step(road([(0, 12), (0, 18)]), 0, True, speed=25)
    assert command.throttle <= 0.3 and command.brake == 0


def test_a_past_corner_cannot_keep_limiting_a_later_straight():
    corner = [(0, y) for y in range(12, 43, 6)] + [(-x, 42) for x in range(6, 85, 6)]
    straight = [(sin(radians(15)) * y, cos(radians(15)) * y) for y in range(12, 100, 6)]
    driver = Driver(drive_config(["style=bold"]))
    driver.step(road(corner), 0, True, speed=20)
    for i in range(1, 151):
        command = driver.step(road(straight), i / 30, True, speed=20)
    assert command.throttle >= 0.95 and command.brake == 0


def test_brief_damage_flag_on_the_same_straight_does_not_lift_the_pedal():
    picture = road([(0, y) for y in range(12, 100, 6)])
    driver = Driver(drive_config(["style=bold"]))
    driver.step(picture, 0, True, speed=20)
    for i in range(1, 25):
        command = driver.step(replace(picture, corrupt=True, confidence=0.35), i / 30, True, speed=20)
        assert command.throttle >= 0.95 and command.brake == 0
    # Changed geometry cannot renew the last clean straight.
    changed = replace(picture, path=((60, 13), (70, 19)), bearing=80, corrupt=True, confidence=0.35)
    command = driver.step(changed, 1.1, True, speed=20)
    assert command.throttle == command.brake == 0
