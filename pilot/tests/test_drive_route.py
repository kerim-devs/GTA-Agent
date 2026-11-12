"""A drive reports measured progress and never mistakes lost guidance for arrival."""

from dataclasses import asdict, replace

import pytest

from pilot.contract import NEUTRAL_PAD, Observation, Reading
from pilot.skills import DriveRoute

GOOD = Reading("tilted", "purple", 0, 0, 0, False, 0.95)


def tick(skill, t, distance=None, *, moving=True, route="purple", sampled_at=None, corrupt=False):
    reading = replace(
        GOOD,
        route=route,
        corrupt=corrupt,
        gps_distance=distance,
        gps_time=t if sampled_at is None and distance is not None else sampled_at,
    )
    return skill.step(Observation(reading, moving, t))


def lose_route(skill, t):
    result = None
    for i in range(23):
        result = tick(skill, t + i / 10, route="none")
    return result


def test_arrival_needs_a_recent_small_falling_trend_and_serializes_distances():
    skill = DriveRoute({})
    for t, distance in ((0, 30), (0.5, 20), (1, 10), (1.5, 5)):
        assert tick(skill, t, distance).status == "running"
    result = lose_route(skill, 1.6)
    assert (result.status, result.reason, result.pad) == ("done", "arrived", NEUTRAL_PAD)
    assert asdict(result)["start_distance"] == 30
    assert result.end_distance == 5 and result.distance_age >= 2
    assert tick(skill, 10, 100) is result


@pytest.mark.parametrize(
    "distances,reason",
    [
        ([1500, 1490, 1480], "route-lost-far"),
        ([5, 5, 5], "route-lost-unknown"),
        ([3, 5, 8], "route-lost-unknown"),
    ],
)
def test_lost_route_is_not_arrival(distances, reason):
    skill = DriveRoute({})
    for i, distance in enumerate(distances):
        tick(skill, i / 2, distance)
    result = lose_route(skill, 1.1)
    assert (result.status, result.reason, result.pad) == ("failed", reason, NEUTRAL_PAD)


def test_old_distance_is_kept_with_age_but_cannot_prove_arrival():
    skill = DriveRoute({})
    for t, distance in ((0, 20), (0.5, 10), (1, 5)):
        tick(skill, t, distance)
    for i in range(2, 20):
        tick(skill, i / 2)
    result = lose_route(skill, 10)
    assert result.reason == "route-lost-unknown"
    assert result.end_distance == 5 and result.distance_age >= 11


@pytest.mark.parametrize("at,distance", [(100, 5), (-10, 5), (0, float("nan")), (0, -1)])
def test_invalid_or_stale_distance_does_not_become_evidence(at, distance):
    skill = DriveRoute({})
    tick(skill, 0, distance, sampled_at=at)
    result = lose_route(skill, 0.1)
    assert result.reason == "route-lost-unknown" and result.end_distance is None


def test_moving_away_ends_before_timeout_but_useful_progress_continues():
    away, nearer = DriveRoute({}), DriveRoute({})
    for i in range(61):
        t = i / 2
        result = tick(away, t, 1800 + t * 8)
        good = tick(nearer, t, 1800 - t * 8)
        if result.status != "running":
            break
    assert t == 20
    assert result.reason == "no-progress" and result.pad == NEUTRAL_PAD
    assert (result.start_distance, result.end_distance) == (1800, 1960)
    assert good.status == "running"


@pytest.mark.parametrize("moving", [None, True])
def test_silence_does_not_prove_no_progress(moving):
    skill = DriveRoute({})
    for i in range(81):
        t = i / 2
        result = tick(skill, t, 1800 if t in (0, 30, 40) else None, moving=moving)
    assert result.status == "running"


def test_deadline_is_not_arrival_and_interrupt_retains_distance():
    skill = DriveRoute({"duration": 2})
    tick(skill, 0, 1500)
    result = tick(skill, 2, 1480)
    # Like every other skill, a drive that runs out of time is done with its reason, so a route that
    # is still there is followed on; only "arrived" means the place was reached.
    assert (result.status, result.reason, result.pad) == ("done", "time-limit", NEUTRAL_PAD)
    assert (result.start_distance, result.end_distance) == (1500, 1480)
    other = DriveRoute({})
    tick(other, 0, 100)
    stopped = other.stop("replaced")
    assert stopped.end_distance == 100 and stopped.pad == NEUTRAL_PAD


def test_duplicate_near_fixes_cannot_invent_a_falling_trend():
    skill = DriveRoute({})
    tick(skill, 0, 15)
    for i in range(1, 10):
        tick(skill, i / 10, 5, sampled_at=0)
    assert lose_route(skill, 1).reason == "route-lost-unknown"


def test_measured_eight_second_ocr_gap_keeps_progress_window_but_does_not_end_in_the_gap():
    skill = DriveRoute({})
    for i in range(49):
        t = i / 2
        result = tick(skill, t, None if 8 <= t < 16 else 1800 + 2 * t)
        if 8 <= t < 16:
            assert result.status == "running"
        if result.status != "running":
            break
    assert result.reason == "no-progress" and t == 20


# What the HUD printed, as (capture time, metres), on the two arrivals that are on record. The route
# vanished while 27 m (a waypoint, the car at walking pace) and 23 m (a mission marker, the car at
# 13 m/s, the route gone from 39 m) were still printed.
RECORDED_ARRIVALS = {
    "20261111-131628": [
        (48.55, 65),
        (49.06, 64),
        (49.59, 62),
        (49.86, 61),
        (50.93, 53),
        (51.46, 49),
        (51.77, 46),
        (52.0, 43),
        (52.31, 41),
        (52.81, 37),
        (53.89, 32),
        (54.43, 31),
        (56.58, 30),
        (56.85, 29),
        (57.1, 28),
        (57.35, 27),
    ],
    "20261112-122056": [
        (49.38, 76),
        (50.47, 68),
        (51.26, 65),
        (51.82, 63),
        (52.13, 61),
        (52.34, 57),
        (52.66, 53),
        (52.86, 48),
        (53.18, 43),
        (53.37, 39),
        (54.23, 29),
        (54.42, 26),
        (54.66, 24),
        (54.92, 23),
    ],
}


@pytest.mark.parametrize("session", RECORDED_ARRIVALS)
def test_the_recorded_arrivals_end_as_arrived(session):
    readings = RECORDED_ARRIVALS[session]
    skill = DriveRoute({})
    for t, distance in readings:
        assert tick(skill, t, distance).status == "running"
    result = lose_route(skill, readings[-1][0] + 0.1)
    assert (result.status, result.reason) == ("done", "arrived")
    assert (result.start_distance, result.end_distance) == (readings[0][1], readings[-1][1])


def test_a_route_that_goes_while_the_place_is_still_far_is_not_an_arrival():
    skill = DriveRoute({})
    for i, distance in enumerate((140, 130, 120, 110, 100, 90)):
        tick(skill, i / 2, distance)
    result = lose_route(skill, 3)
    assert (result.status, result.reason) == ("failed", "route-lost-far")
