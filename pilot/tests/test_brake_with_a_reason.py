"""P107: the recorded brake must have a path and stop when its reason ends."""

import json
from pathlib import Path

import pytest

from pilot.contract import Command, Detection, Observation, Reading
from pilot.skills import DriveRoute

FIXTURE = Path(__file__).parent / "fixtures/p107_brakes.json"


def replay(name):
    case = json.loads(FIXTURE.read_text())[name]
    skill = DriveRoute({})
    for row in case["rows"]:
        detection = case["detections"][str(row["frame_id"])]
        reading = Reading("tilted", "purple", **row["reading"])
        obs = Observation(
            reading,
            True,
            row["now"],
            objects=tuple(Detection(**o) for o in detection["objects"]),
            objects_time=detection["t"],
        )
        yield row, skill._around(Command(row["steer"], 1, 0, "follow"), obs)


@pytest.mark.parametrize("name", ["oncoming_bend", "oncoming_second"])
def test_recorded_opposite_lane_traffic_does_not_request_l2(name):
    rows = list(replay(name))
    assert any(r["before"] for r, _ in rows)
    assert all(p.l2 == 0 for _, p in rows)


def test_a_slower_recorded_car_gets_a_lift_before_a_full_stop():
    rows = list(replay("slower"))
    original = sum(r["dt"] for r, _ in rows if r["before"])
    braking = [(r, p) for r, p in rows if p.l2]
    assert sum(r["dt"] for r, _ in braking) < original / 2
    assert not braking or braking[-1][0]["reading"]["gps_speed"] > 8
    assert all(p.r2 == 0 for _, p in braking)


@pytest.mark.parametrize("name", ["p106_queue", "p106_lorry"])
def test_p106_first_brake_tick_is_preserved_with_the_recorded_bearings(name):
    rows = list(replay(name))
    expected = next(r["now"] for r, _ in rows if r["before"])
    row, pad = next((r, p) for r, p in rows if p.l2)
    assert row["now"] == expected
    assert pad.l2 == 1 and pad.r2 == 0


def test_the_half_hidden_queue_keeps_the_pedal_off_through_the_gps_gap_and_stop():
    rows = list(replay("hidden_queue"))
    assert next(r["now"] for r, p in rows if p.l2) <= next(r["now"] for r, _ in rows if r["before"])
    waiting = [(r, p) for r, p in rows if r["now"] >= 80.3]
    assert waiting and all(p.r2 == 0 for _, p in waiting)
    assert all(p.l2 == 1 for r, p in waiting if (r["reading"]["gps_speed"] or 0) > 2)
    assert all(p.l2 == 0 for r, p in waiting if (r["reading"]["gps_speed"] or 0) <= 2)


def test_a_recorded_brake_releases_while_still_following_at_twelve_metres_a_second():
    rows = list(replay("slower_release"))
    original = [r for r, _ in rows if r["before"]]
    braking = [r for r, p in rows if p.l2]
    assert braking and sum(r["dt"] for r in braking) < sum(r["dt"] for r in original) / 2
    assert braking[-1]["now"] < original[-1]["now"]
    assert braking[-1]["reading"]["gps_speed"] > 8


def test_reducing_closing_speed_releases_a_brake_without_waiting_for_a_crawl():
    from pilot.avoid import Avoider

    skill = Avoider()
    outputs = []
    for i in range(15):
        distance = 14 - min(i, 8)
        h = 1200 / (distance + 6)
        box = Detection("car", (640 - h * 0.625, 360 - h, 640 + h * 0.625, 360), 0.9)
        outputs.append(skill.step([box], i * 0.1, i * 0.1, speed=14))
    assert any(a.brake for a in outputs)
    assert outputs[-1].brake == 0


def test_an_adjacent_close_car_without_the_approach_does_not_start_a_queue_stop():
    from pilot.avoid import Avoider

    skill = Avoider()
    box = Detection("car", (447, 362, 594, 476), 0.9)
    for i in range(20):
        assert skill.step([box], i * 0.1, i * 0.1, speed=5).brake == 0


def test_a_small_closing_speed_gets_a_partial_brake_and_keeps_the_push():
    from pilot.avoid import Avoider

    skill = Avoider()
    for i in range(8):
        h = 1200 / (17 - i * 0.8)
        box = Detection("car", (640 - h * 0.625, 360 - h, 640 + h * 0.625, 360), 0.9)
        result = skill.step([box], i * 0.1, i * 0.1, speed=20)
    assert 0 < result.brake < 1 and result.pedal == 0
    assert result.steer != 0


def test_a_lost_queue_box_cannot_hold_a_stop_indefinitely():
    rows = list(replay("hidden_queue"))
    assert rows[-1][1].r2 == 0
    case = json.loads(FIXTURE.read_text())["hidden_queue"]
    skill = DriveRoute({})
    for row in case["rows"]:
        detection = case["detections"][str(row["frame_id"])]
        reading = Reading("tilted", "purple", **row["reading"])
        skill._around(
            Command(0, 1, 0, "follow"),
            Observation(
                reading,
                True,
                row["now"],
                objects=tuple(Detection(**o) for o in detection["objects"]),
                objects_time=detection["t"],
            ),
        )
    now = case["rows"][-1]["now"] + 1
    pad = skill._around(Command(0, 1, 0, "follow"), Observation(reading, True, now, objects_time=now))
    assert pad.l2 == 0 and pad.r2 == 1
