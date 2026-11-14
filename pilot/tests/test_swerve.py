"""A way round keeps the road's heading and releases reverse on observed travel."""

import pytest
from test_round_what_stands import load, picture

from pilot.cli import drive_config
from pilot.drive import Driver
from pilot.sim import CAR_PROFILES

simulations = load("p110_sim")


@pytest.mark.parametrize("profile", CAR_PROFILES)
def test_parked_box_is_passed_without_turning_away_from_the_road(profile):
    row = simulations.parked(profile)
    assert row["after_contact"] is not None and row["after_contact"] < 20, row
    assert row["joined_at"] is not None, row
    assert row["max_heading"] <= 50, row
    assert row["end_heading"] < 20, row
    assert row["longest_retreat_m"] <= 4, row


def test_standing_at_a_clear_kerb_first_drives_on_without_reversing():
    driver = Driver(drive_config(["style=bold"]))
    pushed_at = None
    for tick in range(180):
        now = tick / 30
        # A kerb needs more pedal than normal unknown-speed following supplies.
        moving = pushed_at is not None and now - pushed_at > 0.3
        command = driver.step(picture(), now, moving)
        assert command.brake == 0
        if command.throttle >= 0.65 and pushed_at is None:
            pushed_at = now
    assert pushed_at is not None and pushed_at < 3
    assert command.state == "follow"


def test_downhill_backing_releases_l2_within_a_car_length():
    row = simulations.slope()
    assert row["metres"] <= 4, row
    assert row["reverse_command_seconds"] < 0.8, row
    assert row["last_brake"] == 0, row


def test_recorded_seconds_do_not_hold_full_lock_or_full_reverse():
    replay = load("p110_replay")
    commands = replay.replay()
    assert commands[0]["t"] < 38.1 and commands[-1]["t"] > 56.9
    assert replay.held(commands, "steer", 0.999) <= 1
    assert replay.held(commands, "l2", 0.999) <= 1
    assert any(c["state"] == "bypass-reverse" for c in commands)
    assert any(c["state"] == "bypass-forward" for c in commands)


def test_one_still_tick_and_unknown_motion_do_not_start_backing():
    driver = Driver(drive_config(["style=bold"]))
    for tick in range(180):
        command = driver.step(picture(), tick / 30, False if tick == 20 else None)
        assert command.brake == 0


def test_rear_stillness_interrupts_a_retreat_on_a_forward_clock():
    driver = Driver(drive_config(["style=bold"]))
    for tick in range(120):
        now = tick / 30
        command = driver.step(picture(), now, False, speed=0)
        if command.state == "bypass-reverse":
            break
    else:
        pytest.fail("The forward attempt did not lead to a bounded retreat")
    driver.step(picture(), now + 0.7, True, speed=2)
    command = driver.step(picture(), now + 0.8, False, speed=0)
    assert command.throttle == command.brake == 0
    command = driver.step(picture(), now + 0.95, False, speed=0)
    assert command.state == "bypass-forward" and command.brake == 0


def test_failed_tries_are_bounded_and_release_the_pad():
    driver = Driver(drive_config(["style=bold", "max_recoveries=3"]))
    sides = []
    previous = ""
    for tick in range(1200):
        command = driver.step(picture(), tick / 30, False, speed=0)
        if command.state == "bypass-forward" and previous != command.state:
            sides.append(driver._manoeuvre_side)
        previous = command.state
        if command.state == "failed-recovery":
            break
    assert command.state == "failed-recovery"
    assert len(sides) == 3 and sides[0] == -sides[1] == sides[2]
    assert command.steer == command.throttle == command.brake == 0
