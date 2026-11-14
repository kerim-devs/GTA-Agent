"""P109: a confirmed stop survives a narrow-lane exit and short detector gaps."""

import json
from pathlib import Path

import pytest

from pilot.contract import Command, Detection, Observation, Reading
from pilot.skills import DriveRoute

FIXTURE = json.loads((Path(__file__).parent / "fixtures/p109_brake_held.json").read_text())
FORWARD = Command(0, 1, 0, "follow")


def replay(*, drop=False):
    skill = DriveRoute({})
    for row in FIXTURE["rows"]:
        detection = FIXTURE["detections"][str(row["frame_id"])]
        objects = tuple(Detection(**o) for o in detection["objects"])
        if drop and 95.0 <= detection["t"] < 95.2:
            objects = ()
        observation = Observation(
            Reading("tilted", "purple", **row["reading"]),
            True,
            row["now"],
            objects=objects,
            objects_time=detection["t"],
        )
        yield row, skill._around(Command(row["steer"], 1, 0, "follow"), observation)


@pytest.mark.parametrize("drop", [False, True])
def test_recorded_full_brake_stays_on_until_the_car_leaves_the_overlap(drop):
    rows = list(replay(drop=drop))
    first = next(row["now"] for row, pad in rows if pad.l2)
    assert first == pytest.approx(94.51664962499973)
    held = [(row, pad) for row, pad in rows if first <= row["now"] <= 95.97]
    assert held and all(pad.l2 == 1 and pad.r2 == 0 for _, pad in held)
    assert all(pad.l2 == 0 for row, pad in rows if row["now"] >= 96.0)


def vehicle(distance, lateral=0):
    h = 1200 / (distance + 6)
    w = h * 1.25
    x = 640 + lateral * w
    return Detection("car", (x - w / 2, 360 - h, x + w / 2, 360), 0.9)


def step(skill, now, objects, *, speed=20, at=None, moving=True):
    reading = Reading("tilted", "purple", 0, 0, 0, False, 1, gps_speed=speed)
    return skill._around(
        FORWARD,
        Observation(reading, moving, now, objects=tuple(objects), objects_time=now if at is None else at),
    )


def approach():
    skill = DriveRoute({})
    for i in range(7):
        pad = step(skill, i * 0.1, [vehicle(34 - 2.1 * i)])
    assert pad.l2 == 1
    return skill


def test_a_few_steady_boxes_do_not_reclassify_a_confirmed_standing_car_as_a_lead():
    skill = approach()
    for i in range(7, 17):
        pad = step(skill, i * 0.1, [vehicle(21.4, 0.6)])
        assert pad.l2 == 1 and pad.r2 == 0


def test_a_missing_speed_does_not_release_a_confirmed_stop_while_still_moving():
    skill = approach()
    for i in range(7, 17):
        pad = step(skill, i * 0.1, [vehicle(21.4, 0.6)], speed=None)
        assert pad.l2 == 1 and pad.r2 == 0


def test_a_confirmed_stop_keeps_only_fresh_memory_through_lost_boxes():
    skill = approach()
    for now in (0.7, 0.9, 1.15):
        pad = step(skill, now, [])
        assert pad.l2 == 1 and pad.r2 == 0
    pad = step(skill, 1.21, [])
    assert pad.l2 == 0 and pad.r2 == 1


@pytest.mark.parametrize("speed,moving", [(2, True), (0, False), (20, False)])
def test_a_stop_does_not_hold_l2_at_rest(speed, moving):
    skill = approach()
    pad = step(skill, 0.7, [vehicle(21.4)], speed=speed, moving=moving)
    assert pad.l2 == 0


def test_a_confirmed_stop_releases_when_the_body_no_longer_overlaps():
    skill = approach()
    for i in range(7, 13):
        pad = step(skill, i * 0.1, [vehicle(21.4, (i - 6) * 0.2)])
    assert pad.l2 == 0


def test_a_completed_stop_waits_without_creeping_and_follows_when_the_gap_opens():
    skill = approach()
    for i in range(7, 16):
        step(skill, i * 0.1, [vehicle(34 - 2.1 * i)])
    pad = step(skill, 1.6, [vehicle(2.5)], speed=0, moving=False)
    assert pad.l2 == pad.r2 == 0
    for i in range(17, 25):
        pad = step(skill, i * 0.1, [vehicle(2.5 + (i - 16))], speed=0, moving=False)
    assert pad.l2 == 0 and pad.r2 > 0


def test_reusing_one_full_brake_detection_does_not_confirm_a_stationary_obstacle():
    skill = DriveRoute({})
    for i in range(3):
        box = vehicle(34 - 2.1 * i)
        pad = step(skill, i * 0.1, [box])
    assert pad.l2 == 1
    for now in (0.3, 0.4, 0.5):
        step(skill, now, [box], at=0.2)
    for i in range(6, 15):
        pad = step(skill, i * 0.1, [box])
    assert pad.l2 == 0
