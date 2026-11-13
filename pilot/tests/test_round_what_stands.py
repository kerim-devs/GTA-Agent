"""P101: recorded stillness, missing boxes, and a failed side that must change."""

import importlib.util
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from pilot.avoid import Avoider, passing_side, waits_behind
from pilot.cli import drive_config
from pilot.contract import Detection, Reading
from pilot.drive import Driver
from pilot.sim import CAR_PROFILES

LAB = Path(__file__).resolve().parents[2] / "lab" / "drive"


def load(name):
    spec = importlib.util.spec_from_file_location(name, LAB / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


simulations = load("p101_sim")
replay = load("p101_replay")


def picture(**changes):
    return replace(Reading("tilted", "purple", 0, 0, 0, False, 1), **changes)


def test_recorded_van_starts_reverse_and_keeps_forward_lock_without_map_motion():
    driver = Driver(drive_config(["style=bold"]))
    commands = []
    for row, reading, objects, at in replay.inputs("000623"):
        if not 705 <= row["t"] <= 733:
            continue
        command = driver.step(
            reading,
            row["t"],
            row["moving"],
            speed=reading.gps_speed,
            ahead=waits_behind(objects, at, row["t"]),
            bypass_side=passing_side(objects, at, row["t"]),
        )
        commands.append((row["t"], command))
    reverse = next((t for t, c in commands if c.state == "bypass-reverse"), None)
    assert reverse is not None and reverse < 721  # van reached at approximately 711 s
    forward = [(t, c.steer) for t, c in commands if c.state == "bypass-forward" and c.throttle > 0]
    assert forward and forward[0][0] - reverse < 2.1
    # Ignore the short R2 gear change while reverse momentum still turns the
    # wheels the other way. Each subsequent main lock must last, then alternate.
    groups = []
    for t, command in commands:
        if command.state == "bypass-reverse" and (not groups or groups[-1]["forward"]):
            groups.append({"reverse": t, "forward": []})
        if groups and command.state == "bypass-forward" and command.throttle:
            groups[-1]["forward"].append((t, command.steer))
    locks = []
    for group in groups[:-1]:  # the recording window can cut off its final attempt
        rows = group["forward"]
        if rows:
            held = [(t, s) for t, s in rows if t >= rows[0][0] + 0.6]
            if held:
                assert held[-1][0] - held[0][0] >= 1.5
                assert len({s for _, s in held}) == 1
                locks.append(held[0][1])
    assert len(locks) >= 2 and locks[1] == -locks[0]


@pytest.mark.parametrize("profile", CAR_PROFILES)
@pytest.mark.parametrize("blocked", [0, -1, 1])
def test_unreported_parked_vehicle_is_passed_and_route_rejoined(profile, blocked):
    row = simulations.trial(profile, blocked)
    assert row["first_contact"] is not None
    assert row["after_contact"] is not None and row["after_contact"] <= 20, row
    assert row["joined_at"] is not None, row
    assert row["longest_reverse"] <= 1.84
    if blocked:
        passed = next(r for r in row["trace"] if r[2] > 6)
        assert passed[1] * blocked < 0  # actually passed on the open side


def test_one_bad_motion_tick_and_stale_or_missing_gps_do_not_prove_standing():
    for gps in (None, -10):
        driver = Driver(drive_config(["style=bold"]))
        for tick in range(150):
            now = tick / 30
            command = driver.step(
                picture(gps_speed=0, gps_time=gps), now, False if tick == 50 else None, speed=0
            )
            assert not command.state.startswith("bypass")


def test_fresh_gps_zero_only_authorizes_standing_on_an_ahead_route():
    driver = Driver(drive_config(["style=bold"]))
    for tick in range(180):
        now = tick / 30
        command = driver.step(
            picture(bearing=60, far_bearing=60, gps_speed=0, gps_time=now), now, None, speed=0
        )
        assert not command.state.startswith("bypass")


def test_side_lorry_does_not_authorize_a_bypass():
    lorry = Detection("truck", (0, 180, 540, 540), 0.9)
    assert passing_side((lorry,), 0, 0) is None
    assert Avoider().step((lorry,), 0, 0, bypass=True).steer == 0
    driver = Driver(drive_config(["style=bold"]))
    for tick in range(180):
        now = tick / 30
        command = driver.step(
            picture(),
            now,
            True,
            speed=5,
            ahead=waits_behind((lorry,), now, now),
            bypass_side=passing_side((lorry,), now, now),
        )
        assert command.state == "follow"


def test_careful_does_not_use_the_new_gps_standing_fallback():
    driver = Driver(drive_config(["style=careful"]))
    for tick in range(180):
        now = tick / 30
        command = driver.step(picture(gps_speed=0, gps_time=now), now, None, speed=0)
        assert command.state == "follow"


def test_unseen_reverse_stops_early_when_the_rear_is_blocked():
    driver = Driver(drive_config(["style=bold"]))
    for tick in range(65):
        command = driver.step(picture(), tick / 30, False, speed=0)
    assert command.state == "bypass-reverse"
    start = driver._phase_since
    driver.step(picture(), start + 0.7, True, speed=2)
    command = driver.step(picture(), start + 0.8, False, speed=0)
    assert command.throttle == command.brake == 0
    command = driver.step(picture(), start + 0.95, False, speed=0)
    assert command.state == "bypass-forward" and command.brake == 0


def test_bypass_remembers_the_failed_side_until_real_forward_progress():
    driver = Driver(drive_config(["style=bold"]))
    now = 0.0

    def step(moving, speed):
        nonlocal now
        now += 0.1
        return driver.step(picture(), now, moving, speed=speed)

    def main_lock():
        forward_at = None
        for _ in range(150):
            command = step(False, 0)
            if command.state == "bypass-forward":
                if forward_at is None:
                    forward_at = now
                if now - forward_at > 0.6:
                    return command.steer
        pytest.fail("No forward escape lock within fifteen seconds")

    first = main_lock()
    for _ in range(140):
        step(True, 1)
    assert main_lock() == -first
    for _ in range(100):
        step(True, 10)
    assert main_lock() == first
