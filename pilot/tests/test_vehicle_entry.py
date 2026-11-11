"""Vehicle-entry safety and observable outcomes, without hardware."""

import math

import pytest

from pilot.contract import NEUTRAL_PAD, Detection, Reading
from pilot.skills import Observation
from pilot.vehicle_entry import DOOR_WAIT, MAX_ATTEMPTS, EnterVehicle


def px(x0, y0, x1, y1):
    return (x0 * 1280, y0 * 720, x1 * 1280, y1 * 720)


FAR = Detection("car", px(0.43, 0.50, 0.57, 0.68), 0.9)
NEAR = Detection("car", px(0.30, 0.45, 0.70, 0.90), 0.9)


def same(target, detection):
    return target.kind == detection.kind and target.box == pytest.approx(
        tuple(value / size for value, size in zip(detection.box, (1280, 720, 1280, 720), strict=True))
    )


def obs(time, objects=(FAR,), *, age=0.0, minimap="flat", corrupt=False, delivered=True):
    return Observation(
        Reading(minimap, "none", None, None, None, corrupt, 1.0),
        False,
        time,
        objects=objects,
        objects_time=time - age if delivered else None,
    )


@pytest.mark.parametrize(
    "args",
    [
        None,
        [],
        {"other": 1},
        {"duration": True},
        {"duration": "2"},
        {"duration": math.nan},
        {"duration": math.inf},
        {"kind": "bus"},
        {"kind": []},
    ],
)
def test_arguments_reject_invalid_values(args):
    with pytest.raises(ValueError):
        EnterVehicle(args)


def test_metadata_clamping_and_short_hard_limit():
    assert EnterVehicle.name == "enter_vehicle"
    assert len(EnterVehicle.prompt) <= 400
    assert EnterVehicle({"duration": 100}).limit == 25
    skill = EnterVehicle({"duration": -10})
    assert skill.limit == 0.1
    skill.step(obs(8, (), delivered=True))
    result = skill.step(obs(8.11, ()))
    assert result.status == "failed" and result.reason == "time up"
    assert result.pad == NEUTRAL_PAD


def test_release_before_triangle_and_neutral_for_entire_wait():
    skill = EnterVehicle({})
    assert skill.step(obs(0, (NEAR,))).pad == NEUTRAL_PAD
    # Held for three ticks of the loop: a single tick is easy for the console to miss.
    for time in (0.04, 0.07, 0.10):
        tap = skill.step(obs(time, (), delivered=False, corrupt=True) if time > 0.04 else obs(time, (NEAR,)))
        assert tap.pad.buttons == ("triangle",)
        assert tap.pad.left == tap.pad.right == (0, 0)
    for time in (0.14, 0.2, 0.7, 1.5, 2.9, DOOR_WAIT + 0.02):
        result = skill.step(obs(time, (), delivered=False, corrupt=True))
        assert result.status == "running" and result.pad == NEUTRAL_PAD
    result = skill.step(obs(DOOR_WAIT + 0.05, (NEAR,)))
    assert result.pad.left[1] < 0 and result.pad.buttons == ()


def test_a_vehicle_map_after_the_press_must_last_a_second():
    skill = EnterVehicle({})
    skill.step(obs(0, (NEAR,)))
    assert skill.step(obs(0.04, (NEAR,))).pad.buttons == ("triangle",)
    for time, minimap, corrupt in (
        (0.2, "tilted", False),
        (1.03, "tilted", False),  # on foot the reader held a false vehicle map for 0.83 s
        (1.1, "flat", False),
        (1.2, "tilted", False),
        (1.6, "flat", True),  # a damaged tick neither counts nor starts over
        (2.19, "tilted", False),
    ):
        result = skill.step(obs(time, (), minimap=minimap, corrupt=corrupt, delivered=False))
        assert result.status == "running" and result.pad == NEUTRAL_PAD
    result = skill.step(obs(2.2, minimap="tilted"))
    assert result.status == "done" and result.reason == "entered vehicle"
    assert result.pad == NEUTRAL_PAD
    assert skill.step(obs(3)) == result


def test_a_vehicle_map_before_any_press_is_believed_only_when_it_stays():
    skill = EnterVehicle({})
    for time in (0, 0.5, 0.83):
        assert skill.step(obs(time, minimap="tilted")).pad == NEUTRAL_PAD
    # The map is flat again: it was the reader, and the walk to the car goes on.
    assert skill.step(obs(0.9)).pad.left[1] < 0
    for time in (1.0, 2.0, 2.99):
        assert skill.step(obs(time, minimap="tilted")).status == "running"
    result = skill.step(obs(3.0, minimap="tilted"))
    assert result.status == "done" and result.reason == "already in a vehicle"


@pytest.mark.parametrize("bad", ["stale", "missing", "no_stamp", "future", "corrupt", "no_map"])
def test_unusable_observation_releases_previous_motion(bad):
    skill = EnterVehicle({})
    assert skill.step(obs(0)).pad.left[1] < 0
    kwargs = {
        "stale": {"age": 0.501},
        "missing": {"objects": ()},
        "no_stamp": {"delivered": False},
        "future": {"age": -0.1},
        "corrupt": {"corrupt": True},
        "no_map": {"minimap": "none"},
    }[bad]
    assert skill.step(obs(0.51, **kwargs)).pad == NEUTRAL_PAD


def test_frozen_capture_expires_and_missing_scan_has_short_pulses():
    skill = EnterVehicle({})
    for tick in range(32):
        now = tick / 60
        result = skill.step(obs(now, age=now))
        if now > 0.5:
            assert result.pad == NEUTRAL_PAD
    longest = held = 0
    skill = EnterVehicle({})
    for tick in range(151):
        result = skill.step(obs(tick / 30, ()))
        held = held + 1 if result.pad.right != (0, 0) else 0
        longest = max(longest, held)
    assert longest / 30 <= 0.5
    assert result.status == "failed" and result.reason == "nothing found"


def test_target_stays_on_visible_vehicle_despite_larger_competitor():
    skill = EnterVehicle({})
    skill.step(obs(0))
    for tick in range(1, 20):
        delta = 0.004 * (-1) ** tick
        tracked = Detection("car", px(0.43 + delta, 0.50, 0.57 + delta, 0.68), 0.9)
        competitor = Detection("car", px(0.57, 0.40, 0.97, 0.94), 0.99)
        skill.step(obs(tick / 30, (competitor, tracked)))
        assert same(skill.target, tracked)
    # Brief detector loss does not transfer the target to another car.
    result = skill.step(obs(0.7, (competitor,)))
    assert result.pad == NEUTRAL_PAD and same(skill.target, tracked)


def test_kind_filter_and_foreground_preference():
    motorcycle = Detection("motorcycle", px(0.45, 0.5, 0.55, 0.65), 0.9)
    for kind, expected in (("motorcycle", motorcycle), ("car", NEAR), ("any", NEAR)):
        skill = EnterVehicle({"kind": kind})
        skill.step(obs(0, (motorcycle, NEAR, FAR)))
        assert same(skill.target, expected)


def test_approach_centers_before_walking_and_slows_down():
    skill = EnterVehicle({})
    side = Detection("car", px(0.7, 0.5, 0.85, 0.7), 0.9)
    pad = skill.step(obs(0, (side,))).pad
    assert pad.left == (0, 0) and pad.right[0] > 0
    speed_far = -EnterVehicle({}).step(obs(0)).pad.left[1]
    larger = Detection("car", px(0.4, 0.5, 0.6, 0.76), 0.9)
    speed_larger = -EnterVehicle({}).step(obs(0, (larger,))).pad.left[1]
    assert 0 < speed_larger < speed_far


@pytest.mark.parametrize("phase", ["approach", "tap", "wait", "retry"])
def test_stop_and_replacement_release_every_phase(phase):
    skill = EnterVehicle({})
    skill.step(obs(0, (NEAR,)))
    skill.phase = phase
    result = skill.stop("replaced")
    assert result.status == "failed" and result.reason == "replaced"
    assert result.pad == NEUTRAL_PAD
    assert skill.step(obs(0.1)).pad == NEUTRAL_PAD
    # The replacement begins with its own released state, independent of the old one.
    assert EnterVehicle({}).step(obs(0.2, (NEAR,))).pad == NEUTRAL_PAD


def test_retries_and_every_terminal_outcome_are_bounded_and_neutral():
    skill = EnterVehicle({})
    presses = 0
    wait_started = None
    pressed = False
    for tick in range(751):
        now = tick / 30
        result = skill.step(obs(now, (NEAR,)))
        assert set(result.pad.buttons) <= {"triangle"}
        assert result.pad.l2 == result.pad.r2 == 0
        if result.pad.buttons:
            assert result.pad.left == result.pad.right == (0, 0)
            if not pressed:
                presses += 1
                wait_started = now
        elif wait_started is not None and now - wait_started < DOOR_WAIT:
            assert result.pad == NEUTRAL_PAD
        pressed = bool(result.pad.buttons)
        if result.status != "running":
            break
    assert presses == MAX_ATTEMPTS
    assert now <= 25 and result.status == "failed" and result.reason == "door never opened"
    assert result.pad == NEUTRAL_PAD


def test_absent_delivery_and_unreachable_target_have_actionable_reasons():
    missing = EnterVehicle({})
    missing.step(obs(0, delivered=False))
    assert missing.step(obs(5, delivered=False)).reason == "no detections delivered at all"
    unreachable = EnterVehicle({})
    unreachable.step(obs(0))
    result = unreachable.step(obs(25))
    assert result.reason == "could not reach it" and result.pad == NEUTRAL_PAD


def test_invalid_observation_and_reversed_clock_fail_neutrally():
    skill = EnterVehicle({})
    skill.step(obs(1))
    assert skill.step(obs(0)).pad == NEUTRAL_PAD
    assert skill.finished.status == "failed"
    assert EnterVehicle({}).step(None).reason == "invalid observation"
    broken = Detection("car", px(0.4, 0.5, math.nan, 0.9), 0.9)
    skill = EnterVehicle({})
    skill.step(obs(0, (broken,)))
    assert skill.target is None


def test_the_number_of_attempts_is_bounded_on_its_own(monkeypatch):
    # With the real waits the time limit ends the skill first; shorten them to reach the bound.
    monkeypatch.setattr("pilot.vehicle_entry.DOOR_WAIT", 1.0)
    monkeypatch.setattr("pilot.vehicle_entry.RETRY_APPROACH", 0.5)
    skill = EnterVehicle({})
    presses, pressed = 0, False
    for tick in range(751):
        result = skill.step(obs(tick / 30, (NEAR,)))
        presses += bool(result.pad.buttons) and not pressed
        pressed = bool(result.pad.buttons)
        if result.status != "running":
            break
    assert presses == MAX_ATTEMPTS and tick / 30 < 10
    assert result.status == "failed" and result.reason == "door never opened"


def test_a_doubtful_detection_is_not_walked_to():
    skill = EnterVehicle({})
    doubtful = Detection("car", NEAR.box, 0.3)
    result = skill.step(obs(0, (doubtful,)))
    assert skill.target is None and result.pad.left == (0, 0) and result.pad.buttons == ()
