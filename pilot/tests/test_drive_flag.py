"""A damage flag that stays is driven on slowly; a car that cannot use the picture and stands is given up."""

from dataclasses import asdict, replace

import pytest

from pilot.contract import NEUTRAL_PAD, Command, Observation, Reading
from pilot.drive import Driver
from pilot.sim import SimConfig, Simulator
from pilot.skills import DriveRoute

GOOD = Reading("tilted", "purple", 1.0, 1.0, 1.0, False, 0.95)
FLAG = replace(GOOD, corrupt=True, confidence=0.35)  # the reader's flag as it stood for 70 s on the console
STEP = 1 / 30


def feed(driver, readings, *, start=0.0, speed=5.0, moving=True, **kwargs):
    """The driver's answers to `readings` (a function of the time since `start`) at thirty ticks a second."""
    answers = []
    for i in range(round(readings.seconds / STEP)):
        t = start + i * STEP
        answers.append((t, driver.step(readings(t - start), t, moving, speed=speed, **kwargs)))
    return answers


def over(seconds, reading):
    def readings(_):
        return reading

    readings.seconds = seconds
    return readings


def burst(clean, damage, burst_seconds):
    """`clean` for one second, `damage` for `burst_seconds`, `clean` again for one second."""

    def readings(t):
        return damage if 1.0 <= t < 1.0 + burst_seconds else clean

    readings.seconds = 2.0 + burst_seconds
    return readings


def flag_after(clean, damage, seconds):
    """`clean` for one second, then `damage` to the end of `seconds`."""

    def readings(t):
        return damage if t >= 1.0 else clean

    readings.seconds = seconds
    return readings


def states(answers, begin, end):
    return {command.state for t, command in answers if begin <= t < end}


def first_state(answers, name):
    return next((t for t, command in answers if command.state == name), None)


# The lasting flag.


def test_a_flag_that_stays_is_driven_on_after_a_second_slowly_and_the_time_is_counted():
    clean, flagged = Driver(), Driver()
    on_clean = feed(clean, over(4.0, GOOD))
    on_flag = feed(flagged, flag_after(GOOD, FLAG, 4.0))
    assert states(on_flag, 1.6, 1.95) == {"coast"}  # the first second is read as damage on the cable
    assert states(on_flag, 2.05, 4.0) == {"follow"}
    assert 1.9 <= flagged.flagged_time <= 2.1
    assert on_flag[-1][1].throttle < on_clean[-1][1].throttle  # a limit of four metres a second, not seven
    assert clean.flagged_time == 0


def test_a_flag_that_stays_is_driven_on_with_the_steering_of_the_map():
    right = replace(FLAG, bearing=25.0, far_bearing=25.0)
    driver = Driver()
    answers = feed(driver, over(3.0, right))
    assert {c.state for _, c in answers[-5:]} == {"follow"}
    assert answers[-1][1].steer > 0


@pytest.mark.parametrize("moving", [None, True])
def test_a_flag_that_stays_over_a_car_at_speed_is_never_given_up(moving):
    driver = Driver()
    answers = feed(driver, over(40.0, FLAG), speed=6.0, moving=moving)
    assert first_state(answers, "map-unreadable") is None
    assert states(answers, 1.2, 40.0) == {"follow"}


def test_a_short_burst_of_damage_coasts_and_the_drive_resumes_as_before():
    driver = Driver()
    damage = replace(FLAG, bearing=50.0)  # damage from the cable scrambles the bearing
    answers = feed(driver, burst(GOOD, damage, 0.8))
    assert states(answers, 1.6, 1.8) == {"coast"}
    assert states(answers, 2.0, 2.8) == {"follow"}
    assert driver.flagged_time == 0


def test_a_burst_that_keeps_its_bearing_is_still_a_burst_when_it_is_over_before_a_second():
    driver = Driver()
    answers = feed(driver, burst(GOOD, FLAG, 0.9))
    assert states(answers, 1.6, 1.9) == {"coast"}
    assert states(answers, 2.0, 2.9) == {"follow"}
    assert driver.flagged_time == 0


@pytest.mark.parametrize(
    "change",
    [
        {"route": "none"},
        {"confidence": 0.1},
        {"confidence": None},
        {"arrow": None},
        {"bearing": None},
        {"minimap": "tilted", "route": "red"},
    ],
)
def test_a_flag_without_a_reading_behind_it_is_still_coasted_on(change):
    driver = Driver()
    answers = feed(driver, over(4.0, replace(FLAG, **change)), speed=8.0)
    assert states(answers, 0.6, 4.0) == {"coast"}
    assert driver.flagged_time == 0


def test_a_flag_whose_bearing_will_not_stand_still_is_not_driven_on():
    def jumping(t):
        return replace(FLAG, bearing=0.0 if int(t * 6) % 2 else 60.0)

    jumping.seconds = 4.0
    driver = Driver()
    answers = feed(driver, jumping, speed=8.0)
    assert states(answers, 0.6, 4.0) == {"coast"}
    assert driver.flagged_time == 0


def test_a_flag_that_changes_its_route_starts_its_second_again():
    def changing(t):
        return replace(FLAG, route="yellow" if int(t) % 2 else "purple")

    changing.seconds = 5.0
    driver = Driver()
    answers = feed(driver, changing, speed=8.0)
    assert states(answers, 0.6, 5.0) == {"coast"}


def test_a_clean_tick_in_the_middle_of_a_flag_starts_its_second_again():
    def flickering(t):
        return GOOD if 1.5 <= t < 1.5 + STEP else FLAG

    flickering.seconds = 2.5
    answers = feed(Driver(), flickering, speed=8.0)
    assert states(answers, 0.2, 0.9) == {"coast"}
    assert states(answers, 1.1, 1.45) == {"follow"}  # a second after the start, driven on
    assert states(answers, 2.05, 2.5) == {"coast"}  # and a second again after the clean tick


# The end of a drive that cannot read the picture.


@pytest.mark.parametrize(
    "evidence",
    [{"moving": False, "speed": 0.0}, {"moving": None, "speed": 0.2}, {"moving": False, "speed": None}],
)
@pytest.mark.parametrize("unusable", [{"route": "none"}, {"confidence": 0.1}])
def test_a_car_that_stands_under_a_picture_it_cannot_use_gives_the_drive_up_after_a_few_seconds(
    unusable, evidence
):
    driver = Driver()
    answers = feed(driver, over(1.0, GOOD), speed=8.0)
    answers += feed(driver, over(8.0, replace(FLAG, **unusable)), start=1.0, **evidence)
    gave_up = first_state(answers, "map-unreadable")
    assert gave_up is not None and 4.0 <= gave_up <= 5.2  # three seconds, after the speed has settled
    assert {c.state for t, c in answers if 1.0 <= t < gave_up} == {"coast"}
    command = answers[-1][1]
    assert (command.state, command.steer, command.throttle, command.brake) == ("map-unreadable", 0, 0, 0)
    # It stays given up, the way a held car does, whatever the picture says afterwards.
    assert driver.step(GOOD, 10.0, False, speed=0.0).state == "map-unreadable"


def test_a_car_that_keeps_moving_under_a_picture_it_cannot_use_is_given_up_after_ten_seconds_at_most():
    driver = Driver()
    answers = feed(driver, over(12.0, replace(FLAG, route="none")), speed=8.0, moving=True)
    gave_up = first_state(answers, "map-unreadable")
    assert gave_up is not None and 10.0 <= gave_up <= 10.1


def test_a_car_whose_motion_is_not_known_is_not_given_up_before_ten_seconds():
    driver = Driver()
    answers = feed(driver, over(9.5, replace(FLAG, route="none")), speed=None, moving=None)
    assert states(answers, 0, 9.5) == {"coast"}


def test_a_car_that_moves_again_starts_the_standing_count_again():
    driver = Driver()
    nothing = over(2.5, replace(FLAG, route="none"))
    answers = feed(driver, nothing, moving=False, speed=0.0)
    answers += feed(driver, nothing, start=2.5, moving=True, speed=3.0)
    answers += feed(driver, nothing, start=5.0, moving=False, speed=0.0)
    assert first_state(answers, "map-unreadable") is None
    answers += feed(driver, over(1.0, replace(FLAG, route="none")), start=7.5, moving=False, speed=0.0)
    assert first_state(answers, "map-unreadable") is not None


def test_a_flag_that_stays_over_a_car_that_does_not_move_is_given_up_too():
    driver = Driver()
    answers = feed(driver, flag_after(GOOD, FLAG, 9.0), moving=None, speed=0.0)
    gave_up = first_state(answers, "map-unreadable")
    assert gave_up is not None and 4.0 <= gave_up <= 4.2
    assert (
        1.9 <= driver.flagged_time <= 2.3
    )  # driven on from the second of the flag, until the car was given up


def test_a_flag_over_a_car_whose_map_says_it_stands_is_left_to_the_recovery_and_not_given_up():
    driver = Driver()
    answers = feed(driver, flag_after(GOOD, FLAG, 9.0), moving=False, speed=0.0)
    assert first_state(answers, "recovery-reverse") is not None
    assert first_state(answers, "map-unreadable") is None


def test_a_car_waiting_behind_a_vehicle_under_a_flag_is_given_the_queue_wait_first():
    driver = Driver()
    answers = feed(driver, over(30.0, FLAG), moving=None, speed=0.0, ahead=True)
    assert first_state(answers, "map-unreadable") is None
    answers += feed(driver, over(6.0, FLAG), start=30.0, moving=None, speed=0.0, ahead=True)
    assert first_state(answers, "map-unreadable") is not None


# The skill: what it reports and how it ends.


def at(skill, t, reading, moving=None, **kwargs):
    return skill.step(Observation(replace(reading, **kwargs), moving, t))


def test_the_skill_says_it_drove_on_a_flagged_map_and_for_how_long():
    skill = DriveRoute({})
    result = None
    for i in range(round(4 / STEP)):
        t = i * STEP
        result = at(skill, t, GOOD if t < 1.0 else FLAG, gps_speed=6.0)
        assert result.status == "running"
    assert 1.9 <= result.flagged_seconds <= 2.1  # the first second, waiting for the flag to stay, is not
    assert asdict(result)["flagged_seconds"] == result.flagged_seconds
    clean = DriveRoute({})
    for i in range(round(2 / STEP)):
        result = at(clean, i * STEP, GOOD, gps_speed=6.0)
    assert result.flagged_seconds == 0


def test_the_skill_fails_with_a_reason_of_its_own_when_the_car_stands_and_cannot_read_the_picture():
    skill = DriveRoute({})
    result = None
    for i in range(round(8 / STEP)):
        t = i * STEP
        reading = GOOD if t < 1.0 else replace(FLAG, route="none")
        result = at(skill, t, reading, moving=True if t < 1.0 else False, gps_speed=0.0)
        if result.status != "running":
            break
    assert (result.status, result.reason, result.pad) == ("failed", "map-unreadable", NEUTRAL_PAD)
    assert 3.9 <= t <= 4.3
    assert at(skill, 20.0, GOOD, moving=True, gps_speed=9.0) is result


def test_the_skill_says_map_unreadable_in_its_prompt():
    assert "map-unreadable" in DriveRoute.prompt


# A whole drive in the simulator.


def world(*, held=False, seconds=60):
    config = SimConfig(
        acceleration=0 if held else 4.5,
        noise_degrees=0,
        noise_tail_probability=0,
        outlier_probability=0,
        damage_probability=0,
        path_noise=0,
        path_missing=0,
        speed_noise=0,
        speed_missing=0,
        gps_wrong=0,
        gps_dropout=0,
        max_time=seconds,
    )
    return Simulator([(0, 0), (0, 600)], config=config)


def run(sim, seconds, *, flag_from, flag_until=None):
    """DriveRoute on the simulator whose reader flags every tick from `flag_from`, as the console's did:
    the map is clean, the route and its bearing are right, and no motion can be read from the picture."""
    skill = DriveRoute({"duration": 120})
    result, track = None, []
    while sim.time < seconds:
        reading, moving = sim.observe()
        if flag_from <= sim.time and (flag_until is None or sim.time < flag_until):
            reading, moving = replace(reading, corrupt=True, confidence=0.35), None
        result = skill.step(Observation(reading, moving, sim.time))
        track.append((sim.time, sim.y, sim.speed, skill.driver._last.state))
        if result.status != "running":
            break
        sim.advance(Command(result.pad.left[0], result.pad.r2, result.pad.l2, skill.driver._last.state))
    return result, track


def test_a_flag_that_stays_for_forty_seconds_does_not_leave_the_car_standing():
    sim = world()
    result, track = run(sim, 60, flag_from=10, flag_until=50)
    assert result.status == "running"
    clean = [row for row in track if 4 <= row[0] < 10]
    in_flag = [row for row in track if 14 <= row[0] < 50]
    assert {state for *_, state in in_flag} == {"follow"}
    assert max(row[2] for row in clean) > 4.0  # the clean drive goes faster than the limit of the flagged one
    assert max(row[2] for row in in_flag) <= 4.0
    assert min(row[2] for row in in_flag) > 1.0  # and the car never stands
    assert in_flag[-1][1] - in_flag[0][1] > 70
    assert 35 <= result.flagged_seconds <= 39.5


def test_a_flag_that_stays_over_a_car_that_cannot_move_ends_the_drive_in_seconds_not_minutes():
    sim = world(held=True)
    result, track = run(sim, 60, flag_from=0)
    assert (result.status, result.reason) == ("failed", "map-unreadable")
    assert 2.5 <= track[-1][0] <= 6.0
