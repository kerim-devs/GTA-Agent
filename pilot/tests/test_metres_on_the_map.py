"""P105 recorded junctions, measured independently from road-texture motion and GPS."""

from math import hypot

import pytest

from pilot.cli import drive_config
from pilot.drive import Driver
from pilot.sim import SimConfig, Simulator

# Texture correspondences calibrate the distance; route pixels are separate observations.
# The optical/GPS reference has 15% plus 3 m uncertainty, not exact console ground truth.
CASES = (
    {
        "run": "20261114-014037:261.096",
        "speed": 25.981,
        "corner": (-23.719, 54.241),
        "metres": 212.808,
        "path": (
            (-4, 13),
            (-6, 18),
            (-8, 25),
            (-12, 31),
            (-15, 37),
            (-19, 43),
            (-21, 49),
            (-27, 54),
            (-35, 55),
            (-41, 55),
            (-47, 55),
            (-53, 55),
            (-59, 54),
            (-65, 53),
            (-71, 53),
            (-77, 53),
            (-83, 53),
            (-87, 53),
            (-92, 54),
        ),
    },
    {
        "run": "20261114-021738:600.855",
        "speed": 19.622,
        "corner": (6.429, 40.898),
        "metres": 112.945,
        "path": (
            (0, 13),
            (2, 19),
            (3, 24),
            (3, 31),
            (6, 36),
            (12, 41),
            (19, 42),
            (25, 43),
            (31, 43),
            (37, 43),
            (44, 42),
            (49, 42),
            (55, 43),
            (61, 43),
            (68, 43),
            (73, 44),
            (79, 44),
            (85, 45),
            (89, 46),
        ),
    },
)


@pytest.mark.parametrize("case", CASES, ids=[c["run"] for c in CASES])
def test_recorded_junction_lifts_by_the_measured_braking_distance(case):
    driver = Driver(drive_config(["style=bold"]))
    cfg, speed = driver.config, case["speed"]
    required = (speed**2 - cfg.junction_speed**2) / (2 * cfg.planned_deceleration)
    required += speed * (cfg.command_delay + cfg.gps_window / 2)
    assert case["metres"] - (case["metres"] * 0.15 + 3) <= required
    assert driver._speed_limit(case["path"], 0, speed) < speed


@pytest.mark.parametrize("case", CASES, ids=[c["run"] for c in CASES])
def test_recorded_junction_distance_stays_on_the_short_side(case):
    driver = Driver(drive_config(["style=bold"]))
    planned = hypot(*driver._map_point(case["corner"], case["speed"]))
    # p10 minus the measurement allowance is deliberately below the median reference.
    assert 0.55 * case["metres"] <= planned <= case["metres"] * 1.15 + 3


def test_speed_band_boundaries_cannot_push_a_visible_junction_away():
    driver = Driver(drive_config(["style=bold"]))
    for speed in (6, 8, 12, 16, 18, 24):
        before = hypot(*driver._map_point((0, 50), speed - 0.01))
        after = hypot(*driver._map_point((0, 50), speed + 0.01))
        assert abs(after - before) < 0.2
    assert hypot(*driver._map_point((0, 50), 4)) < hypot(*driver._map_point((0, 50), 22))


def test_simulator_draws_foreshortening_and_transverse_compression_independently():
    sim = Simulator(((0, 0), (0, 1000)), config=SimConfig(map_tilt=0.0065))
    near = sim._map_project(0, 50)[1]
    middle = sim._map_project(0, 100)[1]
    far = sim._map_project(0, 150)[1]
    assert far - middle < middle - near
    assert sim._map_project(50, 0)[0] > near


def test_zoom_cannot_instantly_follow_a_braking_car():
    sim = Simulator(((0, 0), (0, 1000)), config=SimConfig(map_tilt=0.0065))
    sim.speed = 24
    assert sim.map_scale < 2
    sim._map_speed = 24
    sim.speed = 0
    assert sim.map_scale > 2
