"""Closed goal round and real conductor/runner ownership with scripted skill mechanics."""

import itertools
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


# The card's limits, written out: seconds and tries per goal.
SECONDS = {"vehicle": 90, "cruise": 240, "fight": 90, "escape": 180, "road": 90}
TRIES = {"vehicle": 3, "cruise": 3, "fight": 4, "escape": 4, "road": 4}
# Each goal's first step in its own situation, and the skill whose failure the goal answers.
SETUP = {
    "vehicle": ({"cars": True}, "enter_vehicle"),
    "cruise": ({"mode": "vehicle"}, "set_waypoint"),
    "fight": ({"people": True}, "punch"),
    "escape": ({"wanted": 1}, "walk"),
    "road": ({}, "walk_road"),
}


def running(name):
    return {"name": SETUP[name][1], "status": "running", "queue": []}


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
    assert all(h["outcome"] != "gave_up" for h in run(3)[1])
    assert all(row["goal"]["name"] == "story" for row in run(3)[0])


def test_fresh_head_does_not_claim_an_old_drive_result_as_its_arrival():
    head = MissionHead(goal_seed=1)
    head.goals.chooser = lambda offers: "cruise"
    answer = head.decide(request(mode="vehicle", last=done("drive_route", "route-gone")))
    assert answer.goal["name"] == "cruise"


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


def test_an_interruption_or_a_refusing_map_is_not_held_against_the_place():
    """Review C, 3 and 4: stars on the way to a shop, an objective on the way to a letter and a map
    that takes no waypoint say nothing about the place, which stays open to the session."""
    head = MissionHead(goal_seed=1)
    goals = head.goals
    for round_ in range(3):
        goals.active = None
        goals.mapless_until = -float("inf")
        goal = goals._start(request(10 * round_), None, False, 0)
        goal.name, goal.place, goal.step = "shop", "Ponsonbys", "travel"
        goals.guard(replace(request(10 * round_ + 1), hud={"screen": "game", "wanted": 2}))
    assert goals.abandonments["Ponsonbys"] == 0
    instance = goals.story_instance
    for round_ in range(3):
        goals.active = None
        goal = goals._start(request(100 + 10 * round_), None, False, 0)
        goal.name, goal.place, goal.step = "story", "Franklin", "travel"
        goals.guard(replace(request(101 + 10 * round_), objective="Fahre zum Treffpunkt."))
    # The letter is neither struck off nor passed over for the next one of its kind.
    assert goals.abandonments["Franklin"] == 0 and goals.story_instance == instance


def test_a_map_that_refuses_three_waypoints_is_left_alone_for_two_minutes():
    """Review C, 3: with set_waypoint failing every time the map was opened every few seconds for the
    whole session and every shop was struck off. Now the third refusal in a row sends the figure
    along the road for two minutes, and no place is blamed for the map."""
    head = MissionHead(goal_seed=4)
    head.goals.chooser = lambda offers: next(o["name"] for o in offers if o["name"] != "story")
    now, last, plans = 0.0, None, []
    for _ in range(60):
        answer = head.decide(replace(request(now), last_skill=last))
        name = answer.plan[0].name if answer.plan else None
        plans.append((now, name, (answer.goal or {}).get("name")))
        if name == "set_waypoint":
            last = {"name": "set_waypoint", "status": "failed", "reason": "menu-not-map", "t": now}
            now += 4
        elif name is None:
            now += 5
        else:
            last = {"name": name, "status": "done", "reason": "time-limit", "t": now}
            now += 30
    tried = [t for t, name, _ in plans if name == "set_waypoint"]
    roamed = [t for t, _, goal in plans if goal == "roam"]
    assert roamed and not any(head.goals.abandonments.values())
    assert len(tried) >= 4  # the map is asked again after the pause
    # Between the third refusal and the next question two minutes pass on the road.
    assert min(b - a for a, b in itertools.pairwise(tried[2:])) >= 100
    assert max(len([t for t in tried if start <= t < start + 120]) for start in tried) <= 3


def test_a_null_reason_on_a_finished_waypoint_is_read_as_no_place():
    """Review C, 10: `reason: None` reached a regular expression and raised."""
    head = MissionHead(goal_seed=5)
    head.decide(request(0))
    head.goals.active.step = "waypoint"
    head.goals.active.attempts = 1
    answer = head.decide(
        replace(request(3), last_skill={"name": "set_waypoint", "status": "done", "reason": None})
    )
    assert answer.plan or answer.action == "go_on"


def test_money_is_spent_in_a_shop_and_not_where_the_map_led_instead():
    """Review C, 6b: a shop's errand whose waypoint was read as the safehouse spent there."""
    for place, spend in (("Ponsonbys", "yes"), ("Unterschlupf", "no"), ("Franklin", "no")):
        head = MissionHead(goal_seed=2)
        goal = head.goals._start(request(0), None, False, 0)
        goal.name, goal.place, goal.step, goal.attempts = "shop", place, "use", 1
        answer = head.goals.decide(request(1), "on_foot")
        assert answer.plan[0].name == "use_place"
        assert answer.plan[0].args["spend"] == spend, place


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
        assert all(
            r["goal"]["name"] in {"story", "shop", "home", "mayhem", "cruise"} and r["step"] and r["reason"]
            for r in kept
        )
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
    head.goals.chooser = lambda offers: "cruise"
    first = head.decide(request(mode="vehicle"))
    missing = {"name": "drive_route", "status": "done", "reason": "route-gone", "queue": []}
    second = head.decide(request(4, mode="vehicle", last=missing))
    assert first.goal["name"] == second.goal["name"] == "cruise"
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
    assert confirmed.goal["name"] == first.goal["name"]


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
    assert head.decide(request(5, last_skill=own)).reason == "stuck on foot: another way, turned by 120"


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
        assert answer["goal"] is not None and answer["goal"]["name"] in {
            "story",
            "shop",
            "home",
            "mayhem",
            "cruise",
        }
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
    head.goals.chooser = lambda offers: "cruise"
    first = head.decide(request(mode="vehicle"))
    assert first.goal["name"] == "cruise"
    head.decide(request(1, mode="vehicle", last=waypoint_set("Away", 700)))
    return head, first


DRIVING_ON = {"name": "drive_route", "status": "running", "queue": []}


def test_a_drive_goal_does_not_go_on_with_the_figure_on_foot():
    head, _first = drive_head()
    seated = head.decide(request(5, mode="vehicle", last_skill=DRIVING_ON))
    assert seated.action == "go_on"
    afoot = head.decide(request(10, mode="foot", last_skill=DRIVING_ON))
    assert afoot.action == "replace" and afoot.goal["name"] == "cruise"
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
    head.goals.chooser = lambda offers: "mayhem"
    head.decide(request(mode="foot", people=True))
    walking = {"name": "walk_road", "status": "running", "queue": []}
    assert head.decide(request(3, mode="foot", last_skill=walking, people=True)).action == "go_on"
    seated = head.decide(request(6, mode="vehicle", last_skill=walking))
    assert seated.action == "replace" and seated.goal["name"] == "mayhem"
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
        "place": None,
        "distance": None,
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
        assert seen[:2] == ["level_camera", "set_waypoint"]
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


# Part 2: a trip with nothing asked goes to a place from the map's legend.

LEGEND = [
    "Ammu-Nation",
    "Autowaschanlage",
    "Friseursalon",
    "Fahrgeschäft",
    "Kino",
    "Fremde und Freaks",
    "Chinesen",
]


def waypoint_set(name, meters, places=LEGEND):
    return {
        "name": "set_waypoint",
        "status": "done",
        "reason": f"waypoint set: {name} ({meters}m); gameplay observed; places: {', '.join(places)}",
        "queue": [],
    }


def waypoint_refused(code, asked, places):
    return {
        "name": "set_waypoint",
        "status": "failed",
        "reason": f"{code}: {asked}; gameplay observed; places: {', '.join(places)}",
        "queue": [],
    }


def first_of_kind(kind, legend=LEGEND):
    from pilot.legend import kind_of

    return next(name for name in legend if kind_of(name) == kind)


def one_trip(head, t, *, legend=LEGEND, meters=300):
    """A drive goal that asks, is told where it went, follows the waypoint and arrives."""
    head.goals.active, head.goals.next = None, "cruise"
    ask = head.decide(request(t, mode="vehicle"))
    assert ask.goal["name"] == "cruise" and ask.plan[0].name == "set_waypoint"
    args = ask.plan[0].args
    name = args["place"] if "place" in args else first_of_kind(args["kind"], legend)
    told = head.decide(request(t + 5, mode="vehicle", last_skill=waypoint_set(name, meters, legend)))
    assert [call.name for call in told.plan] == ["drive_route"]
    arrived = head.decide(request(t + 60, mode="vehicle", last_skill=done("drive_route", "route-gone")))
    assert head.goals.history[-2]["outcome"] == "reached"
    return ask, told, arrived, name


def test_the_places_tail_and_the_waypoint_a_set_waypoint_reports_are_read():
    from pilot.goals import WAYPOINT_SET, read_places

    german = "Ammu-Nation mit Schießstand"
    done_reason = f"waypoint set: {german} (294m); gameplay observed; places: Ammu-Nation, {german}, Kino"
    assert read_places(done_reason) == ["Ammu-Nation", german, "Kino"]
    found = WAYPOINT_SET.match(done_reason)
    assert (found.group(1), found.group(2)) == (german, "294")
    unread = WAYPOINT_SET.match("waypoint set: Golf (distance not read); gameplay observed; places: Golf")
    assert unread.group(1) == "Golf" and unread.group(2) is None
    refused = (
        f"place-not-in-legend: Friseursalon; gameplay observed; places: {german}, Garage in Pillbox Hill"
    )
    assert read_places(refused) == [german, "Garage in Pillbox Hill"]
    # A legend that held nothing prints an empty tail; a failure that read none has no tail at all.
    assert read_places("place-not-in-legend: shop; gameplay observed; places: ") == []
    assert read_places("time-limit: confirm; gameplay not verified") is None
    assert read_places(None) is None


def test_the_trip_is_followed_without_spending_a_second_try_and_a_failure_is_answered_in_the_goal():
    head = MissionHead(goal_seed=51)
    head.goals.chooser = lambda offers: "cruise"
    head.decide(request(mode="vehicle"))
    told = head.decide(request(5, mode="vehicle", last_skill=waypoint_set("Kino", 700)))
    assert told.goal["attempts"] == 1 and told.plan[0].name == "drive_route"
    # A drive that fails is not met with the rules' point on the map: the goal asks for a place.
    broken = {"name": "drive_route", "status": "failed", "reason": "failed-recovery", "queue": []}
    retry = head.decide(request(40, mode="vehicle", last_skill=broken))
    assert any(h["outcome"] == "gave_up" for h in head.goals.history)
    assert retry.goal["started"] > told.goal["started"]
    assert retry.goal["name"] in {"story", "shop", "home", "mayhem", "cruise"}
    assert "target" not in retry.plan[0].args


def test_an_escape_from_the_police_keeps_its_point_on_the_map():
    head = MissionHead(goal_seed=51)
    head.goals.chooser = lambda offers: "cruise"
    answer = head.decide(request(mode="vehicle", wanted=2))
    assert answer.goal["name"] == "escape"
    assert [call.name for call in answer.plan] == ["get_away"]
    assert "set_waypoint" not in names(answer)


def test_the_rules_outside_a_goal_take_a_place_too_when_nothing_is_asked_and_not_when_it_is():
    flicker = {"minimap": "tilted", "route": "none", "blips": [{"color": "yellow", "x": 10, "y": 25}]}
    unasked = replace(request(mode="vehicle"), minimap=flicker)
    head = MissionHead(goal_seed=51)
    head.goals.chooser = lambda offers: "cruise"
    answer = head.decide(unasked)
    assert head.last_rule == "vehicle_waypoint" and answer.goal is None
    assert [call.name for call in answer.plan] == ["set_waypoint"]
    assert answer.plan[0].args["target"] == "away"
    asked = replace(unasked, objective="Fahre zum Treffpunkt.")
    head = MissionHead(goal_seed=51)
    head.goals.chooser = lambda offers: "cruise"
    answer = head.decide(asked)
    # Asked to go somewhere, with no route and the game's marker on the map: the car goes at the marker.
    assert head.last_rule == "objective_blip_reach"
    assert [(call.name, call.args["color"], call.args["mode"]) for call in answer.plan] == [
        ("drive_to_blip", "yellow", "reach")
    ]
    asked = replace(asked, minimap={**flicker, "blips": []})
    head = MissionHead(goal_seed=51)
    head.goals.chooser = lambda offers: "cruise"
    answer = head.decide(asked)
    assert head.last_rule == "vehicle_waypoint"
    assert answer.plan[0].args["target"] in {"mission", "away"} and "kind" not in answer.plan[0].args


def test_what_a_dropped_answer_learned_of_the_legend_is_given_back_too():
    head = MissionHead(goal_seed=51)
    head.goals.chooser = lambda offers: "cruise"
    head.decide(request(mode="vehicle"))
    head.decide(request(5, mode="vehicle", last_skill=waypoint_set("Kino", 700)))
    assert "Kino" in head.goals.known
    head.discard()
    assert head.goals.known == {} and head.goals.active.place is None


def test_a_goal_names_its_place_and_distance_for_the_log_and_the_contract_checks_them():
    for bad in (
        {"place": 7},
        {"place": ""},
        {"distance": -1},
        {"distance": float("inf")},
        {"distance": True},
    ):
        reply = goal_reply()
        reply["goal"] = {**reply["goal"], **bad}
        with pytest.raises(ValueError):
            parse_response(reply)
    reply = goal_reply()
    reply["goal"] = {**reply["goal"], "place": "Ammu-Nation mit Schießstand", "distance": 294.0}
    assert parse_response(reply).goal["place"] == "Ammu-Nation mit Schießstand"


class Setting(HeldSkill):
    """set_waypoint as the legend skill ends it: done after a moment, saying where it went."""

    uninterruptible = True

    def step(self, observation):
        if observation.time >= 0.5:
            reason = "waypoint set: Kino (700m); gameplay observed; places: Kino, Golf, Fremde und Freaks"
            return SkillResult(status="done", reason=reason)
        return SkillResult(Pad(left=(0, 0)))


def test_the_conductor_carries_where_the_waypoint_went_to_the_head_and_follows_it(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "pilot.skills.make_skill",
        lambda call, **kwargs: (Setting if call.name == "set_waypoint" else HeldSkill)(call.name),
    )
    runner = SkillRunner()
    conductor = Conductor(
        tmp_path / "session",
        notebook=tmp_path / "notes",
        runner=runner,
        head=MissionHead(goal_seed=7, chooser=lambda offers: "cruise"),
        detector=NoEvents(),
        submit=immediate,
    )
    reading = Reading("tilted", "none", 0, 0, 0, False, 1)
    obs = Observation(reading, True, 0, hud=Hud(screen="game", wanted=0, health=1))
    rgb = np.zeros((720, 1280, 3), dtype=np.uint8)
    try:
        started = []
        for i in range(30):
            conductor._tick(replace(obs, time=i * 0.1), rgb)
            if runner.active is not None and runner.active.name not in started:
                started.append(runner.active.name)
        assert started == ["set_waypoint", "drive_route"]
        assert conductor.goal["place"] == "Kino" and conductor.goal["distance"] == 700
        # The waypoint is the second half of the trip: no second try went for it.
        assert conductor.goal["attempts"] == 1
        rows = [json.loads(line) for line in (tmp_path / "session/head.jsonl").read_text().splitlines()]
        answers = [r for r in rows if r.get("type") == "response"]
        assert answers[0]["plan"][0]["name"] == "set_waypoint"
        assert answers[1]["plan"] == [{"name": "drive_route", "args": {"duration": 120}}]
        assert "Kino" in answers[1]["sentence"] and "700 m" in answers[1]["sentence"]
    finally:
        conductor.close()


# Part 3: how a drive that ended without arriving is answered (skills.py DriveRoute).


def routed(t, route="purple", **kwargs):
    value = request(t, mode="vehicle", **kwargs)
    return replace(value, minimap={**value.minimap, "route": route})


def failed_drive(reason, n=0):
    """The nth drive that ended so: results that differ only in n are told apart as new ones."""
    return {"name": "drive_route", "status": "failed", "reason": reason, "queue": [], "n": n}


def on_the_way(head, t=0, place="Kino"):
    head.goals.chooser = lambda offers: "cruise"
    """A drive goal that asked for a place, was told it went to it and has begun to follow the route."""
    head.decide(request(t, mode="vehicle"))
    told = head.decide(routed(t + 5, last_skill=waypoint_set(place, 700)))
    assert [call.name for call in told.plan] == ["drive_route"]
    return told


def names(answer):
    return [call.name for call in answer.plan]


def test_a_car_that_will_not_move_is_left_and_the_same_car_is_not_taken_at_once():
    head = MissionHead(goal_seed=51)
    head.goals.chooser = lambda offers: "cruise"
    on_the_way(head)
    tries = head.goals.active.attempts
    left = head.decide(routed(40, last_skill=failed_drive("dead-or-held")))
    assert names(left) == ["press", "wait", "walk_road"] and left.plan[0].args["button"] == "triangle"
    assert left.goal["name"] == "cruise" and left.goal["attempts"] == tries  # leaving costs no try
    assert "dead-or-held" in left.reason
    # On foot with a car in sight, three seconds later: away from the car first, not into it.
    early = head.decide(request(43, mode="foot", cars=True, last_skill=done("walk_road", "time-limit")))
    assert names(early) == ["walk_road"]
    later = head.decide(request(53, mode="foot", cars=True, last_skill=done("walk_road", "time-limit 2")))
    assert names(later) == ["enter_vehicle"]
    # In another car the trip goes on to the same place, and the head asks for no other.
    again = head.decide(routed(70, last_skill=done("enter_vehicle", "entered vehicle")))
    assert names(again) == ["drive_route"]
    assert again.goal["name"] == "cruise" and again.goal["place"] == "Kino"


def test_an_exit_that_does_not_show_is_pressed_again_but_not_for_ever():
    head = MissionHead(goal_seed=51)
    head.goals.chooser = lambda offers: "cruise"
    on_the_way(head)
    answers = [head.decide(routed(40, last_skill=failed_drive("dead-or-held")))]
    for t in (55, 70, 85, 100):
        # Still seated at the end of the plan: the figure did not get out.
        answers.append(head.decide(routed(t, last_skill=done("walk_road", f"time-limit {t}"))))
    assert [names(a) for a in answers[:3]] == [["press", "wait", "walk_road"]] * 3
    assert any(h["reason"] == "vehicle exit not observed after three attempts" for h in head.goals.history)


def test_a_second_car_that_is_held_is_left_as_well():
    head = MissionHead(goal_seed=51)
    head.goals.chooser = lambda offers: "cruise"
    on_the_way(head)
    head.decide(routed(40, last_skill=failed_drive("dead-or-held")))
    head.decide(request(55, mode="foot", cars=True, last_skill=done("walk_road", "time-limit")))
    head.decide(routed(70, last_skill=done("enter_vehicle", "entered vehicle")))
    second = head.decide(routed(100, last_skill=failed_drive("dead-or-held")))
    assert names(second) == ["press", "wait", "walk_road"] and second.goal["name"] == "cruise"


def test_an_unreadable_map_is_answered_with_a_look_round_and_the_second_time_by_leaving_the_car():
    head = MissionHead(goal_seed=51)
    head.goals.chooser = lambda offers: "cruise"
    on_the_way(head)
    tries = head.goals.active.attempts
    # The map is the trouble: the route may read as gone, and the answer is still the drive.
    first = head.decide(routed(40, route="none", last_skill=failed_drive("map-unreadable")))
    assert names(first) == ["look", "drive_route"]
    assert first.plan[0].args["angle"] == 180 and first.plan[1].args["duration"] == 120
    assert first.goal["name"] == "cruise" and first.goal["place"] == "Kino"
    assert first.goal["attempts"] == tries + 1
    assert "map-unreadable" in first.reason
    # The drive runs again, and ends for the same map again: this car is left, like a held one.
    head.decide(routed(55, last_skill={"name": "drive_route", "status": "running", "queue": []}))
    second = head.decide(routed(70, last_skill=failed_drive("map-unreadable", 2)))
    assert names(second) == ["press", "wait", "walk_road"] and second.plan[0].args["button"] == "triangle"
    assert second.goal["name"] == "cruise" and second.goal["attempts"] == tries + 1  # leaving costs no try
    assert "map-unreadable" in second.reason
    assert head.goals.active.unreadable == 0  # the next car is read afresh


def test_a_drive_that_lost_its_route_far_from_the_place_sets_that_waypoint_again_once_and_then_gives_up():
    head = MissionHead(goal_seed=51)
    head.goals.chooser = lambda offers: "cruise"
    on_the_way(head)
    first = head.decide(routed(40, route="none", last_skill=failed_drive("route-lost-far")))
    assert names(first) == ["set_waypoint"]
    assert first.plan[0].args == {"place": "Kino", "duration": 45}
    assert "route-lost-far" in first.reason
    followed = head.decide(routed(55, last_skill=waypoint_set("Kino", 650)))
    assert names(followed) == ["drive_route"] and followed.goal["name"] == "cruise"
    second = head.decide(routed(100, route="none", last_skill=failed_drive("route-lost-far")))
    assert second.goal["name"] != "cruise"
    gave_up = [h for h in head.goals.history if h["name"] == "cruise" and h["outcome"] == "gave_up"]
    assert (
        len(gave_up) == 1
        and "route-lost-far twice" in gave_up[0]["reason"]
        and "Kino" in gave_up[0]["reason"]
    )
    assert head.goals.abandoned == "cruise" and head.goals.abandonments["Kino"] == 1


def test_a_drive_that_got_no_nearer_is_driven_again_on_its_waypoint_once_and_then_given_up():
    head = MissionHead(goal_seed=51)
    head.goals.chooser = lambda offers: "cruise"
    on_the_way(head)
    first = head.decide(routed(40, last_skill=failed_drive("no-progress")))
    # The waypoint stands and set_waypoint refuses to toggle it off: the drive begins anew.
    assert names(first)[-1] == "drive_route" and "set_waypoint" not in names(first)
    assert first.goal["name"] == "cruise" and first.goal["place"] == "Kino"
    second = head.decide(routed(90, last_skill=failed_drive("no-progress", 2)))
    assert second.goal["name"] != "cruise"
    assert any("twice" in h["reason"] for h in head.goals.history if h["outcome"] == "gave_up")


def test_each_place_has_its_own_count_of_drives_that_got_nowhere():
    head = MissionHead(goal_seed=51)
    head.goals.chooser = lambda offers: "cruise"
    on_the_way(head)
    head.decide(routed(40, last_skill=failed_drive("no-progress")))
    # Another place is another trip: it has its own first time.
    head.goals.end(request(50), "new trip")
    head.goals.last_name = "story"
    head.decide(routed(55))
    other = head.decide(routed(60, last_skill=waypoint_set("Golf", 300)))
    assert other.goal["place"] == "Golf"
    again = head.decide(routed(90, last_skill=failed_drive("no-progress", 2)))
    assert again.goal["name"] == "cruise"


def test_arrival_reaches_the_trip_as_route_gone_did():
    head = MissionHead(goal_seed=51)
    head.goals.chooser = lambda offers: "cruise"
    on_the_way(head)
    head.decide(routed(60, route="none", last_skill=done("drive_route", "arrived")))
    assert [h["outcome"] for h in head.goals.history if h["name"] == "cruise"] == ["started", "reached"]
    assert head.goals.history[-2]["place"] == "Kino"


def test_a_drive_out_of_time_on_a_route_that_stands_is_called_again_and_the_goal_decides():
    head = MissionHead(goal_seed=51)
    head.goals.chooser = lambda offers: "cruise"
    on_the_way(head)
    started = head.goals.active.started
    again = head.decide(routed(70, last_skill=done("drive_route", "time-limit")))
    assert names(again) == ["drive_route"] and again.goal["name"] == "cruise"
    over = head.decide(routed(started + LIMITS["cruise"][0], last_skill=done("drive_route", "time-limit 2")))
    assert over.goal["name"] != "cruise"
    assert any(h["reason"] == "limit" for h in head.goals.history if h["name"] == "cruise")


DRIVING_ON = {"name": "drive_route", "status": "running", "reason": None, "queue": []}


def vanishing(**kwargs):
    event = {"kind": "route_vanished", "previous": "yellow", "current": "none"}
    return replace(routed(5, route="none", last_skill=DRIVING_ON, **kwargs), events=[event])


def test_with_no_goal_a_running_drive_is_let_run_out_when_its_route_goes():
    head = MissionHead(goal_seed=1)
    assert head.goals.active is None
    answer = head.decide(vanishing())
    assert answer.action == "go_on" and answer.plan == () and answer.goal is None
    assert head.last_rule == "drive_ends" and head.goals.active is None
    # What it ends as is then answered by the rules: a route lost far away is a new waypoint.
    after = head.decide(routed(7, route="none", last_skill=failed_drive("route-lost-far")))
    assert names(after)[0] == "set_waypoint"


def test_a_mission_drive_is_let_run_out_too_and_wanted_or_a_finished_drive_is_not():
    mission = replace(vanishing(), objective="Fahre zum Treffpunkt.")
    head = MissionHead(goal_seed=1)
    assert head.decide(mission).action == "go_on"
    stars = replace(vanishing(), hud={"screen": "game", "health": 1, "wanted": 2})
    assert MissionHead(goal_seed=1).decide(stars).action == "replace"
    finished = replace(vanishing(), last_skill=done("drive_route", "arrived"))
    head = MissionHead(goal_seed=1)
    head.decide(finished)
    assert head.last_rule != "drive_ends"


def test_a_held_car_is_left_by_the_rules_outside_a_goal_too_and_other_failures_keep_their_route():
    asked = replace(routed(5, route="none", last_skill=failed_drive("dead-or-held")), objective="Fahre los.")
    head = MissionHead(goal_seed=1)
    answer = head.decide(asked)
    assert head.last_rule == "leave_held_vehicle" and names(answer) == ["press", "wait", "walk_road"]
    other = MissionHead(goal_seed=1)
    answer = other.decide(replace(asked, last_skill=failed_drive("failed-recovery")))
    assert other.last_rule == "failed_vehicle_skill" and names(answer)[0] == "set_waypoint"


class Scripted(HeldSkill):
    """A skill for the goal that ends after a moment: drive_route as the script says, the rest done."""

    def __init__(self, call, script, delay):
        super().__init__(call.name)
        self.call, self.script, self.delay, self.since = call, script, delay, None

    def step(self, observation):
        if self.since is None:
            self.since = observation.time
        # The plan that leaves a car takes as long as it says; the rest ends after a moment.
        timed = self.name in ("press", "wait", "walk_road")
        if observation.time - self.since < (self.call.args["duration"] if timed else self.delay):
            return SkillResult(Pad(left=(0, 0)))
        if self.name == "drive_route":
            if not self.script:
                return SkillResult(Pad(left=(0, 0)))  # the script is told: it drives on
            status, reason = self.script.pop(0)
            return SkillResult(status=status, reason=reason)
        if self.name == "set_waypoint":
            return SkillResult(
                status="done", reason="waypoint set: Kino (700m); gameplay observed; places: Kino, Golf"
            )
        return SkillResult(status="done", reason="time-limit")


def conducted(tmp_path, monkeypatch, script, *, delay=0.3):
    monkeypatch.setattr("pilot.skills.make_skill", lambda call, **kwargs: Scripted(call, script, delay))
    runner = SkillRunner()
    conductor = Conductor(
        tmp_path / "session",
        notebook=tmp_path / "notes",
        runner=runner,
        head=MissionHead(goal_seed=7),
        detector=NoEvents(),
        submit=immediate,
    )
    conductor.head.goals.chooser = lambda offers: "cruise"
    return conductor, runner


def run(conductor, runner, seconds, *, seat, route, events=lambda i: (), **kwargs):
    """Tick for `seconds`. `seat` and `route` say what the picture shows, from the skill that runs, the
    names of those that have started and the time; the list of the skills started is the result."""
    from pilot.contract import Detection

    started = []
    car = (Detection("car", (500, 300, 700, 420), 0.9),)
    rgb = np.zeros((720, 1280, 3), dtype=np.uint8)
    last = None
    for i in range(int(seconds * 10)):
        active = None if runner.active is None else runner.active.name
        names = [name for name, _ in started]
        shape = "tilted" if seat(active, names, i / 10) == "vehicle" else "flat"
        reading = Reading(shape, route(active, names, i / 10), 0, 0, 0, False, 1)
        obs = Observation(reading, True, i * 0.1, hud=Hud(screen="game", wanted=0, health=1), objects=car)
        conductor._tick(obs, rgb, events=events(i), **kwargs)
        if runner.active is not None and runner.active.call is not last:
            last = runner.active.call
            started.append((last.name, dict(last.args)))
    return started


def test_the_conductor_leaves_a_held_car_and_goes_on_to_the_same_place_in_another(tmp_path, monkeypatch):
    conductor, runner = conducted(tmp_path, monkeypatch, [("failed", "dead-or-held")])

    def seat(active, names, now):
        # Seated until the exit has been pressed, on foot while the plan walks, seated in the next car.
        return "foot" if "press" in names and "enter_vehicle" not in names else "vehicle"

    try:
        started = run(
            conductor,
            runner,
            40,
            seat=seat,
            route=lambda active, names, now: "purple" if "drive_route" in names else "none",
        )
        order = [name for name, _ in started]
        assert order[:7] == [
            "set_waypoint",
            "drive_route",
            "press",
            "wait",
            "walk_road",
            "enter_vehicle",
            "drive_route",
        ]
        assert started[2][1]["button"] == "triangle"
        assert conductor.goal["name"] == "cruise" and conductor.goal["place"] == "Kino"
        # A held car, a walk and a second entry did not use up the three tries of the trip.
        assert conductor.goal["attempts"] <= 2
    finally:
        conductor.close()


def test_the_conductor_looks_round_after_an_unreadable_map_and_leaves_the_car_the_second_time(
    tmp_path, monkeypatch
):
    conductor, runner = conducted(
        tmp_path, monkeypatch, [("failed", "map-unreadable"), ("failed", "map-unreadable")]
    )

    def seat(active, names, now):
        return "foot" if "press" in names and "enter_vehicle" not in names else "vehicle"

    try:
        started = run(
            conductor,
            runner,
            50,
            seat=seat,
            route=lambda active, names, now: "purple" if "drive_route" in names else "none",
        )
        order = [name for name, _ in started]
        assert order[:9] == [
            "set_waypoint",
            "drive_route",
            "look",
            "drive_route",
            "press",
            "wait",
            "walk_road",
            "enter_vehicle",
            "drive_route",
        ]
        assert started[2][1]["angle"] == 180
        assert conductor.goal["name"] == "cruise" and conductor.goal["place"] == "Kino"
    finally:
        conductor.close()


def test_the_conductor_sets_the_place_again_once_and_then_moves_on_to_the_next_goal(tmp_path, monkeypatch):
    conductor, runner = conducted(
        tmp_path, monkeypatch, [("failed", "route-lost-far"), ("failed", "route-lost-far")]
    )
    try:
        # The route is there while a drive runs and gone when it ended and while the map is open.
        started = run(
            conductor,
            runner,
            40,
            seat=lambda active, names, now: "vehicle",
            route=lambda active, names, now: (
                "purple" if active == "drive_route" and now - runner.active.since < 0.2 else "none"
            ),
        )
        order = [(name, args.get("place")) for name, args in started]
        assert order[:4] == [
            ("set_waypoint", None),
            ("drive_route", None),
            ("set_waypoint", "Kino"),
            ("drive_route", None),
        ]
        # The second drive lost its route as well: the trip is given up and the round goes on.
        history = [(h["name"], h["outcome"]) for h in conductor.head.goals.history]
        assert history[:2] == [("cruise", "started"), ("cruise", "gave_up")]
        assert history[2][0] != "cruise" and history[2][1] == "started"
        assert "twice" in conductor.head.goals.history[1]["reason"]
    finally:
        conductor.close()


def test_the_conductor_lets_a_drive_end_by_itself_when_a_mission_route_goes(tmp_path, monkeypatch):
    from pilot.scene import SceneText

    # The drive would end as arrived after 1.5 s; its route goes after half a second.
    conductor, runner = conducted(tmp_path, monkeypatch, [("done", "arrived")], delay=1.5)
    try:
        vanished = [{"kind": "route_vanished", "previous": "yellow", "current": "none"}]
        started = run(
            conductor,
            runner,
            1.4,
            seat=lambda active, names, now: "vehicle",
            route=lambda active, names, now: "purple" if now < 0.5 else "none",
            events=lambda i: vanished if i == 5 else (),
            text=SceneText(objective="Fahre zum Treffpunkt."),
        )
        assert [name for name, _ in started] == ["drive_route"]
        rows = [json.loads(line) for line in (tmp_path / "session/head.jsonl").read_text().splitlines()]
        replies = [r for r in rows if r.get("type") == "response"]
        assert any(r.get("action") == "go_on" and r.get("disposition") == "kept" for r in replies)
    finally:
        conductor.close()


@pytest.fixture(autouse=True)
def no_place_model(monkeypatch):
    # These goal tests exercise sessions without the optional place model.
    monkeypatch.setattr("pilot.conductor.ahead.where", lambda: None)
