"""Visible junctions constrain speed before steering, without braking for mere coasting."""

import pytest

from pilot.cli import drive_config
from pilot.contract import Reading
from pilot.drive import Driver
from pilot.sim import CAR_PROFILES, SimConfig, Simulator


def road(path):
    return Reading(
        minimap="tilted",
        route="purple",
        bearing=0,
        far_bearing=0,
        arrow=0,
        corrupt=False,
        confidence=1,
        path=tuple(path),
    )


def test_the_last_visible_outgoing_chord_already_limits_the_approach():
    picture = road([(0, y) for y in range(12, 43, 6)] + [(6, 42), (12, 42)])
    driver = Driver(drive_config(["style=bold"]))
    command = driver.step(picture, 0, True, speed=22)
    assert driver.speed_reason == "curve"
    assert command.throttle == 0
    assert command.brake == 0  # There is still enough distance to lift first.
    assert abs(command.steer) < 0.1


def test_a_short_visible_straight_cannot_authorize_unbounded_acceleration():
    driver = Driver(drive_config(["style=bold"]))
    command = driver.step(road([(0, y) for y in range(12, 49, 6)]), 0, True, speed=22)
    assert driver.speed_reason == "visibility"
    assert command.throttle == 0 and command.brake == 0


def test_a_near_junction_brakes_before_the_arrow_turns():
    driver = Driver(drive_config(["style=bold"]))
    picture = road([(0, 12), (0, 18), (0, 24)] + [(x, 24) for x in range(6, 85, 6)])
    command = driver.step(picture, 0, True, speed=22)
    assert command.throttle == 0 and command.brake > 0
    assert abs(command.steer) < 0.1


def test_a_floor_crossing_cannot_reopen_the_same_brake_pulse():
    driver = Driver(drive_config(["style=bold"]))
    brakes = [driver._pulsed(0.5, speed, i / 30) for i, speed in enumerate([9, 6.9, 7.2, 6.9, 7.2, 6.9, 7.2])]
    assert brakes[0] > 0
    assert all(brake == 0 for brake in brakes[1:])


def test_sensor_sized_excess_lifts_without_starting_a_trigger_shaped_brake():
    driver = Driver(drive_config(["style=bold"]))
    driver.speed_reason = "curve"
    driver._brake_limit = 6
    assert driver._pedal(6, 7.5, 0, False, None) == (0, 0)
    throttle, brake = driver._pedal(6, 12, 0.1, False, None)
    assert throttle == 0 and brake > 0


@pytest.mark.parametrize("blocks", (1, 2))
@pytest.mark.parametrize("profile", tuple(CAR_PROFILES))
def test_town_blocks_keep_the_existing_five_metre_road_bound(profile, blocks):
    route = ((0.0, 0.0), (0.0, 150.0), (150.0, 150.0))
    if blocks == 2:
        route += ((150.0, 300.0),)
    config = SimConfig(
        **CAR_PROFILES[profile],
        dead_zone=0.25,
        delay=0.14,
        max_time=160,
        gps_wrong=0,
        gps_dropout=0,
        path_missing=0,
        damage_probability=0,
        outlier_probability=0,
        noise_degrees=0.5,
        path_noise=0.15,
        path_spacing=6,
        path_horizon=90,
    )
    sim = Simulator(route, config=config)
    driver = Driver(drive_config(["style=bold"]))
    entries = []
    maximum = 0
    while sim.time < config.max_time:
        reading, moving = sim.observe()
        command = driver.step(reading, sim.time, moving, speed=sim.observed_speed)
        error, progress = sim._route_position()
        maximum = max(maximum, error)
        if len(entries) < blocks and progress >= 150 * (len(entries) + 1) - 5:
            entries.append(sim.speed)
        sim.advance(command)
        if progress >= sim.length - 3:
            break
    assert progress >= sim.length - 3
    assert maximum <= 5
    assert len(entries) == blocks and max(entries) <= 7
