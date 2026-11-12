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


def test_deadline_is_not_success_and_interrupt_retains_distance():
    skill = DriveRoute({"duration": 2})
    tick(skill, 0, 1500)
    result = tick(skill, 2, 1480)
    assert (result.status, result.reason, result.pad) == ("failed", "time-limit", NEUTRAL_PAD)
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
