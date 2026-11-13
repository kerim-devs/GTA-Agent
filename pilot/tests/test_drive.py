"""Public controller behavior, including hostile scalar inputs and timed recovery."""

import json
from dataclasses import fields, replace
from math import atan2, degrees, isfinite, sqrt
from pathlib import Path

import pytest

from pilot.contract import Reading
from pilot.drive import DriveConfig, Driver, _onward, _straight, _target

GOOD = Reading("tilted", "yellow", 0.0, 0.0, 0.0, False, 0.95)


def test_picture_angles_are_relative_to_arrow_and_far_bend_slows() -> None:
    left = Driver().step(replace(GOOD, arrow=30), 0)
    right = Driver().step(replace(GOOD, bearing=30, far_bearing=30), 0)
    assert left.steer < 0 < right.steer
    assert Driver().step(replace(GOOD, far_bearing=70), 0).throttle < Driver().step(GOOD, 0).throttle
    assert Driver().step(replace(GOOD, bearing=-179, far_bearing=-179, arrow=179), 0).steer >= 0


def test_a_small_error_is_steered_against_from_the_sticks_dead_zone_on() -> None:
    """Console drive of 13 November, 17:20: under 0.3 of the stick the car turned by 0 to 1 degree a
    second and at 0.36 by 6. With 0.25 for the first degree past a band of 8 the car was left alone up
    to 11 degrees of error and swung by 20 around the route."""

    def settled(error: float) -> float:
        driver = Driver(DriveConfig(yaw_memory=0.0))  # the law alone, without what the car has still to turn
        for i in range(30):
            command = driver.step(replace(GOOD, bearing=error, far_bearing=error), i / 30)
        return command.steer

    assert settled(2) == 0  # not every pixel of the map's wander is steered against
    assert 0.29 < settled(5) < 0.36  # the first of the turn, not a jerk
    assert 0.36 < settled(10) < 0.47
    assert settled(-10) == -settled(10)
    assert settled(60) > 0.8


def test_the_turn_that_has_still_to_show_is_taken_off_the_error() -> None:
    """Kerim's drives of 12 and 13 November and three of the pilot's: the car turns by 77 degrees a
    second per unit of the stick past its dead zone, and the turn shows on the map 0.2 to 0.7 s after
    the stick. An error that cannot have changed yet was steered against for all of that time."""

    def drive(memory: float, errors) -> Driver:
        driver = Driver(DriveConfig(yaw_memory=memory))
        for i, error in enumerate(errors):
            driver.step(replace(GOOD, bearing=error, far_bearing=error), i / 30)
        return driver

    # Half a second of 20 degrees that do not move: the stick lies lower than the error alone asks.
    plain, minded = drive(0.0, [20.0] * 15), drive(1.0, [20.0] * 15)
    assert plain._pending(0.5) > 5 and 0.36 < minded._last.steer < plain._last.steer - 0.05
    # A hard turn of a third of a second, then the map shows 6 degrees left: the car has 10 more
    # still to come, and the stick does not go on turning it into what the map shows.
    after = [60.0] * 10 + [6.0] * 10
    assert drive(0.0, after)._last.steer > 0.1
    assert drive(1.0, after)._last.steer <= 0
    # What was steered more than the answer's time ago has shown, and counts no more.
    rested = drive(1.0, [60.0] * 10 + [0.0] * 60)
    assert abs(rested._pending(70 / 30)) < 0.5
    # A stop ends the account: nothing is carried over a picture that is not the map.
    stopped = drive(1.0, [60.0] * 10)
    stopped.step(replace(GOOD, minimap="flat"), 11 / 30)
    assert stopped._pending(11 / 30) == 0


def ahead(*points):
    return replace(GOOD, path=tuple(points))


def test_the_aim_lies_far_out_on_a_straight_way_and_short_where_it_bends(monkeypatch) -> None:
    """Country road of 13 November, 18:10: three or four pixels beside the route are 25 degrees at
    8 px, the car swung across the line every 2.7 s with the stick at its stop."""
    monkeypatch.delenv("PILOT_AIM_AB", raising=False)
    config = DriveConfig()
    straight = [(0.0, float(y)) for y in range(12, 80, 6)]
    assert _straight(straight, config, False)
    # A corner behind the path's first point, and one between the car and it: the short aim.
    assert not _straight([(0.0, 12.0), (0.0, 18.0), (6.0, 18.0), (12.0, 18.0), (40.0, 18.0)], config, False)
    assert not _straight([(3.0, 14.0), (9.0, 14.0), (15.0, 14.0), (40.0, 14.0)], config, False)
    # A car a few pixels beside a straight route keeps the far aim, one far off it gets the short one.
    assert _straight([(3.0, float(y)) for y in range(12, 80, 6)], config, False)
    assert not _straight([(9.0, float(y)) for y in range(12, 80, 6)], config, False)
    # Too little of the way in the picture, or a waver round the limit once far.
    assert not _straight([(0.0, 12.0), (0.0, 30.0)], config, False)
    wavering = [(5.5, float(y)) for y in range(12, 80, 6)]
    assert not _straight(wavering, config, False) and _straight(wavering, config, True)
    driver = Driver()
    driver.step(ahead(*straight), 0)
    assert driver.aim_px == config.straight_lookahead_px
    driver.step(ahead((0.0, 12.0), (0.0, 18.0), (6.0, 18.0), (12.0, 18.0), (40.0, 18.0)), 0.03)
    assert driver.aim_px == config.lookahead_px
    # Beside the route the far aim asks for less of the stick than the short one did.
    beside = [(4.0, float(y)) for y in range(12, 80, 6)]
    far = Driver().step(ahead(*beside), 0).steer
    near = Driver(DriveConfig(straight_lookahead_px=8.0)).step(ahead(*beside), 0).steer
    assert 0 < far < near


def test_the_comparison_switch_alternates_the_aims_by_the_clock(monkeypatch) -> None:
    straight = [(0.0, float(y)) for y in range(12, 80, 6)]
    monkeypatch.setenv("PILOT_AIM_AB", "30")
    driver = Driver()
    seen = {}
    for t in (0.0, 29.9, 30.0, 59.9, 60.0):
        driver.step(ahead(*straight), t)
        seen[t] = driver.aim_px
    assert seen == {0.0: 20.0, 29.9: 20.0, 30.0: 8.0, 59.9: 8.0, 60.0: 20.0}


@pytest.mark.parametrize("minimap", ["none", "flat", "unknown", None, [], {}])
def test_idle_is_neutral(minimap: object) -> None:
    driver = Driver()
    driver.step(GOOD, 0)
    cmd = driver.step(replace(GOOD, minimap=minimap), 0.1)
    assert (cmd.steer, cmd.throttle, cmd.brake, cmd.state) == (0, 0, 0, "idle")


@pytest.mark.parametrize(
    "bad",
    [
        replace(GOOD, corrupt=True),
        replace(GOOD, confidence=0.1),
        replace(GOOD, route="none"),
        replace(GOOD, bearing=None),
        replace(GOOD, arrow=None),
    ],
)
def test_coast_holds_briefly_then_releases(bad: Reading) -> None:
    driver = Driver()
    first = driver.step(replace(GOOD, bearing=20, far_bearing=20), 0)
    held = driver.step(bad, 0.2)
    released = driver.step(bad, 0.31)
    assert held.state == "coast"
    assert (held.steer, held.throttle) == (first.steer, first.throttle)
    assert (released.steer, released.throttle, released.brake) == (0, 0, 0)
    assert driver.step(GOOD, 0.4).state == "follow"


def test_route_gone_brakes_but_does_not_reverse_forever() -> None:
    driver = Driver()
    missing = replace(GOOD, route="none")
    driver.step(GOOD, 0)
    driver.step(missing, 0.1)
    assert driver.step(missing, 1.9).state == "coast"
    assert driver.step(missing, 2.11, True).brake > 0
    stopped = driver.step(missing, 2.2, False)
    assert stopped.state == "route-gone" and stopped.brake == 0
    assert driver.step(missing, 3, None).brake == 0
    assert driver.step(GOOD, 3.1).state == "follow"
    driver.step(replace(GOOD, minimap="flat"), 4)
    assert driver.step(missing, 4.1).state == "coast"


def test_one_outlier_does_not_jerk_the_wheel() -> None:
    driver = Driver()
    first = driver.step(GOOD, 0)
    jump = driver.step(replace(GOOD, bearing=130), 1 / 30)
    assert jump.steer == first.steer and jump.throttle == first.throttle
    assert driver.step(GOOD, 2 / 30).state == "follow"
    for i in range(3, 20):
        cmd = driver.step(replace(GOOD, bearing=100, far_bearing=100), i / 30)
    assert cmd.steer > 0  # A real, persistent new heading is eventually accepted.


def test_completely_held_car_ends_after_one_try_with_latched_neutral() -> None:
    driver = Driver()
    reading = replace(GOOD, bearing=25, far_bearing=25)
    phases = []
    previous = ""
    for i in range(600):
        cmd = driver.step(reading, i / 30, False)
        if cmd.state != previous:
            phases.append(cmd.state)
            previous = cmd.state
        if cmd.state == "recovery-reverse":
            assert cmd.brake > 0 and cmd.throttle == 0 and cmd.steer < 0
        if cmd.state == "recovery-forward":
            assert cmd.throttle > 0 and cmd.brake == 0 and cmd.steer > 0
    assert phases.count("recovery-reverse") == 1
    assert phases.count("recovery-forward") == 1
    assert cmd.state == "dead-or-held"
    assert (cmd.throttle, cmd.brake, cmd.steer) == (0, 0, 0)
    assert driver.step(reading, 30, True).state == "dead-or-held"


def test_unknown_motion_and_brief_damage_do_not_invent_or_hide_stuck() -> None:
    driver = Driver()
    for i in range(300):
        assert driver.step(GOOD, i / 30, None).state == "follow"
    for i in range(300, 400):
        reading = replace(GOOD, corrupt=True) if i % 10 == 0 else GOOD
        cmd = driver.step(reading, i / 30, False)
        if cmd.state == "recovery-reverse":
            break
    assert cmd.state == "recovery-reverse"


def test_successful_forward_motion_resets_consecutive_attempt_limit() -> None:
    driver = Driver()
    for cycle in range(5):
        states = set()
        for i in range(270):
            t = cycle * 9 + i / 30
            states.add(driver.step(GOOD, t, i >= 110).state)
        assert "recovery-reverse" in states
        assert "failed-recovery" not in states


@pytest.mark.parametrize("field", list(Reading.__dataclass_fields__))
@pytest.mark.parametrize(
    "value", [None, float("nan"), float("inf"), -float("inf"), 1e308, 10**400, "bad", [], {}, True]
)
def test_hostile_fields_are_total_and_bounded(field: str, value: object) -> None:
    driver = Driver()
    for t in (0, 0.1, -1, 0, float("nan"), float("inf"), None, "bad", 10**400, 1e308):
        cmd = driver.step(replace(GOOD, **{field: value}), t, None)
        assert all(isfinite(v) for v in (cmd.steer, cmd.throttle, cmd.brake))
        assert -1 <= cmd.steer <= 1
        assert 0 <= cmd.throttle <= 1 and 0 <= cmd.brake <= 1


def test_bad_reading_objects_and_backwards_time_release_controls() -> None:
    driver = Driver()
    assert driver.step(GOOD, 5).throttle > 0
    cmd = driver.step(GOOD, 4)
    assert cmd.throttle == cmd.brake == cmd.steer == 0
    for reading in (None, {}, [], "bad", 1):
        assert driver.step(reading, 6).state == "idle"


@pytest.mark.parametrize(
    "kwargs",
    [{"steer_gain": float("nan")}, {"hold_time": -1}, {"cruise_throttle": 2}, {"max_recoveries": 1.5}],
)
def test_invalid_configuration_is_rejected_at_construction(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        DriveConfig(**kwargs)


def test_route_absence_does_not_count_unreadable_time_or_reapply_brake() -> None:
    driver = Driver()
    missing = replace(GOOD, route="none")
    driver.step(missing, 0)
    driver.step(replace(missing, corrupt=True), 0.1)
    driver.step(replace(missing, corrupt=True), 10)
    assert driver.step(missing, 10.1).state == "coast"
    assert driver.step(missing, 12.2, True).brake == 1
    assert driver.step(missing, 12.3, False).brake == 0
    assert driver.step(missing, 12.4, None).brake == 0
    assert driver.step(missing, 12.5, True).brake == 0


def test_recovery_survives_short_damage_and_one_moving_tick_is_not_success() -> None:
    driver = Driver()
    phase_started = None
    sent_motion = False
    reverses = 0
    last_active_state = ""
    for i in range(900):
        now = i / 30
        moving = False
        if phase_started is not None and now - phase_started > 2.1 and not sent_motion:
            moving, sent_motion = True, True
        reading = replace(GOOD, corrupt=True) if i % 10 == 0 else GOOD
        command = driver.step(reading, now, moving)
        if command.state == "coast":
            continue
        if command.state == "recovery-reverse" and last_active_state != command.state:
            reverses += 1
            phase_started, sent_motion = None, False
        if command.state == "recovery-forward" and last_active_state != command.state:
            phase_started = now
        last_active_state = command.state
    assert reverses == 3
    assert command.state == "failed-recovery"


def test_same_direction_bend_does_not_cancel_turn():
    cmd = Driver().step(replace(GOOD, bearing=20, far_bearing=55), 0)
    assert cmd.state == "follow" and cmd.steer > 0


def test_damaged_route_requires_recent_clean_agreement_and_cannot_renew_it():
    clean = replace(GOOD, bearing=20, far_bearing=40)
    damage = replace(clean, corrupt=True, confidence=0.35, bearing=23)
    assert Driver().step(damage, 0).throttle == 0
    driver = Driver()
    driver.step(clean, 0)
    for time in (0.1, 0.2, 0.3, 0.4, 0.49):
        cmd = driver.step(damage, time)
        assert cmd.state == "follow" and cmd.steer > 0
    released = driver.step(damage, 0.51)
    assert released.state == "coast"
    assert released.steer == released.throttle == released.brake == 0


@pytest.mark.parametrize(
    "change",
    [
        {"bearing": -30},
        {"bearing": 65},
        {"route": "purple"},
        {"confidence": 0.1},
        {"bearing": None},
        {"arrow": None},
    ],
)
def test_disagreeing_or_unusable_damage_cannot_take_control(change):
    clean = replace(GOOD, bearing=20, far_bearing=40)
    driver = Driver()
    first = driver.step(clean, 0)
    damage = replace(clean, corrupt=True, confidence=0.35)
    damage = replace(damage, **change)
    held = driver.step(damage, 0.1)
    assert held.state == "coast" and held.steer == first.steer
    released = driver.step(damage, 0.31)
    assert released.steer == released.throttle == released.brake == 0


def test_leaving_vehicle_map_clears_damage_trust():
    clean = replace(GOOD, bearing=20)
    driver = Driver()
    driver.step(clean, 0)
    driver.step(replace(clean, minimap="flat"), 0.1)
    cmd = driver.step(replace(clean, corrupt=True, confidence=0.35), 0.2)
    assert cmd.state == "coast" and cmd.throttle == cmd.steer == 0


def test_small_map_jitter_does_not_create_predictive_countersteering():
    driver = Driver()
    for i in range(120):
        reading = replace(GOOD, bearing=3 if i % 2 else -3)
        cmd = driver.step(reading, i / 30, True)
        assert cmd.state == "follow" and cmd.steer == 0


def test_speed_brake_comes_in_bounded_pulses_and_not_below_the_floor():
    driver = Driver(DriveConfig(brake_pulse=0.35, brake_rest=1.0, brake_floor=7.0))
    held = [driver._pulsed(0.5, 12.0, t / 10) for t in range(30)]
    # 0.35 s on, a second off, and on again: never one unbroken hold.
    assert held[:4] == [0.5] * 4 and held[4:14] == [0.0] * 10 and held[14] == 0.5
    assert driver._pulsed(0.5, 6.0, 5.0) == 0.0
    assert Driver()._pulsed(0.5, 3.0, 0.0) == 0.5  # the defaults leave the brake as it was


def test_a_wider_curvature_baseline_and_a_trimmed_tail_lift_the_limit_on_a_straight():
    # A straight route as the reader gives it: whole pixels, and a hook along the minimap's rim at the end.
    xs = (0, 0, 1, 1, 0, 0, 1, 1, 0, 0, 1)
    path = (
        *tuple((float(x), 13.0 + 6 * i) for i, x in enumerate(xs)),
        (6.0, 78.0),
        (12.0, 80.0),
        (18.0, 81.0),
    )
    live = {"speed_limit": 22.0, "lateral_acceleration": 7.0, "map_scale_min": 0.7}
    plain = Driver(DriveConfig(**live))._speed_limit(path, 0.0, 10.0)
    wide = Driver(DriveConfig(**live, curve_step=3, curve_trim=3))._speed_limit(path, 0.0, 10.0)
    assert plain < 13 and wide == 22.0


def test_a_bend_ahead_is_not_steered_away_from() -> None:
    """Console drive of 13 November, 18:32, 206 to 216 s: a right turn ahead, 22 px out at 210.6 s.
    The path's first segment, 13 px ahead of the car, began to lean into the turn; continued back
    under the arrow it passed the car on its left, the aim at 8 px lay 6 to 28 degrees to the left
    and the stick went to 0.65 to the left, into a right turn."""
    rows = json.loads((Path(__file__).parent / "fixtures" / "p95-corner.json").read_text())
    names = {field.name for field in fields(Reading)}
    driver, sticks = Driver(), {}
    for row in rows:
        reading = {k: v for k, v in row["reading"].items() if k in names}
        reading["path"], reading["blips"] = tuple(tuple(p) for p in reading["path"]), ()
        command = driver.step(Reading(**reading), row["t"], True, speed=reading["gps_speed"])
        sticks[row["t"]] = command.steer
        if 210.3 < row["t"] < 210.9:
            # The line alone, as before, lies to the left there; by way of the car's direction it does not.
            path, arrow = reading["path"], reading["arrow"]
            alone, minded = _target(path, 8.0), _target(path, 8.0, arrow)
            assert degrees(atan2(alone[0], alone[1])) - arrow < -4
            assert degrees(atan2(minded[0], minded[1])) - arrow > -1
    before = [stick for t, stick in sticks.items() if 209.5 <= t < 211.0]
    assert len(before) > 30 and min(before) > -0.05
    assert max(stick for t, stick in sticks.items() if 211.0 <= t < 212.5) > 0.3  # and then to the right


def test_the_aim_under_the_arrow_goes_by_the_cars_own_way_to_the_line() -> None:
    def corner(ahead: float):
        return ((sqrt(121 - ahead * ahead), ahead), (17.0, ahead), (23.0, ahead))

    # A right angle under the arrow, 9 px ahead: straight on until the line comes within the aim's reach.
    assert _target(corner(9), 8.0, 0.0) == pytest.approx((0.0, 8.0))
    # 6 px ahead: on the line, as before.
    assert _target(corner(6), 8.0, 0.0) == pytest.approx(_target(corner(6), 8.0))
    assert _target(corner(6), 8.0, 0.0)[0] > 5
    # A car beside a straight route does not meet it ahead: the line's nearest stretch, as before.
    beside = tuple((7.0, float(y)) for y in (8.5, 14.5, 20.5))
    assert _target(beside, 8.0, 0.0) == pytest.approx(_target(beside, 8.0))
    # A car that heads away from the line, or whose way meets the path beyond its first point: as before.
    assert _target(corner(9), 8.0, 180.0) == pytest.approx(_target(corner(9), 8.0))
    crossing = ((-6.0, 10.0), (-2.0, 14.0), (2.0, 18.0))
    assert _target(crossing, 8.0, 0.0) == pytest.approx(_target(crossing, 8.0))


def test_the_middle_aim_steers_where_the_paths_beginning_goes_on_from_the_car(monkeypatch) -> None:
    monkeypatch.delenv("PILOT_AIM_AB", raising=False)
    config = DriveConfig()
    # A bend 30 px ahead: not straight over 40 px, but the beginning goes on from the car.
    bend = [(0.0, 12.0), (0.0, 18.0), (0.0, 24.0), (2.0, 30.0), (7.0, 34.0), (13.0, 35.0), (19.0, 35.0)]
    assert not _straight(bend, config, False) and _onward(bend, config, False, 0.0)
    driver = Driver()
    driver.step(replace(GOOD, path=tuple(bend)), 0)
    assert driver.aim_px == config.bend_lookahead_px
    # A right angle 6 or 9 px ahead under the arrow: the path begins round it, and the short aim stays.
    for ahead in (6.0, 9.0):
        hidden = [(sqrt(121 - ahead * ahead), ahead), (17.0, ahead), (23.0, ahead), (29.0, ahead)]
        assert not _onward(hidden, config, False, 0.0)
        driver = Driver()
        driver.step(replace(GOOD, path=tuple(hidden)), 0)
        assert driver.aim_px == config.lookahead_px
    # A car 7 px beside a straight route that runs its way: brought back by the middle aim.
    beside = [(7.0, float(y)) for y in (8.5, 14.5, 20.5, 26.5, 32.5, 38.5, 44.5, 50.5)]
    assert not _straight(beside, config, False) and _onward(beside, config, False, 0.0)
    # A waver round the limit keeps what it was.
    # The beginning 29 degrees off the line to its first point, and far off the car's heading.
    leaning = [(0.0, 12.0), (2.9, 17.2), (5.8, 22.4), (8.7, 27.6)]
    assert not _onward(leaning, config, False, -30.0) and _onward(leaning, config, True, -30.0)
