"""Closed goal round and real conductor/runner ownership with scripted skill mechanics."""

import json
from concurrent.futures import Future
from dataclasses import replace

import numpy as np
import pytest

from pilot.conductor import Conductor
from pilot.contract import Hud, Pad, Reading, SkillResult
from pilot.goals import LIMITS
from pilot.head import HeadRequest, SkillCall, parse_response, response_data
from pilot.mission import MissionHead
from pilot.skills import Observation, SkillRunner


def request(t=0, *, mode="foot", wanted=0, last=None, last_skill=None, cars=False, people=False, **kwargs):
    last = last if last is not None else last_skill
    return HeadRequest(
        [],
        "",
        "",
        "",
        "",
        {"minimap": "flat" if mode == "foot" else "tilted", "route": "none", "blips": []},
        last,
        "",
        "unused.jpg",
        time=t,
        hud={"screen": "game", "health": 1, "wanted": wanted},
        judgment={"mode": mode},
        objects=([{"kind": "car"}] if cars else []) + ([{"kind": "person"}] if people else []),
        **kwargs,
    )


def done(name, reason):
    return {
        "name": name,
        "status": "done",
        "reason": reason,
        "queue": [],
        **({"route_seen": True} if name == "drive_route" else {}),
    }


def test_closed_round_uses_observed_entry_arrival_punch_and_wanted_clear():
    head = MissionHead(goal_seed=17)
    vehicle = head.decide(request(cars=True))
    drive = head.decide(request(2, mode="vehicle", last=done("enter_vehicle", "entered vehicle")))
    fight = head.decide(request(20, mode="vehicle", last=done("drive_route", "route-gone")))
    assert [r.goal["name"] for r in (vehicle, drive, fight)] == ["vehicle", "drive", "fight"]
    assert drive.plan[0].args["distance"] == "far"
    assert fight.plan[0].args["button"] == "triangle"
    punch = head.decide(request(24, people=True, last=done("wait", "time-limit")))
    assert punch.plan[0].name == "punch"
    escape = head.decide(request(30, people=True, last=done("punch", "delivered 3 punch pulses in reach")))
    assert escape.goal["name"] == "escape"
    sought = head.decide(request(31, wanted=2, last={"name": "walk", "status": "running", "queue": []}))
    assert sought.goal["name"] == "escape"
    again = head.decide(request(40, cars=True, wanted=0, last=done("walk", "time-limit")))
    assert again.goal["name"] == "vehicle"
    assert [h["name"] for h in head.goals.history if h["outcome"] == "reached"] == [
        "vehicle",
        "drive",
        "fight",
        "escape",
    ]


def test_road_observation_and_car_sighting_advance_without_restarting_on_noise():
    head = MissionHead(goal_seed=7)
    first = head.decide(request())
    assert first.goal["name"] == "road"
    current = {"name": "walk_road", "status": "running", "queue": ["look"]}
    for t, kind in enumerate(("subtitle", "help", "route_changed", "quiet", "plan_ending"), 1):
        kept = head.decide(replace(request(t, last=current), events=[{"kind": kind}]))
        assert kept.action == "go_on" and kept.plan == ()
        assert kept.goal == first.goal
        assert kept.step and "running" in kept.reason
    road = head.decide(request(7, last={**current, "road_reached": True}))
    assert road.goal["name"] == "vehicle"
    assert "road observed" in road.reason
    # A visible car becomes the next attempt after the road-seeking step ends.
    car = head.decide(request(8, cars=True, last=done("walk_road", "time-limit")))
    assert car.plan[0].name == "enter_vehicle"


# The card's limits, written out: seconds and tries per goal.
SECONDS = {"vehicle": 90, "drive": 240, "fight": 90, "escape": 180, "road": 90}
TRIES = {"vehicle": 3, "drive": 3, "fight": 4, "escape": 4, "road": 4}
# Each goal's first step in its own situation, and the skill whose failure the goal answers.
SETUP = {
    "vehicle": ({"cars": True}, "enter_vehicle"),
    "drive": ({"mode": "vehicle"}, "set_waypoint"),
    "fight": ({"people": True}, "punch"),
    "escape": ({"wanted": 1}, "walk"),
    "road": ({}, "walk_road"),
}


def test_the_limits_are_those_of_the_card():
    assert {name: seconds for name, (seconds, _) in LIMITS.items()} == SECONDS
    assert {name: tries for name, (_, tries) in LIMITS.items()} == TRIES


@pytest.mark.parametrize("name", SECONDS)
def test_each_goal_gives_up_at_its_deadline_and_is_not_reselected(name):
    head = MissionHead(goal_seed=12)
    head.goals.next = name
    situation, _ = SETUP[name]
    initial = request(**situation)
    first = head.decide(initial)
    assert first.goal["name"] == name
    assert first.goal["deadline"] - first.goal["started"] == SECONDS[name]
    just_before = head.decide(replace(initial, time=SECONDS[name] - 0.5, last_skill=running(name)))
    assert just_before.goal["name"] == name
    expired = replace(initial, time=SECONDS[name], hud={"screen": "game", "health": 1, "wanted": 0})
    after = head.decide(expired)
    assert after.goal["name"] != name
    assert any(
        h["name"] == name and h["outcome"] == "gave_up" and h["reason"] == "limit" for h in head.goals.history
    )


def running(name):
    return {"name": SETUP[name][1], "status": "running", "queue": []}


@pytest.mark.parametrize("name", TRIES)
def test_each_goal_is_tried_as_often_as_the_card_says_and_no_more(name):
    head = MissionHead(goal_seed=12)
    head.goals.next = name
    situation, skill = SETUP[name]
    issued = [head.decide(request(**situation))]
    for t in range(1, 8):
        failed = {"name": skill, "status": "failed", "reason": f"try {t}", "queue": []}
        answer = head.decide(request(t, last=failed, **situation))
        if answer.goal is None or answer.goal["name"] != name:
            break
        issued.append(answer)
    assert len(issued) == TRIES[name]
    assert [a.goal["attempts"] for a in issued] == list(range(1, TRIES[name] + 1))
    assert any(h["name"] == name and h["outcome"] == "gave_up" for h in head.goals.history)


def test_failed_attempt_budget_and_seeded_choices_are_reproducible():
    def run(seed):
        head = MissionHead(goal_seed=seed)
        outputs = [response_data(head.decide(request(mode="vehicle")))]
        for t in range(1, 5):
            failed = {"name": "set_waypoint", "status": "failed", "reason": f"missing cursor {t}"}
            outputs.append(response_data(head.decide(request(t, mode="vehicle", last=failed))))
        return outputs, head.goals.history

    assert run(3) == run(3)
    assert run(3)[0][0]["goal"]["direction"] != run(5)[0][0]["goal"]["direction"]
    assert any(h["outcome"] == "gave_up" for h in run(3)[1])


def test_fresh_head_does_not_claim_an_old_drive_result_as_its_arrival():
    answer = MissionHead(goal_seed=1).decide(request(mode="vehicle", last=done("drive_route", "route-gone")))
    assert answer.goal["name"] == "drive"


@pytest.mark.parametrize(
    "change",
    [
        {"hud": {"screen": "game", "wanted": 1}},
        {"hud": {"screen": "game", "health": 0.32}},
        {"hud": {"screen": "wasted"}},
        {"objective": "Folge Lamar."},
    ],
)
def test_head_ends_goal_for_priority_observation(change):
    head = MissionHead(goal_seed=1)
    head.decide(request(cars=True))
    answer = head.decide(replace(request(2, cars=True), **change))
    assert head.goals.history[1]["outcome"] == "gave_up"
    assert answer.action == "replace"
    if "objective" in change:
        assert answer.goal is None


def test_go_on_contract_rejects_hidden_calls_and_empty_replacements():
    reply = {"plan": [], "sentence": "Ich bleibe dabei.", "action": "go_on"}
    assert parse_response(response_data(parse_response(reply))).action == "go_on"
    with pytest.raises(ValueError):
        parse_response({**reply, "plan": [{"name": "wait", "args": {}}]})
    with pytest.raises(ValueError):
        parse_response({**reply, "action": "replace"})


class NoEvents:
    def update(self, *args, **kwargs):
        return ()


class HeldSkill:
    def __init__(self, name):
        self.name = name
        self.limit = 120
        self.stops = []

    def step(self, observation):
        return SkillResult(Pad(left=(0, -0.5)))

    def stop(self, reason):
        self.stops.append(reason)
        return SkillResult(status="failed", reason=reason)


def immediate(function, *args):
    future = Future()
    future.set_result(function(*args))
    return future


def setup_conductor(tmp_path, monkeypatch, *, submit=immediate, head=None, opening=()):
    monkeypatch.setattr("pilot.skills.make_skill", lambda call, **kwargs: HeldSkill(call.name))
    runner = SkillRunner()
    conductor = Conductor(
        tmp_path / "session",
        notebook=tmp_path / "notes",
        runner=runner,
        head=MissionHead(goal_seed=7) if head is None else head,
        opening=opening,
        detector=NoEvents(),
        submit=submit,
    )
    reading = Reading("flat", "none", 0, 0, 0, False, 1)
    obs = Observation(reading, True, 0, hud=Hud(screen="game", wanted=0, health=1))
    rgb = np.zeros((720, 1280, 3), dtype=np.uint8)
    return conductor, runner, obs, rgb


def test_conductor_go_on_preserves_active_identity_queue_and_controller_input(tmp_path, monkeypatch):
    conductor, runner, obs, rgb = setup_conductor(tmp_path, monkeypatch)
    try:
        for t in (0, 0.1, 0.2):
            conductor._tick(replace(obs, time=t), rgb)
        runner.append((SkillCall("look", {"duration": 1}),))
        active, queued = runner.active, tuple(runner.queue)
        # What the sessions of 12 November brought while a plan ran, none of it a reason to change it.
        for i, kind in enumerate(
            (
                "route_appeared",
                "route_vanished",
                "help_changed",
                "menu_closed",
                "mode_changed",
                "plan_ending",
            ),
            1,
        ):
            t = i * 0.4
            conductor._tick(replace(obs, time=t), rgb, events=[{"kind": kind}])
            result = conductor._tick(replace(obs, time=t + 0.1), rgb)
            assert runner.active is active and tuple(runner.queue) == queued
            assert not active.stops
            assert result.pad.left == (0, -0.5)
        rows = [json.loads(line) for line in (tmp_path / "session/head.jsonl").read_text().splitlines()]
        kept = [r for r in rows if r.get("disposition") == "kept"]
        assert len(kept) == 6
        assert all(r["goal"]["name"] == "road" and r["step"] and r["reason"] for r in kept)
    finally:
        conductor.close()


@pytest.mark.parametrize("reason", ["stars", "low_health", "death_or_arrest", "objective", "limit"])
def test_conductor_interrupts_goal_before_next_skill_tick(tmp_path, monkeypatch, reason):
    from pilot.scene import SceneText

    conductor, runner, obs, rgb = setup_conductor(tmp_path, monkeypatch)
    try:
        for t in (0, 0.1, 0.2):
            conductor._tick(replace(obs, time=t), rgb)
        active = runner.active
        runner.append((SkillCall("look", {}),))
        hud = {
            "stars": Hud(screen="game", wanted=1, health=1),
            "low_health": Hud(screen="game", wanted=0, health=0.2),
            "death_or_arrest": Hud(screen="wasted", wanted=0, health=1),
        }.get(reason, obs.hud)
        t = conductor.goal["deadline"] if reason == "limit" else 1
        kwargs = {"text": SceneText(objective="Folge Lamar.")} if reason == "objective" else {}
        conductor._tick(replace(obs, time=t, hud=hud), rgb, **kwargs)
        assert active.stops == ["goal_" + reason]
        assert runner.active is None and not runner.queue
        rows = [json.loads(line) for line in (tmp_path / "session/head.jsonl").read_text().splitlines()]
        assert any(r.get("type") == "goal_end" and r["reason"] == reason for r in rows)
    finally:
        conductor.close()


def test_stale_go_on_is_discarded_after_goal_interruption(tmp_path, monkeypatch):
    pending = []

    def submit(fn, *args):
        future = Future()
        pending.append((future, fn, args))
        return future

    conductor, runner, obs, rgb = setup_conductor(tmp_path, monkeypatch, submit=submit)
    try:
        conductor._tick(obs, rgb)
        future, fn, args = pending.pop(0)
        future.set_result(fn(*args))
        conductor._tick(replace(obs, time=0.1), rgb)
        conductor._tick(replace(obs, time=0.2), rgb)
        conductor._tick(replace(obs, time=0.3), rgb, events=[{"kind": "subtitle_changed"}])
        future, fn, args = pending.pop(0)
        response = fn(*args)
        assert response.action == "go_on"
        conductor._tick(replace(obs, time=0.4, hud=Hud(screen="game", wanted=0, health=0.2)), rgb)
        future.set_result(response)
        conductor._tick(replace(obs, time=0.5, hud=Hud(screen="game", wanted=0, health=0.2)), rgb)
        rows = [json.loads(line) for line in (tmp_path / "session/head.jsonl").read_text().splitlines()]
        assert any(r.get("action") == "go_on" and r["overtaken"] and not r["applied"] for r in rows)
        assert runner.active is None and not runner.queue
    finally:
        conductor.close()


def test_route_loss_without_an_observed_route_is_not_an_arrival():
    head = MissionHead(goal_seed=1)
    first = head.decide(request(mode="vehicle"))
    missing = {"name": "drive_route", "status": "done", "reason": "route-gone", "queue": []}
    second = head.decide(request(4, mode="vehicle", last=missing))
    assert first.goal["name"] == second.goal["name"] == "drive"
    assert not any(h["outcome"] == "reached" for h in head.goals.history)


def test_expired_escape_keeps_police_rules_without_immediately_restarting_goal():
    head = MissionHead(goal_seed=1)
    first = head.decide(request(wanted=1))
    after = head.decide(request(first.goal["deadline"], wanted=1))
    assert after.goal is None
    assert head.goals.active is None
    assert after.plan[0].args["sprint"] is True
    assert "limit" in after.reason


def test_runner_reports_road_reach_on_completion_and_resets_for_next_skill(monkeypatch):
    class RoadSkill(HeldSkill):
        ON_ROAD_SECONDS = 0.3
        on_road_since = 0

        def step(self, observation):
            return SkillResult(status="done" if observation.time >= 0.4 else "running")

    monkeypatch.setattr("pilot.skills.make_skill", lambda call, **kwargs: RoadSkill(call.name))
    runner = SkillRunner()
    runner.replace((SkillCall("walk_road", {}),))
    obs = Observation(Reading("flat", "none", 0, 0, 0, False, 1), True, 0)
    runner.tick(obs)
    runner.tick(replace(obs, time=0.1))
    assert runner.describe()["road_reached"] is False
    runner.tick(replace(obs, time=0.4))
    assert runner.describe()["road_reached"] is True
    runner.replace((SkillCall("look", {}),))
    runner.tick(replace(obs, time=0.5))
    runner.tick(replace(obs, time=0.6))
    assert "road_reached" not in runner.describe()


def test_goals_own_map_is_kept_until_waypoint_skill_closes_it():
    head = MissionHead(goal_seed=1)
    first = head.decide(request(mode="vehicle"))
    on_map = replace(
        request(2, mode="none", last={"name": "set_waypoint", "status": "running", "queue": ["drive_route"]}),
        hud={"screen": "map", "health": 1, "wanted": 0},
    )
    kept = head.decide(on_map)
    assert kept.action == "go_on" and kept.goal == first.goal


def test_go_on_arriving_after_completion_requests_next_step_without_quiet_delay(tmp_path, monkeypatch):
    pending = []

    def submit(fn, *args):
        future = Future()
        pending.append((future, fn, args))
        return future

    conductor, runner, obs, rgb = setup_conductor(tmp_path, monkeypatch, submit=submit)
    try:
        conductor._tick(obs, rgb)
        future, fn, args = pending.pop(0)
        future.set_result(fn(*args))
        conductor._tick(replace(obs, time=0.1), rgb)
        conductor._tick(replace(obs, time=0.2), rgb)
        conductor._tick(replace(obs, time=0.3), rgb, events=[{"kind": "subtitle_changed"}])
        future, fn, args = pending.pop(0)
        response = fn(*args)
        assert response.action == "go_on"
        # Natural completion while the response is in flight does not increment the epoch.
        runner.active.step = lambda observation: SkillResult(status="done", reason="time-limit")
        conductor._tick(replace(obs, time=0.4), rgb)
        assert not runner.has_plan
        future.set_result(response)
        conductor._tick(replace(obs, time=0.5), rgb)
        assert pending and conductor.request_count == 3
        assert pending[0][2][0].events == [{"kind": "plan_finished"}]
    finally:
        conductor.close()


def test_unreadable_wanted_is_not_successful_escape():
    head = MissionHead(goal_seed=1)
    head.decide(request(wanted=2))
    after = head.decide(request(4, wanted=None, last={"name": "walk", "status": "running", "queue": []}))
    assert after.goal["name"] == "escape" and after.action == "go_on"
    assert not any(h["outcome"] == "reached" for h in head.goals.history)


@pytest.mark.parametrize("screen", ["wasted", "busted"])
def test_screen_event_ends_goal_without_a_hud_reading(screen):
    head = MissionHead(goal_seed=1)
    head.decide(request(cars=True))
    head.decide(replace(request(1), hud=None, events=[{"kind": "screen", "screen": screen}]))
    assert head.goals.active is None
    assert head.goals.history[-1]["reason"] == "death_or_arrest"


def test_expected_entry_mode_change_keeps_skill_until_it_confirms_entry():
    head = MissionHead(goal_seed=7)
    first = head.decide(request(cars=True))
    entering = request(2, mode="vehicle", last={"name": "enter_vehicle", "status": "running", "queue": []})
    kept = head.decide(replace(entering, events=[{"kind": "mode_changed", "old": "foot", "new": "vehicle"}]))
    assert kept.action == "go_on" and kept.goal == first.goal
    confirmed = head.decide(request(3, mode="vehicle", last=done("enter_vehicle", "entered vehicle")))
    assert confirmed.goal["name"] == "drive"


def test_unreadable_mode_does_not_replace_a_running_goal():
    head = MissionHead(goal_seed=1)
    first = head.decide(request(cars=True))
    unreadable = replace(
        request(1, last={"name": "enter_vehicle", "status": "running", "queue": []}),
        judgment=None,
        minimap={"minimap": "none", "corrupt": True},
    )
    kept = head.decide(unreadable)
    assert kept.action == "go_on" and kept.goal == first.goal


# D1: a stop the conductor made for the goal is no failure of the skill.


@pytest.mark.parametrize("reason", ["goal_limit", "goal_stars", "goal_objective"])
def test_a_stop_made_for_the_goal_is_not_met_as_a_failure(reason):
    head = MissionHead(goal_seed=5)
    first = head.decide(request())
    stopped = {"name": "walk_road", "status": "failed", "reason": reason, "queue": []}
    after = head.decide(request(first.goal["deadline"] + 0.1, last_skill=stopped))
    assert after.goal is not None and after.goal["name"] != "road"
    assert after.reason != "retry: observed skill failure"
    assert head.last_rule.startswith("goal_")
    # The same words from a skill that stopped by itself are a failure and are answered as one.
    own = {**stopped, "reason": "stuck"}
    head = MissionHead(goal_seed=5)
    head.decide(request())
    assert head.decide(request(5, last_skill=own)).reason == "retry: observed skill failure"


def test_the_stop_at_the_deadline_leads_to_the_next_goal_and_not_to_a_failure_step(tmp_path, monkeypatch):
    conductor, _runner, obs, rgb = setup_conductor(tmp_path, monkeypatch)
    try:
        for t in (0, 0.1, 0.2):
            conductor._tick(replace(obs, time=t), rgb)
        deadline = conductor.goal["deadline"]
        for t in (deadline, deadline + 0.1, deadline + 0.2, deadline + 0.3):
            conductor._tick(replace(obs, time=t), rgb)
        rows = [json.loads(line) for line in (tmp_path / "session/head.jsonl").read_text().splitlines()]
        stopped = [r for r in rows if r.get("type") == "request" and r["request"]["last_skill"]]
        assert stopped[0]["request"]["last_skill"]["reason"] == "goal_limit"
        answer = [r for r in rows if r.get("type") == "response"][-1]
        assert answer["goal"] is not None and answer["goal"]["name"] == "vehicle"
        assert answer["reason"] != "retry: observed skill failure"
        assert "failed_skill" not in conductor.head.counts
    finally:
        conductor.close()


# D2: go_on only while the running skill fits what the figure is doing.


@pytest.mark.parametrize(
    "skill,seat,fits_it",
    [
        ("drive_route", "vehicle", True),
        ("drive_route", "on_foot", False),
        ("drive_route", "unknown", True),
        ("walk", "on_foot", True),
        ("walk", "vehicle", False),
        ("walk_road", "vehicle", False),
        ("walk_to", "vehicle", False),
        ("punch", "vehicle", False),
        ("punch", "on_foot", True),
        ("walk_road", "none", True),
        # the entry crosses from one to the other, and these do the same in both
        ("enter_vehicle", "vehicle", True),
        ("enter_vehicle", "on_foot", True),
        ("set_waypoint", "vehicle", True),
        ("set_waypoint", "on_foot", True),
        ("look", "vehicle", True),
        ("wait", "on_foot", True),
        ("press", "vehicle", True),
    ],
)
def test_which_skills_fit_which_way_of_moving(skill, seat, fits_it):
    from pilot.goals import fits

    assert fits(skill, seat) is fits_it


def drive_head():
    head = MissionHead(goal_seed=3)
    first = head.decide(request(mode="vehicle"))
    assert first.goal["name"] == "drive"
    return head, first


DRIVING_ON = {"name": "drive_route", "status": "running", "queue": []}


def test_a_drive_goal_does_not_go_on_with_the_figure_on_foot():
    head, _first = drive_head()
    seated = head.decide(request(5, mode="vehicle", last_skill=DRIVING_ON))
    assert seated.action == "go_on"
    afoot = head.decide(request(10, mode="foot", last_skill=DRIVING_ON))
    assert afoot.action == "replace" and afoot.goal["name"] == "drive"
    assert afoot.plan[0].name in {"enter_vehicle", "walk_road"}
    assert "drive_route does not fit" in afoot.reason


def test_a_vehicle_exit_event_ends_the_drive_step_before_the_judge_has_changed_its_word():
    head, _ = drive_head()
    exit_event = [{"kind": "vehicle_exit", "old": "tilted", "new": "flat"}]
    answer = head.decide(replace(request(10, mode="vehicle", last_skill=DRIVING_ON), events=exit_event))
    assert answer.action == "replace" and answer.plan[0].name in {"enter_vehicle", "walk_road"}
    # An exit that a later entry made good is no exit.
    back = [*exit_event, {"kind": "vehicle_enter", "old": "flat", "new": "tilted"}]
    head, _ = drive_head()
    assert (
        head.decide(replace(request(10, mode="vehicle", last_skill=DRIVING_ON), events=back)).action
        == "go_on"
    )


def test_a_walk_does_not_go_on_with_the_figure_seated():
    head = MissionHead(goal_seed=3)
    head.goals.next = "fight"
    head.decide(request(mode="foot", people=True))
    walking = {"name": "walk_road", "status": "running", "queue": []}
    assert head.decide(request(3, mode="foot", last_skill=walking, people=True)).action == "go_on"
    seated = head.decide(request(6, mode="vehicle", last_skill=walking))
    assert seated.action == "replace" and seated.goal["name"] == "fight"
    assert [call.name for call in seated.plan] == ["press", "wait"]
    assert "walk_road does not fit" in seated.reason


def test_an_unreadable_mode_does_not_end_a_step_that_fits_either_way():
    head, _ = drive_head()
    unreadable = replace(
        request(5, last_skill=DRIVING_ON), judgment=None, minimap={"minimap": "none", "corrupt": True}
    )
    assert head.decide(unreadable).action == "go_on"


# D3: the event reaches the head once.


def test_the_goal_interruption_reaches_the_head_once(tmp_path, monkeypatch):
    conductor, _runner, obs, rgb = setup_conductor(tmp_path, monkeypatch)
    try:
        for t in (0, 0.1, 0.2):
            conductor._tick(replace(obs, time=t), rgb)
        conductor._tick(replace(obs, time=1, hud=Hud(screen="game", wanted=1, health=1)), rgb)
        rows = [json.loads(line) for line in (tmp_path / "session/head.jsonl").read_text().splitlines()]
        events = [e["kind"] for r in rows if r.get("type") == "request" for e in r["request"]["events"]]
        assert events.count("goal_interrupted") == 1
    finally:
        conductor.close()


# D4: a goal is the rules' own.


def goal_reply(**changes):
    goal = {
        "name": "escape",
        "started": 0,
        "deadline": 999,
        "seed": 1,
        "direction": "north",
        "attempts": 1,
    }
    return {
        "plan": [{"name": "wait", "args": {"duration": 5}}],
        "sentence": "Ich warte.",
        "goal": goal,
        **changes,
    }


def test_the_schema_for_a_model_has_no_goal_to_fill_in():
    from pilot.head import response_schema

    schema = response_schema()
    assert schema["properties"]["goal"] == {"type": "null"}
    assert "goal" in schema["required"]


def test_a_goal_from_a_head_that_is_not_the_rules_is_ignored(tmp_path, monkeypatch):
    from pilot.head import ScriptedHead

    conductor, runner, obs, rgb = setup_conductor(tmp_path, monkeypatch, head=ScriptedHead([goal_reply()]))
    try:
        for t in (0, 0.1, 0.2):
            conductor._tick(replace(obs, time=t), rgb)
        assert conductor.goal is None
        rows = [json.loads(line) for line in (tmp_path / "session/head.jsonl").read_text().splitlines()]
        assert [r["goal"] for r in rows if r.get("type") == "response"] == [None]
        # With no goal held, nothing the conductor stops for one: stars leave the plan to the head.
        active = runner.active
        conductor._tick(replace(obs, time=1, hud=Hud(screen="game", wanted=2, health=1)), rgb)
        assert not active.stops
    finally:
        conductor.close()


def test_a_goal_the_model_behind_the_rules_hands_in_is_dropped():
    class Model:
        answer = parse_response(goal_reply())

        def decide(self, request):
            return self.answer

    unclear = replace(request(), judgment=None, minimap={"minimap": "none", "corrupt": True})
    answer = MissionHead(Model()).decide(unclear)
    assert answer.goal is None and answer.plan[0].name == "wait"


def test_a_go_on_with_nothing_running_does_not_loop(tmp_path, monkeypatch):
    from pilot.head import ScriptedHead

    idle = {"plan": [], "sentence": "Ich bleibe dabei.", "action": "go_on"}
    head = ScriptedHead([idle] * 200)
    conductor, _runner, obs, rgb = setup_conductor(tmp_path, monkeypatch, head=head)
    try:
        for i in range(300):
            conductor._tick(replace(obs, time=i * 0.1), rgb)
        # Thirty seconds of ticks: a request at the start and one at the end of each short wait.
        assert conductor.request_count <= 12
        rows = [json.loads(line) for line in (tmp_path / "session/head.jsonl").read_text().splitlines()]
        assert {r["disposition"] for r in rows if r.get("type") == "response"} == {"refused"}
        assert not any(
            r["request"]["events"] == [{"kind": "plan_finished"}] for r in rows if r.get("type") == "request"
        )
    finally:
        conductor.close()


# D8: a goal's answer never kills a skill that cannot be cut short.


class Uninterruptible(HeldSkill):
    uninterruptible = True

    def __init__(self, name):
        super().__init__(name)
        self.limit = 1.0

    def step(self, observation):
        if observation.time >= 1.0:
            return SkillResult(status="done", reason="time-limit")
        return SkillResult(Pad(left=(0, -0.5)))


def test_a_goal_answer_waits_behind_the_opening_that_cannot_be_cut_short(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "pilot.skills.make_skill",
        lambda call, **kwargs: (Uninterruptible if call.name == "level_camera" else HeldSkill)(call.name),
    )
    runner = SkillRunner()
    conductor = Conductor(
        tmp_path / "session",
        notebook=tmp_path / "notes",
        runner=runner,
        head=MissionHead(goal_seed=7),
        opening=(SkillCall("level_camera", {}),),
        detector=NoEvents(),
        submit=immediate,
    )
    obs = Observation(
        Reading("flat", "none", 0, 0, 0, False, 1), True, 0, hud=Hud(screen="game", wanted=0, health=1)
    )
    rgb = np.zeros((720, 1280, 3), dtype=np.uint8)
    try:
        seen = []
        for i in range(40):
            conductor._tick(replace(obs, time=i * 0.1), rgb)
            if runner.active is not None and runner.active.name not in seen:
                seen.append(runner.active.name)
        assert seen[:2] == ["level_camera", "walk_road"]
        rows = [json.loads(line) for line in (tmp_path / "session/head.jsonl").read_text().splitlines()]
        assert next(r["disposition"] for r in rows if r.get("type") == "response") == "appended"
    finally:
        conductor.close()


# D5: an answer the conductor dropped consumed nothing.


def test_deciding_again_on_the_same_failure_after_a_dropped_answer_gives_the_same_answer():
    failed = {"name": "enter_vehicle", "status": "failed", "reason": "could not reach it", "queue": []}

    def settle(drop):
        head = MissionHead(goal_seed=3)
        head.decide(request(cars=True))
        first = head.decide(request(5, cars=True, last_skill=failed))
        if drop:
            head.discard()
        second = head.decide(request(5.2, cars=True, last_skill=failed))
        return first, second, head

    first, second, head = settle(drop=True)
    assert first.plan == second.plan and first.goal == second.goal and first.reason == second.reason
    assert first.reason == "retry: observed skill failure" and first.goal["attempts"] == 2
    assert sum(h["outcome"] == "started" for h in head.goals.history) == 1
    # Without the take-back the failure is spent: no recovery, one try gone for nothing.
    spent_first, spent_second, _ = settle(drop=False)
    assert spent_second.reason != spent_first.reason and spent_second.goal["attempts"] == 3


def test_the_conductor_gives_back_what_an_overtaken_answer_consumed(tmp_path, monkeypatch):
    dropped = []

    class Spy(MissionHead):
        def discard(self):
            dropped.append(self.goals.active and self.goals.active.attempts)
            super().discard()

    pending = []

    def submit(fn, *args):
        future = Future()
        pending.append((future, fn, args))
        return future

    conductor, _runner, obs, rgb = setup_conductor(
        tmp_path, monkeypatch, submit=submit, head=Spy(goal_seed=7)
    )
    try:
        conductor._tick(obs, rgb)
        future, fn, args = pending.pop(0)
        future.set_result(fn(*args))
        conductor._tick(replace(obs, time=0.1), rgb)
        conductor._tick(replace(obs, time=0.2), rgb)
        conductor._tick(replace(obs, time=0.3), rgb, events=[{"kind": "help_changed"}])
        future, fn, args = pending.pop(0)
        response = fn(*args)
        # An event while that answer is on its way overtakes it.
        conductor._tick(replace(obs, time=0.4), rgb, events=[{"kind": "route_appeared"}])
        future.set_result(response)
        conductor._tick(replace(obs, time=0.5), rgb)
        assert len(dropped) == 1
    finally:
        conductor.close()
