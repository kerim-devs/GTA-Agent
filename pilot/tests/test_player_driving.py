"""Player-style selection and bounded decisions using synthetic observations."""

from dataclasses import replace

import numpy as np
import pytest

from pilot import terrain
from pilot.avoid import Avoider
from pilot.cli import CAREFUL, LIVE, drive_config
from pilot.contract import NEUTRAL_PAD, Detection, Observation, Reading
from pilot.drive import Driver
from pilot.getaway import GetAway
from pilot.skills import DriveRoute


def route():
    return Reading("tilted", "yellow", 0.0, 0.0, 0.0, False, 1.0)


def test_styles_reach_the_skill_and_preserve_live_values():
    assert LIVE is CAREFUL
    careful = DriveRoute({"style": "careful"}).driver.config
    bold = DriveRoute({}).driver.config
    assert careful == drive_config(["style=careful"])
    assert bold == drive_config([])
    assert bold.queue_wait == 2.0
    assert careful.queue_wait == 30.0
    assert drive_config(["speed_limit=12", "style=careful"]).speed_limit == 12
    with pytest.raises(ValueError):
        DriveRoute({"style": "reckless"})
    with pytest.raises(SystemExit):
        drive_config(["style=reckless"])


def test_stopped_queue_commits_after_two_seconds_only_with_evidence():
    driver = Driver(drive_config([]))
    for tick in range(20):
        driver.step(route(), tick / 10, moving=False, speed=0, ahead=True, bypass_side=-1)
        assert not driver.bypassing
    driver.step(route(), 2.01, moving=False, speed=0, ahead=True, bypass_side=-1)
    assert driver.bypassing


def test_recovery_changes_lock_until_thirty_metres_have_been_driven():
    driver = Driver(
        replace(
            drive_config([]),
            stuck_time=0.1,
            reverse_time=0.1,
            forward_time=0.5,
            recovery_clear_time=0.1,
            speed_smoothing=0,
        )
    )
    now = 0.0

    def tick(moving, speed):
        nonlocal now
        now += 0.1
        # The generic recovery still handles an off-route stop; straight-road
        # obstructions use the bypass covered in test_round_what_stands.
        return driver.step(replace(route(), bearing=60, far_bearing=60), now, moving=moving, speed=speed)

    def stuck():
        for _ in range(20):
            command = tick(False, 0)
            if command.state == "recovery-reverse":
                return command.steer
        pytest.fail("standing car did not start a bounded recovery")

    first = stuck()
    for _ in range(20):
        tick(True, 10)
    second = stuck()
    assert second == -first
    for _ in range(110):
        tick(True, 10)
    assert stuck() == first


@pytest.mark.parametrize("style", ["bold", "careful"])
def test_explicit_stop_releases_both_styles(style):
    result = DriveRoute({"style": style}).stop("interrupted")
    assert result.pad.l2 == result.pad.r2 == 0
    assert result.pad.left == (0.0, 0.0)
    assert not result.pad.buttons


def test_a_car_standing_in_water_for_two_seconds_ends_the_drive_with_a_neutral_pad(monkeypatch):
    wet = terrain.Terrain((), False, (None,) * 36, True)
    monkeypatch.setattr(terrain, "read", lambda crop: wet)
    skill = DriveRoute({})
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    t = 0.0
    while t < 1.9:
        result = skill.step(Observation(route(), False, t, frame=frame))
        assert result.status == "running"
        t += 0.1
    last = skill.step(Observation(route(), False, 2.1, frame=frame))
    assert last.reason == "dead-or-held" and last.pad == NEUTRAL_PAD
    assert skill.step(Observation(route(), False, 2.2)) == last


def test_a_car_that_moves_with_water_round_the_arrow_drives_on(monkeypatch):
    # A bridge, a ford, the beach: the map shows water and the car is not in it.
    monkeypatch.setattr(terrain, "read", lambda crop: terrain.Terrain((), False, (None,) * 36, True))
    skill = DriveRoute({})
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    t = 0.0
    while t < 6.0:
        result = skill.step(Observation(route(), True, t, frame=frame))
        assert result.status == "running", (t, result.reason)
        t += 0.1


def test_water_seen_once_between_dry_frames_starts_over(monkeypatch):
    seen = iter([True] * 15 + [False] + [True] * 15)
    monkeypatch.setattr(terrain, "read", lambda crop: terrain.Terrain((), False, (None,) * 36, next(seen)))
    skill = DriveRoute({})
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    for index in range(31):
        result = skill.step(Observation(route(), False, index * 0.1, frame=frame))
        assert result.status == "running", index


def test_water_with_the_motion_unknown_or_the_picture_damaged_is_not_standing_in_it(monkeypatch):
    monkeypatch.setattr(terrain, "read", lambda crop: terrain.Terrain((), False, (None,) * 36, True))
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    # On a bridge with the motion unread: never the end of the drive.
    skill = DriveRoute({})
    for index in range(60):
        assert skill.step(Observation(route(), None, index * 0.1, frame=frame)).status == "running"
    # Still and wet for a moment, then thirty seconds of damaged pictures while the car drives, then
    # one more still, wet picture: two ticks of standing, not thirty seconds of it.
    skill = DriveRoute({"duration": 120})
    damaged = replace(route(), corrupt=True)
    assert skill.step(Observation(route(), False, 0.0, frame=frame)).status == "running"
    for index in range(1, 300):
        assert skill.step(Observation(damaged, True, index * 0.1, frame=frame)).status == "running"
    assert skill.step(Observation(route(), False, 30.0, frame=frame)).status == "running"


def test_recoveries_far_apart_are_forgotten_with_the_speed_unread():
    driver = Driver(
        replace(
            drive_config([]),
            stuck_time=0.1,
            reverse_time=0.1,
            forward_time=0.5,
            recovery_clear_time=0.1,
            speed_smoothing=0,
        )
    )
    now = 0.0
    for _ in range(12):  # twelve stops, each freed, each fifteen seconds of driving after the last
        for _ in range(40):
            now += 0.1
            command = driver.step(route(), now, moving=False, speed=None)
            assert command.state != "failed-recovery"
            if command.state == "recovery-reverse":
                break
        for _ in range(150):
            now += 0.1
            assert driver.step(route(), now, moving=True, speed=None).state != "failed-recovery"


def test_water_cannot_extend_the_skill_time_limit(monkeypatch):
    monkeypatch.setattr(terrain, "read", lambda crop: terrain.Terrain((), False, (None,) * 36, True))
    skill = DriveRoute({"duration": 0.1})
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    skill.step(Observation(route(), False, 0, frame=frame))
    result = skill.step(Observation(route(), False, 0.2, frame=frame))
    assert result.reason == "time-limit" and result.pad == NEUTRAL_PAD


def test_bypass_uses_an_observed_free_side_but_never_stale_boxes():
    car = Detection("car", (540, 300, 740, 460), 0.9)
    avoider = Avoider()
    for tick in range(5):  # the car comes closer, which is what gets it gone round without the bypass
        shrunk = Detection(
            "car", (540 + 6 * (5 - tick), 300 + 8 * (5 - tick), 740 - 6 * (5 - tick), 460), 0.9
        )
        normal = avoider.step((shrunk,), tick * 0.1 - 0.5, tick * 0.1 - 0.5)
    normal = avoider.step((car,), 0, 0)
    bypass = avoider.step((car,), 0.1, 0.1, bypass=True)
    assert abs(bypass.steer) > abs(normal.steer)
    assert bypass.steer * normal.steer > 0
    stale = avoider.step((car,), 0.1, 2, bypass=True)
    assert stale.steer == 0 and stale.pedal == 1


def test_getaway_stays_on_a_single_forward_road_despite_police():
    skill = GetAway({})
    skill.terrain = terrain.Terrain(((0, 20), (180, 20)), True, (None,) * 36, False)
    skill.police = (-30, 30)
    assert skill.choose() == (0, "road")
    skill.terrain = terrain.Terrain(((0, 20), (90, 20), (180, 20)), True, (None,) * 36, False)
    skill.police = (-60,)
    assert skill.choose() == (90, "road")
