"""Recorded observations plus explicitly counterfactual safety-boundary probes."""

import json
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path
from time import perf_counter_ns

import pytest

from pilot.head import HeadRequest, parse_response
from pilot.mission import MissionHead, movement

CORPUS = Path(__file__).resolve().parents[2] / "lab" / "mission"
CASES = {
    case["id"]: case
    for name in ("saved_cases.json", "frame_cases.json", "extra_cases.json")
    for case in json.loads((CORPUS / name).read_text())
}


def request(case_id):
    return HeadRequest(**deepcopy(CASES[case_id]["request"]))


class Fallback:
    def __init__(self):
        self.requests = []
        self.answer = parse_response(
            {
                "plan": [{"name": "look", "args": {"angle": 25, "duration": 0.5}}],
                "sentence": "Ich schaue mich um.",
                "lesson": "Unklare Lage.",
            }
        )

    def decide(self, value):
        self.requests.append(value)
        return self.answer


@pytest.mark.parametrize("case_id", CASES)
def test_recorded_plans_parse_and_do_not_mutate_request(case_id):
    value = request(case_id)
    before = deepcopy(asdict(value))
    head = MissionHead()
    answer = head.decide(value)
    assert parse_response(json.dumps(asdict(answer))) == answer
    assert asdict(value) == before
    assert sum(head.counts.values()) == 1


def test_unknown_reaches_fallback_by_identity_and_returns_exact_answer():
    value = replace(request("pilot-20261110-231512-01"), minimap={"minimap": "none"})
    fallback = Fallback()
    head = MissionHead(fallback)
    assert head.decide(value) is fallback.answer
    assert fallback.requests == [value]
    assert fallback.requests[0] is value
    assert head.counts == {"fallback": 1}


@pytest.mark.parametrize(
    "case_id, rule, first_call",
    [
        ("wifi-25", "low_health_on_foot", "walk"),
        ("wifi-5.2415", "foot_target", "walk_to"),
        ("wifi-41.5", "screen_wait", "wait"),
        ("wifi-160", "vehicle_waypoint", "set_waypoint"),
        ("wifi-230", "vehicle_route", "drive_route"),
        ("wifi-245", "low_health_vehicle", "set_waypoint"),
        ("wifi-485", "foot_explore", "look"),
        ("wifi-536.761", "wanted_on_foot", "walk"),
        ("wifi-33.7221", "screen_reflex", "wait"),
        ("objects-071", "wanted_on_foot_vehicle", "enter_vehicle"),
    ],
)
def test_observed_rule_decisions(case_id, rule, first_call):
    head = MissionHead(Fallback())
    answer = head.decide(request(case_id))
    assert head.last_rule == rule
    assert answer.plan[0].name == first_call


@pytest.mark.parametrize("case_id", ["wifi-20", "wifi-45", "wifi-540", "wifi-590.005"])
def test_real_ambiguous_combat_and_wanted_frames_delegate(case_id):
    fallback = Fallback()
    head = MissionHead(fallback)
    value = request(case_id)
    assert head.decide(value) is fallback.answer
    assert fallback.requests[0] is value


@pytest.mark.parametrize(
    "case_id", ["wifi-15", "wifi-33.7221", "wifi-340", "wifi-385", "wifi-390", "wifi-628.8"]
)
def test_recorded_blocking_screens_only_hold(case_id):
    answer = MissionHead().decide(request(case_id))
    assert [call.name for call in answer.plan] == ["wait"]


def test_screen_hold_does_not_move_after_a_failed_wait():
    value = replace(request("wifi-33.7221"), last_skill={"name": "wait", "status": "failed"})
    assert [call.name for call in MissionHead().decide(value).plan] == ["wait"]


def test_vehicle_escape_with_future_judge_evidence(monkeypatch):
    # This is an explicit seam probe, not a claim that today's map proves it.
    import pilot.mission

    monkeypatch.setattr(pilot.mission, "movement", lambda request: "vehicle")
    answer = MissionHead().decide(request("wifi-540"))
    assert [call.name for call in answer.plan] == ["set_waypoint", "drive_route"]
    assert answer.plan[0].args["target"] == "away"
    assert parse_response(json.dumps(asdict(answer))) == answer


@pytest.mark.parametrize("stars", [1, 2, 5])
@pytest.mark.parametrize("shape", ["flat", "tilted", "none"])
@pytest.mark.parametrize("car", [False, True])
def test_wanted_never_fights_or_enters_without_observed_foot(stars, shape, car):
    # Deliberate counterfactuals isolate the dangerous toggle boundary.
    value = replace(
        request("pilot-20261110-231512-01"),
        minimap={"minimap": shape, "route": "yellow", "blips": [{"color": "red"}]},
        hud={"wanted": stars, "health": 1, "screen": "game"},
        objects=[{"kind": "car", "confidence": 0.9}] if car else [],
    )
    fallback = Fallback()
    head = MissionHead(fallback)
    answer = head.decide(value)
    names = [call.name for call in answer.plan]
    assert not {"fight", "melee", "punch", "shoot"} & set(names)
    assert "enter_vehicle" not in names or movement(value) == "on_foot"
    assert bool(fallback.requests) == (shape != "flat")
    assert parse_response(json.dumps(asdict(answer))) == answer


@pytest.mark.parametrize("failed", ["walk", "look", "wait", "drive_route", "set_waypoint", "enter_vehicle"])
@pytest.mark.parametrize("shape", ["flat", "tilted", "none"])
def test_failure_changes_action_before_retry(failed, shape):
    value = replace(
        request("pilot-20261110-231512-01"),
        minimap={"minimap": shape, "route": "none"},
        hud={"wanted": 0},
        last_skill={"name": failed, "status": "failed", "reason": "stuck"},
    )
    head = MissionHead()
    answer = head.decide(value)
    assert answer.plan[0].name != failed
    assert parse_response(json.dumps(asdict(answer))) == answer
    if shape == "tilted":
        assert "walk" not in {call.name for call in answer.plan}


@pytest.mark.parametrize("event", ["failure", "pass", "menu_closed", "screen_cleared"])
def test_after_reflex_replans_from_current_request(event):
    # Events are counterfactual overlays on recorded pixels, not recorded calls.
    value = replace(request("pilot-20261110-231512-01"), events=[{"kind": event}])
    head = MissionHead()
    head.decide(value)
    assert head.last_rule == "restart_on_foot"
    head.decide(
        replace(value, events=[], minimap={"minimap": "tilted", "route": "yellow"}, hud={"wanted": 0})
    )
    assert head.last_rule == "vehicle_route"


def test_corrupt_or_unreadable_map_cannot_authorize_vehicle():
    value = request("pilot-20261110-231512-01")
    assert movement(replace(value, minimap={"minimap": "tilted"}, hud={"wanted": None})) == "unknown"
    assert movement(replace(value, minimap={"minimap": "flat", "corrupt": True})) == "unknown"


def test_rule_path_is_within_a_few_milliseconds():
    value = request("pilot-20261110-231512-01")
    head = MissionHead()
    elapsed = []
    for _ in range(300):
        start = perf_counter_ns()
        head.decide(value)
        elapsed.append((perf_counter_ns() - start) / 1e6)
    assert sorted(elapsed)[int(len(elapsed) * 0.95)] < 5


# The review's rules, as counterfactual overlays on a recorded request: no recording has them yet.
DRIVING = {"minimap": "tilted", "route": "none"}
CALM = {"wanted": 0, "health": 1, "screen": "game"}


def test_on_foot_with_nothing_to_do_and_a_car_in_view_it_goes_for_a_drive_to_a_mission():
    value = replace(
        request("pilot-20261110-231512-01"),
        objective="",
        minimap={"minimap": "flat", "route": "none", "blips": []},
        hud=CALM,
        objects=[{"kind": "car", "confidence": 0.9}],
    )
    head = MissionHead(Fallback())
    answer = head.decide(value)
    assert head.last_rule == "foot_drive"
    assert [call.name for call in answer.plan] == ["enter_vehicle", "set_waypoint", "drive_route"]
    assert answer.plan[1].args["target"] == "mission"


def test_a_map_without_a_mission_letter_is_not_asked_again_at_once():
    base = replace(request("pilot-20261110-231512-01"), minimap=DRIVING, hud=CALM, objects=[])
    head = MissionHead()
    assert head.decide(base).plan[0].args["target"] == "mission"
    failed = replace(base, last_skill={"name": "set_waypoint", "status": "failed", "reason": "no letter"})
    answer = head.decide(failed)
    assert [call.name for call in answer.plan] == ["look", "set_waypoint", "drive_route"]
    assert answer.plan[1].args["target"] == "away"
    targets = [head.decide(base).plan[0].args["target"] for _ in range(MissionHead.LETTERLESS_ROUTES)]
    assert targets == ["away"] * (MissionHead.LETTERLESS_ROUTES - 1) + ["mission"]


def test_where_a_route_ended_the_picture_decides_and_not_a_new_waypoint():
    value = replace(
        request("pilot-20261110-231512-01"),
        minimap=DRIVING,
        hud=CALM,
        last_skill={"name": "drive_route", "status": "done", "reason": "route-gone"},
    )
    fallback = Fallback()
    assert MissionHead(fallback).decide(value) is fallback.answer


def test_with_stars_a_waypoint_that_is_up_is_driven_and_the_map_stays_shut(monkeypatch):
    import pilot.mission

    monkeypatch.setattr(pilot.mission, "movement", lambda request: "vehicle")
    value = replace(
        request("pilot-20261110-231512-01"),
        minimap={"minimap": "tilted", "route": "purple"},
        hud={"wanted": 2, "health": 1, "screen": "game"},
    )
    assert [call.name for call in MissionHead().decide(value).plan] == ["drive_route"]
