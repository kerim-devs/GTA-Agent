"""P104: legible town distances, bounded startup and road-aware abstention."""

from dataclasses import replace
from pathlib import Path

import cv2
import pytest

from pilot.cli import drive_config
from pilot.contract import Reading
from pilot.drive import Driver
from pilot.gps import Fix, Speedometer
from pilot.gps import recognize as native_recognize
from pilot.sim import SimConfig, Simulator

LAB = Path(__file__).resolve().parents[2] / "lab/gps"


@pytest.mark.parametrize(
    "name,distance",
    [
        ("024431-02546", 1460),
        ("024431-02629", 1450),
        ("015901-03025", 2080),
        ("024431-07071", 847),
    ],
)
def test_native_print_over_light_roads_and_beside_blips(name, distance):
    pytest.importorskip("Vision")
    crop = cv2.cvtColor(cv2.imread(str(LAB / f"p104-{name}.png")), cv2.COLOR_BGR2RGB)
    try:
        fix = native_recognize(crop)
    except RuntimeError as exc:
        if "failed: None" in str(exc):
            pytest.skip(f"Vision runtime unavailable: {exc}")
        raise
    assert fix is not None and fix.distance == distance


def test_four_coherent_metre_captures_measure_before_one_second():
    meter = Speedometer()
    for index in range(3):
        assert meter.update(index / 4, Fix(500 - 2 * index)) is None
    assert meter.update(0.75, Fix(494)) == pytest.approx(8)


def test_startup_outlier_and_coarse_quantisation_still_wait_for_consensus():
    for fixes in ((500, 498, 700, 494), (500, 498, 496, 100)):
        meter = Speedometer()
        for index, value in enumerate(fixes):
            assert meter.update(index / 4, Fix(value)) is None
    coarse = Speedometer()
    for index in range(4):
        assert coarse.update(index / 4, Fix(2000 - 10 * index, quantum=10)) is None
    assert coarse.update(1, Fix(1960, quantum=10)) == pytest.approx(40)


def test_isolated_wrong_print_neither_moves_speed_nor_renews_it():
    meter = Speedometer()
    for index in range(12):
        meter.update(index / 4, Fix(600 - 2 * index))
    previous_time = meter.time
    assert meter.update(3, Fix(88)) == pytest.approx(8)
    assert meter.time == previous_time
    assert meter.update(3.25, Fix(574)) == pytest.approx(8)
    for t in (3.5, 3.75, 4, 4.25, 4.5, 4.75, 5):
        speed = meter.update(t)
    assert speed is None


def picture(path, **kwargs):
    return replace(Reading("tilted", "purple", 0, 0, 0, False, 0.95, path=tuple(path)), **kwargs)


def test_unknown_speed_pedal_follows_visible_road_and_never_brakes():
    config = drive_config(["style=bold"])
    straight = picture([(0, y) for y in range(12, 100, 6)])
    corner = picture([(0, y) for y in range(12, 25, 6)] + [(-x, 24) for x in range(6, 85, 6)])
    startup = Driver(config).step(straight, 0, True, speed=None)
    assert startup.throttle <= config.unknown_throttle

    def after_loss(reading):
        driver = Driver(config)
        driver.step(reading, 0, True, speed=5)
        return driver.step(reading, 2, True, speed=None)

    open_command = after_loss(straight)
    bend_command = after_loss(corner)
    arrival = after_loss(replace(straight, gps_distance=4))
    assert config.unknown_throttle < open_command.throttle <= 0.24
    assert bend_command.throttle <= config.unknown_throttle + 1e-12
    assert arrival.throttle < bend_command.throttle
    assert open_command.brake == bend_command.brake == arrival.brake == 0
    unresolved = Driver(config).step(picture([(0, 12), (0, 18)]), 0, True, speed=None)
    assert unresolved.throttle <= config.unknown_throttle and unresolved.brake == 0


@pytest.mark.parametrize("dropout", [6, 12])
def test_simulator_abstains_across_a_town_bend_without_leaving_the_road(dropout):
    config = SimConfig(
        gps_dropout=dropout,
        gps_wrong=0,
        dead_zone=0.25,
        delay=0.14,
        path_spacing=6,
        path_noise=0.15,
        noise_degrees=0.5,
        path_missing=0,
        damage_probability=0,
        outlier_probability=0,
        max_time=150,
    )
    result = Simulator([(0, 0), (0, 50), (50, 50), (50, 100)], config=config).run(
        Driver(drive_config(["style=bold"]))
    )
    assert result.reached and result.max_distance <= 5 and result.collisions == 0


def test_a_print_that_lost_its_leading_digit_is_not_the_distance():
    # 20261114-035459 at 277 s: the car stood against parked cars 756 m from the shop, the "7" lay
    # over a sunlit pavement, and "56" was read for four seconds.
    meter = Speedometer()
    at = 0.0
    for distance in (764, 762, 760, 758, 757, 756, 756, 756):
        meter.update(at, Fix(distance, None, 1.0), sampled_at=at)
        at += 0.25
    assert meter.fix.distance >= 756
    for _ in range(16):
        meter.update(at, Fix(56, None, 1.0), sampled_at=at)
        at += 0.25
    assert meter.fix.distance >= 756


def test_a_route_made_shorter_is_believed_when_the_time_allows_the_fall():
    meter = Speedometer()
    at = 0.0
    for distance in (1764, 1762, 1760, 1758, 1757, 1756):
        meter.update(at, Fix(distance, None, 1.0), sampled_at=at)
        at += 0.25
    for step in range(60):
        meter.update(at, Fix(1300 - 3 * step, None, 1.0), sampled_at=at)
        at += 0.25
    assert meter.fix.distance < 1300
