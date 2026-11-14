"""P106: braking follows collision evidence, including when GPS speed disappears."""

import json
from pathlib import Path

import pytest

from pilot import avoid
from pilot.contract import Command, Detection, Observation, Pad, Reading
from pilot.skills import DriveRoute

FIXTURE = json.loads((Path(__file__).parent / "fixtures/p106_approaches.json").read_text())
FORWARD = Command(0.0, 1.0, 0.0, "follow")


def observation(t, objects, speed=22, *, at=None, moving=True):
    return Observation(
        Reading("tilted", "purple", 0.0, 0.0, 0.0, False, 1.0, gps_speed=speed),
        moving,
        t,
        objects=tuple(objects),
        objects_time=t if at is None else at,
    )


def vehicle(distance, lateral=0.0):
    height = 1200 / (distance + 6)
    width = 1.25 * height
    centre = 640 + lateral * width
    return Detection("car", (centre - width / 2, 360 - height, centre + width / 2, 360), 0.9)


def replay(name, *, unknown=False):
    skill = DriveRoute({})
    for row in FIXTURE[name]["rows"]:
        objects = [Detection(**obj) for obj in row["objects"]]
        obs = observation(row["now"], objects, None if unknown else row["speed"], at=row["t"])
        yield row, skill._around(FORWARD, obs)


@pytest.mark.parametrize("name,deadline", [("queue", 272.30), ("lorry", 295.26)])
def test_the_recorded_approach_brakes_before_the_old_nearness_threshold(name, deadline):
    brakes = [(row, pad) for row, pad in replay(name) if pad.l2]
    assert brakes and brakes[0][0]["now"] <= deadline
    assert brakes[0][1].l2 == 1 and brakes[0][1].r2 == 0
    assert brakes[0][0]["now"] < FIXTURE[name]["contact"]


def test_the_recorded_lorry_still_gets_full_braking_during_the_gps_gap():
    brakes = [(r, p) for r, p in replay("lorry") if r["speed"] is None and r["now"] < 296.4]
    assert any(p.l2 == 1 and p.r2 == 0 for _, p in brakes)


def test_the_recorded_queue_grows_fast_enough_without_any_gps_speed():
    brakes = [(r, p) for r, p in replay("queue", unknown=True) if p.l2]
    assert brakes and brakes[0][0]["now"] <= 272.30


def test_width_growth_still_brakes_when_the_bonnet_hides_the_lead_cars_height():
    skill = DriveRoute({})
    pads = []
    for i in range(8):
        width = 1500 / (41 - 2 * i)
        box = Detection("car", (640 - width / 2, 340, 640 + width / 2, 358), 0.9)
        pads.append(skill._around(FORWARD, observation(i * 0.1, [box], 18)))
    assert any(p.l2 == 1 and p.r2 == 0 for p in pads[:6])


@pytest.mark.parametrize("distance,speed", [(100.0, 22.0), (250.0, 34.0)])
def test_a_known_speed_and_a_far_obstacle_use_the_stopping_distance(distance, speed):
    skill = DriveRoute({})
    start_speed = speed
    # A visible stopped car, with the planned deceleration and a 0.2 s pad delay. Boxes remain beyond FAR
    # when L2 must begin. This model checks the stopping law, not the detector's live range.
    dt = 0.05
    pending = [0.0] * 4
    first = None
    for i in range(400):
        pad = skill._around(FORWARD, observation(i * dt, [vehicle(distance)], speed))
        if pad.l2 and first is None:
            first = distance
        pending.append(pad.l2)
        applied = pending.pop(0)
        next_speed = max(0.0, speed - avoid.DECELERATION * applied * dt)
        # The runtime releases L2 near rest; passive drag completes the last two m/s.
        if pad.r2 == 0 and next_speed <= 2:
            next_speed = max(0.0, next_speed - avoid.DECELERATION * dt)
        distance -= (speed + next_speed) / 2 * dt
        speed = next_speed
        assert distance > 0
        if speed == 0:
            break
    assert first is not None and first > start_speed**2 / (2 * avoid.DECELERATION)
    assert speed == 0


def test_the_recorded_queue_does_not_prove_a_stop_at_the_planned_deceleration():
    row, _ = next((r, p) for r, p in replay("queue") if p.l2)
    available = row["speed"] * (FIXTURE["queue"]["contact"] - row["now"])
    required = row["speed"] ** 2 / (2 * avoid.DECELERATION)
    # This is an acceptance shortfall: even the ideal constant-speed approach has too little
    # room at the planned rate. Do not turn earlier L2 into a collision claim.
    assert available < required


def test_a_lead_vehicle_at_the_same_speed_is_followed_without_braking():
    skill = DriveRoute({})
    for i in range(40):
        pad = skill._around(FORWARD, observation(i * 0.05, [vehicle(35)], 22))
        assert pad.l2 == 0 and pad.left == (0, 0)


@pytest.mark.parametrize("side", [-1, 1])
def test_parked_and_oncoming_vehicles_beside_the_lane_do_not_brake(side):
    skill = DriveRoute({})
    for i in range(20):
        distance = 60 - i * 2.5
        pad = skill._around(FORWARD, observation(i * 0.05, [vehicle(distance, side * 1.6)]))
        assert pad.l2 == 0


def test_the_outer_edge_of_the_steering_corridor_is_not_a_reason_to_brake():
    skill = DriveRoute({})
    for i in range(20):
        pad = skill._around(FORWARD, observation(i * 0.05, [vehicle(40 - i, 0.55 + i * 0.004)]))
        assert pad.l2 == 0


@pytest.mark.parametrize("speed", [None, float("nan"), float("inf"), -1])
def test_growth_alone_brakes_a_fast_approach(speed):
    skill = DriveRoute({})
    pads = [skill._around(FORWARD, observation(i * 0.1, [vehicle(60 - 5 * i)], speed)) for i in range(6)]
    assert any(p.l2 == 1 and p.r2 == 0 for p in pads)


def test_a_stopped_car_releases_l2_and_waits_without_creeping():
    skill = DriveRoute({})
    for i in range(15):
        skill._around(FORWARD, observation(i * 0.1, [vehicle(20 - i)], 12))
    pad = skill._around(FORWARD, observation(1.6, [vehicle(0.8)], 0, moving=False))
    assert pad.l2 == pad.r2 == 0
    pad = skill._around(FORWARD, observation(1.7, [vehicle(0.8)], 22, moving=False))
    assert pad.l2 == 0


def test_a_close_obstacle_hidden_by_the_own_car_keeps_only_a_fresh_brake():
    skill = DriveRoute({})
    for i in range(8):
        skill._around(FORWARD, observation(i * 0.1, [vehicle(25 - i * 2)], 16))
    pad = skill._around(FORWARD, observation(0.85, [], 16))
    assert pad.l2 == 1 and pad.r2 == 0
    assert skill._around(FORWARD, observation(1.4, [], 16)).l2 == 0
    assert skill._around(FORWARD, observation(1.5, [vehicle(2)], 0, moving=False)).l2 == 0


def test_stale_or_future_boxes_do_not_authorize_braking():
    for at in (0, 2):
        skill = DriveRoute({})
        assert skill._around(FORWARD, observation(1, [vehicle(1)], 22, at=at)).l2 == 0


def test_repeated_detections_do_not_invent_growth():
    skill = DriveRoute({})
    for i in range(12):
        pad = skill._around(FORWARD, observation(i * 0.03, [vehicle(35)], None, at=0))
        assert pad.l2 == 0


@pytest.mark.parametrize("state", ["recovery-reverse", "bypass-forward", "turn-reverse", "idle"])
def test_manoeuvres_keep_their_own_pad(state):
    command = Command(0.8, 0.4, 0.2, state)
    skill = DriveRoute({})
    assert skill._around(command, observation(0, [vehicle(1)])) == Pad.from_command(command)
