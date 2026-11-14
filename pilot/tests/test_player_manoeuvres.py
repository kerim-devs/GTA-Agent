from dataclasses import replace

import pytest

from pilot.avoid import STALE, passing_side
from pilot.cli import drive_config
from pilot.contract import Observation, Reading
from pilot.drive import Driver
from pilot.objects import Detection
from pilot.skills import DriveRoute


def picture(angle=0, **changes):
    return replace(
        Reading(
            minimap="tilted",
            route="yellow",
            bearing=angle,
            far_bearing=angle,
            arrow=0,
            corrupt=False,
            confidence=0.95,
        ),
        **changes,
    )


def car(x=640):
    return Detection("car", (x - 100, 270, x + 100, 430), 0.9)


def bold(**changes):
    return Driver(replace(drive_config(["style=bold"]), **changes))


def wait_for_bypass(driver, side=-1):
    for tick in range(22):
        command = driver.step(picture(), tick / 10, False, speed=0, ahead=True, bypass_side=side)
    assert command.state == "bypass-reverse"
    return command


@pytest.mark.parametrize(
    ("objects", "side"),
    [
        ((car(),), -1),
        ((car(), car(340)), 1),
        ((car(), car(940)), -1),
        ((car(), car(340), car(940)), 0),
    ],
)
def test_free_side_uses_both_neighbouring_lanes(objects, side):
    assert passing_side(objects, 0, 0) == side
    assert passing_side(objects, 0, STALE + 0.01) is None
    assert passing_side(objects, None, 0) is None


def test_bypass_wait_reverse_forward_and_return_to_route():
    driver = bold()
    command = driver.step(picture(), 0, False, speed=0, ahead=True, bypass_side=-1)
    assert command.state == "bypass-wait" and command.throttle == command.brake == 0
    command = wait_for_bypass(driver)
    assert command.steer == command.throttle == 0 and 0 < command.brake < 1
    for tick in range(22, 80):
        command = driver.step(picture(), tick / 10, True, speed=2, ahead=True, bypass_side=-1)
        if command.state == "bypass-forward":
            break
    assert command.state == "bypass-forward" and 0 < command.throttle < 1 and command.brake == 0
    forward_at = tick
    # Reaching the outward heading must unwind the wheel, even with no box ahead.
    for tick in range(forward_at + 1, forward_at + 70):
        command = driver.step(picture(32), tick / 10, True, speed=2, ahead=False)
        assert command.state != "follow"
        if command.state == "bypass-forward":
            assert abs(command.steer) < 0.1
        if command.state == "bypass-pass":
            break
    assert command.state == "bypass-pass" and command.steer > 0
    pass_at = tick
    for tick in range(pass_at + 1, pass_at + 30):
        command = driver.step(picture(), tick / 10, True, speed=2, ahead=False)
        if command.state == "follow":
            break
    assert command.state == "follow" and driver._phase is None


@pytest.mark.parametrize(("route", "expected"), [(-20, -1), (0, 1), (20, 1)])
def test_both_sides_taken_uses_route_side_then_right(route, expected):
    driver = bold()
    for tick in range(22):
        driver.step(picture(route), tick / 10, False, speed=0, ahead=True, bypass_side=0)
    assert driver._manoeuvre_side == expected


def test_turn_uses_reverse_lock_then_forward_lock_and_finishes():
    driver = bold()
    command = driver.step(picture(150), 0, False, speed=0)
    assert command.state == "turn-reverse" and command.steer == -1 and command.brake == 1
    driver.step(picture(110), 0.5, True, speed=2)
    command = driver.step(picture(55), 1.0, True, speed=2)
    assert command.state == "turn-forward" and command.throttle == 1 and command.brake == 0
    command = driver.step(picture(50), 1.6, True, speed=2)
    assert command.state == "turn-forward" and command.steer == 1
    command = driver.step(picture(20), 2.1, True, speed=2)
    assert command.state == "follow" and driver._phase is None


@pytest.mark.parametrize("angle", [120, -120, 90])
def test_route_must_be_more_than_120_degrees_behind(angle):
    assert bold().step(picture(angle), 0, False, speed=0).state == "follow"


def test_moving_car_is_left_to_turn_and_queue_cannot_start_early():
    assert bold().step(picture(170), 0, True, speed=4).state == "follow"
    driver = bold()
    command = driver.step(picture(), 0, True, speed=0.2, ahead=True, bypass_side=-1)
    assert command.state == "follow"


@pytest.mark.parametrize("angle", [0, 170])
def test_damaged_picture_and_stale_boxes_never_start_a_manoeuvre(angle):
    driver = bold()
    for tick in range(40):
        command = driver.step(
            picture(angle, corrupt=True), tick / 10, False, speed=0, ahead=angle == 0, bypass_side=-1
        )
        assert not command.state.startswith(("bypass-", "turn-"))
    driver = bold()
    for tick in range(40):
        command = driver.step(
            picture(angle), tick / 10, False, speed=0, ahead=angle == 0, bypass_side=-1, boxes_fresh=False
        )
        assert not command.state.startswith(("bypass-", "turn-"))


@pytest.mark.parametrize("kind", ["bypass", "turn"])
def test_reverse_is_bounded_and_ends_when_motion_stops(kind):
    driver = bold()
    if kind == "bypass":
        wait_for_bypass(driver)
    else:
        driver.step(picture(170), 0, False, speed=0)
    start = driver._phase_since
    reading = picture(170 if kind == "turn" else 0)
    driver.step(reading, start + 0.7, True, speed=2, ahead=kind == "bypass", bypass_side=-1)
    command = driver.step(reading, start + 0.8, False, speed=0, ahead=kind == "bypass", bypass_side=-1)
    assert command.brake == command.throttle == command.steer == 0
    assert command.state == f"{kind}-reverse"
    command = driver.step(reading, start + 0.95, False, speed=0, ahead=kind == "bypass", bypass_side=-1)
    assert command.brake == 0 and command.state == f"{kind}-forward"
    driver = bold()
    if kind == "bypass":
        wait_for_bypass(driver)
    else:
        driver.step(reading, 0, False, speed=0)
    start = driver._phase_since
    bound = 1.8 if kind == "bypass" else driver.config.turn_reverse_time
    for tick in range(2, 50):
        now = start + tick / 10
        command = driver.step(reading, now, True, speed=2, ahead=kind == "bypass", bypass_side=-1)
        if command.state == f"{kind}-forward":
            break
    assert command.brake == 0 and command.state == f"{kind}-forward"
    assert now - start <= bound + 0.1


@pytest.mark.parametrize(
    "phase", ["bypass-wait", "bypass-reverse", "bypass-forward", "turn-reverse", "turn-forward"]
)
def test_external_stop_in_every_phase_returns_and_keeps_a_complete_neutral_pad(phase):
    skill = DriveRoute({"style": "bold"})
    bypass = phase.startswith("bypass")
    moving = False
    for tick in range(80):
        observation = Observation(
            picture(0 if bypass else 170),
            moving,
            tick / 10,
            objects=(car(),) if bypass else (),
            objects_time=tick / 10,
        )
        skill.step(observation)
        if skill.driver._last.state == phase:
            break
        moving |= skill.driver._last.state.endswith("reverse")
    assert skill.driver._last.state == phase
    stopped = skill.stop("operator-stop")
    assert stopped.status == "failed" and stopped.reason == "operator-stop"
    assert stopped.pad.left == stopped.pad.right == (0, 0)
    assert stopped.pad.buttons == () and stopped.pad.l2 == stopped.pad.r2 == 0
    assert skill.step(observation) == stopped


def test_turns_stop_after_three_attempts_with_neutral_controls():
    driver = bold(max_recoveries=5)
    for tick in range(400):
        command = driver.step(picture(170), tick / 10, tick > 0, speed=2 if tick else 0)
    assert command.state == "failed-recovery"
    assert command.steer == command.throttle == command.brake == 0
    assert driver._turns == driver._attempts == 3


def test_bypass_retries_other_side_and_respects_existing_recovery_limit():
    driver = bold(max_recoveries=2)
    wait_for_bypass(driver)
    first = driver._manoeuvre_side
    forward_at = None
    for tick in range(22, 120):
        now = tick / 10
        moving = forward_at is None or now - forward_at < 1.6
        command = driver.step(picture(), now, moving, speed=2 if moving else 0, ahead=True, bypass_side=-1)
        if command.state == "bypass-forward" and forward_at is None:
            forward_at = now
        if driver._manoeuvre_side != first:
            break
    assert forward_at is not None and command.state == "bypass-reverse"
    assert driver._manoeuvre_side == -first
    retry_at = tick
    for tick in range(retry_at + 1, retry_at + 180):
        command = driver.step(picture(), tick / 10, False, speed=0, ahead=True, bypass_side=-1)
        if command.state == "failed-recovery":
            break
    assert command.state == "failed-recovery" and driver._attempts == 2
    assert command.steer == command.throttle == command.brake == 0


def test_one_damaged_tick_is_neutral_without_cancelling_the_phase():
    driver = bold()
    driver.step(picture(170), 0, False, speed=0)
    command = driver.step(picture(170, corrupt=True), 0.1, False, speed=0)
    assert command.throttle == command.brake == command.steer == 0
    assert driver._phase == "turn-reverse"
    assert driver.step(picture(170), 0.2, True, speed=2).state == "turn-reverse"


def test_a_far_hairpin_does_not_trigger_a_turn_when_the_near_route_is_ahead():
    assert bold().step(picture(20, far_bearing=170), 0, False, speed=0).state == "follow"


@pytest.mark.parametrize("kind", ["bypass", "turn"])
def test_forward_phase_does_not_push_indefinitely_without_motion(kind):
    driver = bold()
    if kind == "bypass":
        wait_for_bypass(driver)
        reading = picture()
    else:
        reading = picture(170)
        driver.step(reading, 0, False, speed=0)
    now = driver._phase_since + 1.6
    driver.step(reading, now, False, speed=0, ahead=kind == "bypass", bypass_side=-1)
    now += 0.2
    driver.step(reading, now, False, speed=0, ahead=kind == "bypass", bypass_side=-1)
    assert driver._phase == f"{kind}-forward"
    command = driver.step(reading, now + 2.6, False, speed=0, ahead=kind == "bypass", bypass_side=-1)
    assert command.throttle == command.brake == 0
    command = driver.step(reading, now + 2.8, False, speed=0, ahead=kind == "bypass", bypass_side=-1)
    assert command.state != f"{kind}-forward"


def test_fast_speed_does_not_start_a_turn_even_when_map_motion_says_still():
    assert bold().step(picture(170), 0, False, speed=4).state == "follow"
