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
        ("wifi-485", "foot_explore", "walk_road"),
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


def test_the_judge_outranks_the_minimap_on_how_the_figure_moves():
    base = replace(
        request("pilot-20261110-231512-01"),
        minimap={"minimap": "tilted", "route": "none", "blips": []},
        hud={"wanted": 1, "health": 1, "screen": "game"},
        objects=[{"kind": "car", "confidence": 0.9}],
    )
    # With a star the tilted map says nothing, and the rules do not guess.
    assert movement(base) == "unknown"
    on_foot = replace(base, judgment={"mode": "foot", "age": 0.2})
    assert movement(on_foot) == "on_foot"
    head = MissionHead(Fallback())
    assert [call.name for call in head.decide(on_foot).plan] == [
        "enter_vehicle",
        "set_waypoint",
        "drive_route",
    ]
    assert head.last_rule == "wanted_on_foot_vehicle"
    driving = replace(base, judgment={"mode": "vehicle", "age": 0.2})
    assert [call.name for call in head.decide(driving).plan] == ["set_waypoint", "drive_route"]
    # A judgment without an accepted mode leaves the minimap in charge.
    assert movement(replace(base, judgment={"mode": None, "age": 0.2})) == "unknown"
    watching = replace(base, judgment={"mode": "none", "age": 0.2})
    assert [call.name for call in head.decide(watching).plan] == ["wait"]


def test_closing_the_rules_closes_the_head_behind_them():
    class Closable(Fallback):
        closed = False

        def close(self):
            self.closed = True

    fallback = Closable()
    MissionHead(fallback).close()
    assert fallback.closed
    MissionHead().close()


@pytest.mark.parametrize("choice, behind", [("rules-only", type(None)), ("rules", "CodexServerHead")])
def test_the_command_line_puts_the_rules_in_front_of_the_model(monkeypatch, choice, behind):
    from pilot import cli

    class Bridge:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    calls = []
    monkeypatch.setattr(cli, "Bridge", Bridge)
    monkeypatch.setattr(cli, "Pipeline", lambda **kwargs: None)
    monkeypatch.setattr(cli, "run_play", lambda *args, **kwargs: calls.append(kwargs))
    cli.main(["play", "--head", choice, "--no-objects", "--no-record"])
    head = calls[0]["head"]
    assert isinstance(head, MissionHead)
    assert behind in (type(head.fallback), type(head.fallback).__name__)


# Objective steps P39 reconstructed from Kerim's recordings of 10 and 11 November (lab/take-out).
STEPS = json.loads((CORPUS.parent / "take-out" / "cases.json").read_text())


def step(recording, time):
    case = next(c for c in STEPS if c["recording"] == recording and abs(c["sample_t"] - time) < 0.01)
    return HeadRequest(**deepcopy(case["request"]))


VAGOS = ("20261110-093238", 48.527)


@pytest.mark.parametrize(
    "recording, time",
    [VAGOS, ("20261111-164039", 633.990), ("20261111-172549", 133.255), ("20261111-172549", 133.658)],
)
def test_on_foot_an_order_to_take_somebody_out_fights_the_red_blips(recording, time):
    fallback = Fallback()
    head = MissionHead(fallback)
    answer = head.decide(step(recording, time))
    assert head.last_rule == "take_out_fight"
    assert [(call.name, call.args) for call in answer.plan] == [("fight", {"duration": 20, "cover": "no"})]
    assert not fallback.requests


@pytest.mark.parametrize(
    "objective",
    [
        "Schalte dle Vagos aus.",
        "Schalte die V8gos aus.",
        "Schalte den Gai ti ie",
        "Schalte den GafUI",
        "Schalte den Gärtner aus.",
        "Sch8lte die Vagos aus.",
        "Scha1te die Ballas aus",
        "SCHAITE DIE VAGOS AUS",
    ],
)
def test_the_order_is_read_from_its_verb_through_misreadings(objective):
    head = MissionHead(Fallback())
    assert head.decide(replace(step(*VAGOS), objective=objective)).plan[0].name == "fight"
    assert head.last_rule == "take_out_fight"


@pytest.mark.parametrize(
    "objective",
    [
        "",
        "Begib dich zu der Autowaschanlage.",
        "Bring das Auto zum Autohaus.",
        "Sammle eine Waffe auf.",
        "Steig auf das Motorrad",
        "Schalte das Radio ein.",
        "Schalte die Scheinwerfer an",
        "Halte L1 gedrückt, um das Waffenrad aufzurufen.",
        "Folge Lamar.",
    ],
)
def test_other_objectives_with_red_on_the_map_still_go_to_the_model(objective):
    fallback = Fallback()
    value = replace(step(*VAGOS), objective=objective)
    assert MissionHead(fallback).decide(value) is fallback.answer
    assert fallback.requests == [value]


@pytest.mark.parametrize("case", STEPS, ids=lambda c: f"{c['recording']}-{c['sample_t']:.3f}")
def test_recorded_steps_without_the_order_decide_as_before(case):
    head = MissionHead()
    head.decide(HeadRequest(**deepcopy(case["request"])))
    if head.last_rule != "take_out_fight":
        assert head.last_rule == case["p39_rule"]
    else:
        assert case["request"]["objective"].startswith("Schalte")


@pytest.mark.parametrize("stars", [1, 3])
@pytest.mark.parametrize("car", [False, True])
def test_with_stars_an_order_to_take_somebody_out_is_never_fought(stars, car):
    value = replace(
        step(*VAGOS),
        hud={"wanted": stars, "health": 1, "screen": "game"},
        objects=[{"kind": "car", "confidence": 0.9}] if car else [],
    )
    head = MissionHead(Fallback())
    names = [call.name for call in head.decide(value).plan]
    assert not {"fight", "melee", "punch", "shoot"} & set(names)
    assert head.last_rule == ("wanted_on_foot_vehicle" if car else "wanted_on_foot")


def test_low_health_gets_away_before_the_order_is_fought():
    # Recorded: the first Vagos objective with a third of the health left.
    head = MissionHead(Fallback())
    assert head.decide(step("20261110-093238", 13.620)).plan[0].name == "walk"
    assert head.last_rule == "low_health_on_foot"
    unread = replace(
        step(*VAGOS), hud={"wanted": 0, "health": None, "screen": "game"}, events=[{"kind": "low_health"}]
    )
    head.decide(unread)
    assert head.last_rule == "low_health_on_foot"


def test_without_a_red_in_range_the_order_walks_to_what_the_game_marks_or_asks_the_picture():
    base = step(*VAGOS)
    head = MissionHead(Fallback())
    for color in ("yellow", "blue"):
        marked = replace(
            base, minimap={**base.minimap, "blips": [{"color": color, "x": 5.0, "y": 20.0, "border": False}]}
        )
        answer = head.decide(marked)
        assert head.last_rule == "foot_target"
        assert answer.plan[0].args["color"] == color
    border = replace(
        base, minimap={**base.minimap, "blips": [{"color": "red", "x": 0.0, "y": 60.0, "border": True}]}
    )
    nothing = replace(base, minimap={**base.minimap, "blips": []})
    for value in (border, nothing):
        fallback = Fallback()
        assert MissionHead(fallback).decide(value) is fallback.answer


def test_in_a_vehicle_the_order_leaves_the_route_rules_alone():
    base = replace(step(*VAGOS), hud=CALM)
    head = MissionHead(Fallback())
    head.decide(replace(base, minimap={**base.minimap, "minimap": "tilted", "route": "yellow"}))
    assert head.last_rule == "vehicle_route"
    head.decide(replace(base, minimap={**base.minimap, "minimap": "tilted", "route": "none"}))
    assert head.last_rule == "vehicle_waypoint"


def test_a_failed_fight_is_not_repeated_at_once():
    value = replace(
        step(*VAGOS), last_skill={"name": "fight", "status": "failed", "reason": "combat-timeout"}
    )
    head = MissionHead(Fallback())
    assert head.decide(value).plan[0].name != "fight"
    assert head.last_rule == "failed_skill"


def _on_foot_failure(name, reason):
    return replace(
        request("wifi-485"),
        last_skill={"name": name, "status": "failed", "reason": reason},
    )


def test_unmarked_foot_heads_for_a_road():
    head = MissionHead()
    answer = head.decide(request("wifi-485"))
    assert head.last_rule == "foot_explore"
    assert [call.name for call in answer.plan] == ["walk_road"]


def test_a_map_without_roads_looks_and_walks_as_before():
    head = MissionHead()
    answer = head.decide(_on_foot_failure("walk_road", "no-road"))
    assert head.last_rule == "foot_explore_roadless"
    assert [call.name for call in answer.plan] == ["look", "walk", "look", "walk"]


@pytest.mark.parametrize("name", ["walk", "walk_road"])
def test_walking_that_found_no_way_round_turns_about(name):
    head = MissionHead()
    answer = head.decide(_on_foot_failure(name, "stuck"))
    assert head.last_rule == "foot_stuck"
    assert [call.name for call in answer.plan] == ["look", "walk_road"]
    assert answer.plan[0].args["angle"] == 180


def test_a_blocked_walk_to_keeps_its_old_answer():
    head = MissionHead()
    answer = head.decide(_on_foot_failure("walk_to", "blocked"))
    assert head.last_rule == "failed_skill"
    assert [call.name for call in answer.plan] == ["walk"]
