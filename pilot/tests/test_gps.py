"""GPS behavior without recordings or hardware; native OCR only where it is installed."""

import resource
from dataclasses import replace
from pathlib import Path
from threading import Event
from time import perf_counter

import cv2
import numpy as np
import pytest

from pilot.contract import Reading
from pilot.drive import Driver
from pilot.gps import Fix, Reader, Speedometer, parse, turn_arrow
from pilot.gps import recognize as native_recognize  # conftest replaces the module attribute
from pilot.loop import Pipeline, log_row
from pilot.motion import motion_state

GOOD = Reading("tilted", "yellow", 0, 0, 0, False, 0.95)


@pytest.mark.parametrize(
    "text,value",
    [
        ("t292m", 292),
        ("• 1.08km", 1080),
        ("914m-", 914),
        ("130m", 130),
        ("t 1.69km", 1690),
        ("→ 16m", 16),
        ("1 1,40km", 1400),
    ],
)
def test_distance_units_and_prefixes(text, value):
    assert parse([text]).distance == value


@pytest.mark.parametrize("text", ["3884m", "1284m", "1 /6 m", "3IUm", "e5km", "4km", "1284", "42 mph"])
def test_ambiguous_digits_and_units_are_not_repaired(text):
    assert parse([text]) is None


def test_arrow_is_separate_from_distance_and_can_abstain():
    assert parse(["→ 16m"]).arrow == "right"
    assert parse(["t 16m"]).arrow is None
    crop = np.zeros((170, 260, 3), np.uint8)
    assert turn_arrow(crop) is None
    cv2.arrowedLine(crop, (38, 130), (51, 130), (255, 255, 255), 2, tipLength=0.4)
    assert turn_arrow(crop) == "right"


def test_quantisation_outliers_and_two_second_loss():
    meter = Speedometer()
    speeds = []
    for i in range(120):
        t = i / 4
        distance = round((2000 - 20 * t) / 10) * 10
        fix = None if 10 <= t < 12 else Fix(distance + (1000 if i % 10 < 3 else 0), quantum=10)
        speed = meter.update(t, fix)
        if t >= 4 and speed is not None:
            speeds.append(speed)
        if t == 11.75:
            assert speed is None
    assert len(speeds) > 70
    assert max(abs(s - 20) for s in speeds) <= 3


@pytest.mark.parametrize("jump", [30, 140, 400])
def test_reroute_does_not_become_speed_and_reverse_is_rolling(jump):
    meter = Speedometer()
    for i in range(24):
        speed = meter.update(i / 4, Fix(500 - i * 2.5))
    assert speed == pytest.approx(10)
    for i in range(24, 40):
        speed = meter.update(i / 4, Fix(440 - jump - (i - 24) * 2.5))
        assert speed is None or speed <= 12
    reverse = Speedometer()
    for i in range(20):
        speed = reverse.update(i / 4, Fix(100 + i * 2))
    assert speed == pytest.approx(8)
    assert reverse.update(9) is None
    assert reverse.update(1, Fix(50)) is None


def test_late_duplicates_and_outliers_cannot_renew_freshness():
    meter = Speedometer()
    for i in range(16):
        meter.update(i / 4, Fix(300 - i * 2))
    for i in range(16, 24):
        meter.update(i / 4, Fix(1), sampled_at=0)
    assert meter.update(6) is None
    assert meter.time == 3.75


def test_ocr_never_blocks_or_builds_a_queue_and_failure_is_optional():
    entered, release = Event(), Event()
    calls = []

    def slow(crop):
        calls.append(1)
        entered.set()
        release.wait(2)
        raise RuntimeError("optional OCR unavailable")

    reader = Reader(recognizer=slow)
    crop = np.zeros((170, 260, 3), np.uint8)
    reader.poll(crop, 1)
    assert entered.wait(1)
    try:
        started = perf_counter()
        for i in range(30):
            assert reader.poll(crop, 1 + i / 30) is None
        assert perf_counter() - started < 0.1
        assert len(calls) == 1
    finally:
        release.set()
        reader._thread.join(1)
    assert reader.error == "optional OCR unavailable"
    assert reader.poll(crop, 1.1) == (1, None)


def test_pipeline_passes_metres_and_logs_gps_on_every_tick():
    class Sensor:
        def poll(self, crop, t):
            return t, Fix(500 - 8 * t, "left")

    pipeline = Pipeline(reader=lambda crop: GOOD, motion=lambda a, b: 3, gps_reader=Sensor())
    for i in range(20):
        reading, moving, command = pipeline.step(np.zeros((170, 260, 3), np.uint8), i / 4)
    assert reading.gps_speed == pytest.approx(8)
    assert reading.gps_distance == 462
    assert moving is True
    row = log_row(0, 1, 0, 4.75, reading, moving, command)
    assert row["gps_speed"] == pytest.approx(8)
    assert row["gps_arrow"] == "left"
    missing = log_row(0, None, None, None, None, None, None)
    assert all(missing[k] is None for k in ("gps_distance", "gps_speed", "gps_arrow", "gps_time"))


def test_arrival_and_ambiguous_slow_motion():
    straight = Driver().step(GOOD, 0, speed=3)
    arrival = Driver().step(replace(GOOD, gps_distance=5), 0, speed=3)
    assert arrival.throttle < straight.throttle
    assert motion_state(0.7) is None
    assert motion_state(0.1) is False
    assert motion_state(1.1) is True


@pytest.mark.parametrize("band", [0.5, 1.0, 2.0])
def test_map_zoom_covers_the_whole_measured_table(band):
    from pilot.sim import SimConfig, Simulator

    sim = Simulator([(0, 0), (0, 100)], config=SimConfig(map_scale=band))
    for speed, scale in ((0, 0.7), (6, 1), (12, 2.1), (18, 3.6), (24, 3.7), (45, 3.7)):
        sim.speed = speed
        assert sim.map_scale == pytest.approx(band * scale)


def test_simulation_metrics_expose_speed_and_bend_violations():
    from pilot.contract import Command
    from pilot.drive import DriveConfig
    from pilot.sim import SimConfig, Simulator

    class Uncontrolled(Driver):
        def step(self, *args, **kwargs):
            return Command(0, 1, 0, "follow")

    result = Simulator([(0, 0), (0, 30), (30, 30)], config=SimConfig(max_time=12)).run(
        Uncontrolled(DriveConfig(speed_limit=1))
    )
    assert result.max_overspeed_time > 1
    assert result.max_bend_speed > 4
    assert result.max_distance > 5


def test_stationary_map_overrules_a_lagging_gps_speed_for_braking():
    command = Driver().step(GOOD, 0, moving=False, speed=20)
    assert command.brake == 0


def test_hidden_bend_does_not_cut_the_route_on_a_zoomed_map():
    from pilot.sim import SimConfig, Simulator

    route = [(0, 0), (0, 60), (40, 100), (-40, 180), (0, 220), (0, 280)]
    result = Simulator(route, config=SimConfig(delay=0.3, map_scale=2), seed=2).run(Driver())
    assert result.reached
    assert result.max_distance <= 5
    assert result.max_bend_speed <= 4


def test_native_recognition_reads_a_real_crop_without_keeping_its_images():
    pytest.importorskip("Vision")
    path = Path(__file__).parent / "fixtures" / "crop_1020.png"  # the map prints 326m at 282.6 s
    crop = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
    try:
        fix = native_recognize(crop)
    except RuntimeError as exc:
        if "failed: None" in str(exc):  # the framework imports in a sandbox and then cannot run
            pytest.skip(f"Vision runtime unavailable: {exc}")
        raise
    assert fix is not None and fix.distance == 326
    for _ in range(50):
        native_recognize(crop)
    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    for _ in range(300):
        native_recognize(crop)
    # one enlarged patch is 150 KB; a reader that keeps them grows by 45 MB here
    assert resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - before < 15e6
