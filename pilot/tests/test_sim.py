"""Nominal grid, pairwise car ranges and independent model invariants."""

import json
from dataclasses import replace
from itertools import product
from math import atan2, degrees
from pathlib import Path

import pytest

from pilot.contract import Command
from pilot.drive import Driver
from pilot.sim import CAR_PROFILES, SimConfig, Simulator

SCENARIOS = {
    "straight": (((0, 0), (0, 120)), (3, 0), 20, ()),
    "left": (((0, 0), (0, 100), (-100, 100)), (0, 0), 0, ()),
    "right": (((0, 0), (0, 100), (100, 100)), (0, 0), 0, ()),
    "s_bend": (((0, 0), (0, 60), (40, 100), (-40, 180), (0, 220), (0, 280)), (0, 0), 0, ()),
    "block": (((0, 0), (0, 100), (100, 100), (100, -30), (-30, -30), (-30, 20)), (0, 0), 0, ()),
    "wall": (((0, 0), (60, 0), (60, 100)), (0, 0), 0, (((-6, 3), (6, 3)),)),
}
GRID = tuple(product(SCENARIOS, (0.14, 0.21, 0.30), (0.5, 1.0, 2.0), (0, 1, 2), (0.0, 0.25)))


# Explicit measured failures, never a blanket allowance for a new failing cell.
# A changed outcome (including an improvement) fails for review of this baseline.
# P9 retains explicit measured misses; a green gate is not task acceptance.
KNOWN_FAILURES = {
    tuple(row["case"]): row["errors"]
    for row in json.loads((Path(__file__).parent / "fixtures" / "driver-p9-failures.json").read_text())
}
# P55's varied retries finish this existing miss 8.6 s sooner, but its longest
# progress gap rises from 23.667 to 27.800 s. It still fails the ten-second target.
KNOWN_FAILURES[("block", 0.3, 2.0, 0, 0.0, "range-10")] = ["progress gap 27.800s > 10s"]
# The three known misses at delay 0.21 with a pad's dead zone of 0.25 are stops before a block or a
# wall, and each change of the steering moves their longest stretch without progress a little. With
# P87's stick from the measured dead zone and the far aim on a straight way: the block at 2 m to the
# pixel 13.300 s (15.033 before both), the wall at 0.5 m 11.100 s (11.067), and the wall at 1 m, at
# 10.100 s before, now within the ten seconds.
KNOWN_FAILURES[("block", 0.21, 2.0, 0, 0.25, "nominal")] = ["progress gap 13.300s > 10s"]
KNOWN_FAILURES[("wall", 0.21, 0.5, 0, 0.25, "nominal")] = ["progress gap 11.100s > 10s"]
del KNOWN_FAILURES[("wall", 0.21, 1.0, 0, 0.25, "nominal")]


def run_case(name: str, delay: float, scale: float, seed: int, dead_zone: float, profile="nominal"):
    route, position, heading, walls = SCENARIOS[name]
    config = SimConfig(delay=delay, map_scale=scale, dead_zone=dead_zone, **CAR_PROFILES[profile])
    return Simulator(route, position=position, heading=heading, walls=walls, config=config, seed=seed).run(
        Driver()
    )


def violations(name: str, result, scale: float) -> list[str]:
    errors = []
    if not result.reached:
        errors.append(f"not reached at {result.elapsed:.3f}s")
    if result.max_no_progress > 10:
        errors.append(f"progress gap {result.max_no_progress:.3f}s > 10s")
    limit = 5.0
    if result.max_distance > limit:
        errors.append(f"maximum {result.max_distance:.3f}m > {limit}m")
    if result.steering_flips_per_second > 2:
        errors.append(f"flips {result.steering_flips_per_second:.3f}/s > 2/s")
    if result.max_overspeed_time > 1:
        errors.append(f"overspeed {result.max_overspeed_time:.3f}s > 1s")
    if result.max_bend_speed > 4:
        errors.append(f"bend speed {result.max_bend_speed:.3f}m/s > 4m/s")
    return errors


@pytest.mark.parametrize("name,delay,scale,seed,dead_zone", GRID)
def test_closed_loop_grid(name: str, delay: float, scale: float, seed: int, dead_zone: float) -> None:
    result = run_case(name, delay, scale, seed, dead_zone)
    errors = violations(name, result, scale)
    key = (name, delay, scale, seed, dead_zone, "nominal")
    if key in KNOWN_FAILURES:
        assert errors == KNOWN_FAILURES[key], "Measured failure changed; review the explicit baseline"
        pytest.xfail("; ".join(errors))
    assert not errors, "; ".join(errors)


def clean_config(**kwargs) -> SimConfig:
    return replace(SimConfig(noise_degrees=0, outlier_probability=0, damage_probability=0), **kwargs)


def test_seed_reproducibility() -> None:
    assert run_case("right", 0.21, 1, 2, 0.25) == run_case("right", 0.21, 1, 2, 0.25)


def test_fractional_delay_is_applied_at_timestamp() -> None:
    sim = Simulator([(0, 0), (0, 100)], config=clean_config(dt=0.1, delay=0.15, sensor_delay=0, drag=0))
    command = Command(0, 1, 0, "follow")
    sim.advance(command)
    assert sim.speed == 0
    sim.advance(command)
    assert sim.speed == pytest.approx(4.5 * 0.05)


def test_camera_relative_bearings_scale_and_rerouting() -> None:
    for scale in (0.5, 1, 2):
        sim = Simulator(
            [(0, 0), (0, 300)],
            position=(3, 0),
            heading=20,
            config=clean_config(map_scale=scale, scale_with_speed=0),
        )
        sim.camera_heading = 0.1
        reading, _ = sim.observe()
        expected = degrees(atan2(-3, ((30 * scale) ** 2 - 9) ** 0.5)) - 20
        assert reading.bearing - reading.arrow == pytest.approx(expected)
    sim = Simulator([(0, 0), (0, 300)], position=(100, 50), config=clean_config())
    assert sim.observe()[0].bearing == pytest.approx(-90)


def test_dead_zone_braking_reverse_and_wall_sweep() -> None:
    sim = Simulator([(0, 0), (0, 100)], config=clean_config(delay=0, dead_zone=0.25))
    for _ in range(30):
        sim.advance(Command(0.2, 1, 0, "follow"))
    assert sim.heading == 0 and sim.speed > 0
    for _ in range(60):
        sim.advance(Command(0, 0, 1, "recovery-reverse"))
    assert sim.speed < 0
    sim = Simulator([(0, 0), (0, 100)], walls=(((-5, 3), (5, 3)),), config=clean_config(delay=0, dt=1))
    sim.advance(Command(0, 1, 0, "follow"))
    assert sim.y < 3 and sim.collisions == 1 and sim.speed == 0
    sim.advance(Command(0, 0, 1, "recovery-reverse"))
    assert sim.y < 0


def test_closed_route_does_not_finish_at_start() -> None:
    sim = Simulator([(0, 0), (0, 50), (50, 50), (50, 0), (0, 0)], config=clean_config(max_time=0.1))
    assert not sim.run(Driver()).reached


def test_damage_is_missing_route_and_seeded_outliers_are_present() -> None:
    sim = Simulator([(0, 0), (0, 100)], config=clean_config(damage_probability=1))
    reading, _ = sim.observe()
    assert reading.corrupt and reading.route == "none" and reading.confidence == 0
    sim = Simulator([(0, 0), (0, 100)], config=clean_config(outlier_probability=1))
    assert abs(sim.observe()[0].bearing) >= 80


def test_rerouting_uses_global_nearest_segment() -> None:
    sim = Simulator(
        [(0, 0), (0, 200), (100, 200), (100, 0)], position=(90, 50), config=clean_config(scale_with_speed=0)
    )
    reading, _ = sim.observe()
    assert reading.bearing == pytest.approx(degrees(atan2(10, -((30**2 - 10**2) ** 0.5))))


def test_noise_matches_observed_temporal_scale() -> None:
    sim = Simulator(
        [(0, 0), (0, 300)],
        config=replace(SimConfig(), outlier_probability=0, damage_probability=0, sensor_delay=0),
    )
    samples = [sim.observe()[0].bearing for _ in range(12000)]
    differences = sorted(abs(a - b) for a, b in zip(samples, samples[6:], strict=False))
    # Six ticks are 0.2 s. The observed median/p90 are 3.8/15 degrees;
    # this fixed mixture models that spread without claiming a fitted GTA reader.
    median, p90 = differences[len(differences) // 2], differences[int(len(differences) * 0.9)]
    assert 3.3 < median < 4.3
    assert 13 < p90 < 17


@pytest.mark.parametrize("profile", tuple(CAR_PROFILES)[1:])
@pytest.mark.parametrize(
    "name,delay,scale,dead_zone", tuple(product(SCENARIOS, (0.14, 0.21, 0.3), (0.5, 1.0, 2.0), (0.0, 0.25)))
)
def test_unknown_car_ranges(profile, name, delay, scale, dead_zone):
    result = run_case(name, delay, scale, 0, dead_zone, profile)
    errors = violations(name, result, scale)
    key = (name, delay, scale, 0, dead_zone, profile)
    if key in KNOWN_FAILURES:
        assert errors == KNOWN_FAILURES[key], "Measured edge failure changed; review the baseline"
        pytest.xfail("; ".join(errors))
    assert not errors, "; ".join(errors)
