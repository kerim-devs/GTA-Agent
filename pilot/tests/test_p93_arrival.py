"""The recorded mission approach must finish driving and retain the story."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from pilot.contract import NEUTRAL_PAD, Observation, Reading
from pilot.errands import Errand
from pilot.head import HeadRequest
from pilot.mission import MissionHead
from pilot.skills import DriveRoute


def recording():
    return json.loads((Path(__file__).parent / "fixtures" / "p93_arrival.json").read_text())


def test_recorded_drive_225_to_257_arrives_despite_the_ocr_jump():
    data = recording()
    skill = DriveRoute({})
    base = Reading("tilted", "purple", 0, 0, 0, False, 0.95)
    distances = []
    for values in data["drive_readings"]:
        row = dict(zip(data["reading_fields"], values, strict=True))
        now = row.pop("source_t") + data["clock_offset"]
        reading = replace(base, **row)
        result = skill.step(Observation(reading, True, now, mode="vehicle"))
        if reading.gps_distance is not None:
            distances.append(reading.gps_distance)
    assert 5 in distances and 49 in distances
    assert (result.status, result.reason, result.pad) == ("done", "arrived", NEUTRAL_PAD)
    assert result.end_distance == 46
    assert result.distance_age < skill.arrival_age


def test_route_end_can_use_a_reading_outside_the_driving_sampler_window():
    skill = DriveRoute({})
    reading = Reading("tilted", "purple", 0, 0, 0, False, 0.95)
    reading = replace(reading, gps_distance=46, gps_time=0)
    assert skill.step(Observation(reading, True, 2)).end_distance is None
    for i in range(23):
        result = skill.step(Observation(replace(reading, route="none"), True, 2.1 + i / 10))
    assert (result.status, result.reason, result.pad) == ("done", "arrived", NEUTRAL_PAD)
    assert result.end_distance == 46


def head_request(raw):
    fields = (
        "events",
        "help",
        "objective",
        "subtitle",
        "banner",
        "minimap",
        "last_skill",
        "hud",
        "objects",
        "judgment",
        "time",
        "place",
    )
    return HeadRequest(**{key: raw[key] for key in fields}, notebook="", jpeg_path="unused.jpg")


def story_at_recorded_approach(data):
    head = MissionHead(goal_seed=1)
    initial = data["initial_goal"]
    goal = {key: value for key, value in initial["goal"].items() if key != "deadline"}
    head.goals.active = Errand(
        **goal,
        step=initial["step"],
        seen_route=True,
        waypoint_set=True,
        target={"place": goal["place"], "instance": 0},
    )
    return head


@pytest.mark.parametrize("arrived", [False, True])
def test_recorded_head_keeps_story_exits_walks_and_waits(arrived):
    data = recording()
    head = story_at_recorded_approach(data)
    goal = head.goals.active
    responses = [head.decide(head_request(data["seed_request"]))]
    for raw in data["head_requests"]:
        request = head_request(raw)
        if arrived:
            request = replace(
                request,
                last_skill={**request.last_skill, "status": "done", "reason": "arrived"},
                events=[event for event in request.events if event["kind"] != "skill_failed"],
            )
        responses.append(head.decide(request))
        assert head.goals.active is goal
        assert responses[-1].goal["name"] == "story"
        assert responses[-1].step == "exit"
        assert [call.name for call in responses[-1].plan] == ["press", "wait"]
        assert responses[-1].plan[0].args["button"] == "triangle"
    foot = replace(
        request,
        time=request.time + 3,
        events=[{"kind": "vehicle_exit"}],
        judgment={"mode": "foot"},
        minimap={**request.minimap, "minimap": "flat"},
        last_skill={"name": "wait", "status": "done", "reason": "time-limit", "queue": []},
    )
    walk = head.decide(foot)
    responses.append(walk)
    assert walk.step == "approach"
    assert [call.name for call in walk.plan] == ["walk_to_point"]
    assert walk.plan[0].args["exact"] is True
    waiting = replace(
        foot,
        time=foot.time + 5,
        events=[],
        last_skill={"name": "walk_to_point", "status": "done", "reason": "arrived", "queue": []},
    )
    response = head.decide(waiting)
    responses.append(response)
    assert response.step == "await_story" and head.goals.active is goal
    assert [call.name for call in response.plan] == ["wait"]
    assert not head.goals.history
    assert all(response.goal["name"] == "story" for response in responses)
    assert all(call.name != "set_waypoint" for response in responses for call in response.plan)
    head.decide(replace(waiting, time=waiting.time + 21))
    assert head.goals.history[-1]["reason"].endswith("letter did not start a mission")


def test_recorded_route_loss_far_away_keeps_the_existing_waypoint_retry():
    data = recording()
    head = story_at_recorded_approach(data)
    head.decide(head_request(data["seed_request"]))
    request = head_request(data["head_requests"][0])
    request = replace(
        request,
        minimap={**request.minimap, "gps_distance": 1480},
        last_skill={**request.last_skill, "reason": "route-lost-far"},
    )
    response = head.decide(request)
    assert response.goal["name"] == "story" and response.step == "waypoint"
    assert [call.name for call in response.plan] == ["set_waypoint"]
    assert head.goals.active.stalls == 1


def test_head_can_use_the_drives_near_distance_when_the_reading_is_missing():
    data = recording()
    head = story_at_recorded_approach(data)
    request = head_request(data["head_requests"][0])
    response = head.decide(
        replace(
            request,
            minimap={**request.minimap, "gps_distance": None, "gps_time": None},
            last_skill={**request.last_skill, "end_distance": 46, "distance_age": 1},
        )
    )
    assert response.goal["name"] == "story" and response.step == "exit"
    assert [call.name for call in response.plan] == ["press", "wait"]


@pytest.mark.parametrize("distance,age", [(46, 6), (46, -1), (-1, 1), (float("nan"), 1)])
def test_invalid_or_old_head_reading_does_not_preserve_a_failed_drive(distance, age):
    data = recording()
    head = story_at_recorded_approach(data)
    goal = head.goals.active
    request = head_request(data["head_requests"][0])
    response = head.decide(
        replace(
            request,
            minimap={**request.minimap, "gps_distance": distance, "gps_time": request.time - age},
        )
    )
    assert head.goals.active is not goal
    assert response.step != "exit"
