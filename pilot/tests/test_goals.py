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


def request(t=0, *, mode="foot", wanted=0, last=None, cars=False, people=False, **kwargs):
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


@pytest.mark.parametrize("name", LIMITS)
def test_each_goal_gives_up_at_its_deadline_and_is_not_reselected(name):
    head = MissionHead(goal_seed=12)
    head.goals.next = name
    initial = request(
        mode="vehicle" if name == "drive" else "foot",
        cars=name == "vehicle",
        wanted=1 if name == "escape" else 0,
    )
    first = head.decide(initial)
    assert first.goal["name"] == name
    expired = replace(initial, time=first.goal["deadline"], hud={"screen": "game", "health": 1, "wanted": 0})
    after = head.decide(expired)
    assert after.goal["name"] != name
    assert any(
        h["name"] == name and h["outcome"] == "gave_up" and h["reason"] == "limit" for h in head.goals.history
    )


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


def setup_conductor(tmp_path, monkeypatch, *, submit=immediate):
    monkeypatch.setattr("pilot.skills.make_skill", lambda call, **kwargs: HeldSkill(call.name))
    runner = SkillRunner()
    conductor = Conductor(
        tmp_path / "session",
        notebook=tmp_path / "notes",
        runner=runner,
        head=MissionHead(goal_seed=7),
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
        for i, kind in enumerate(
            (
                "subtitle_changed",
                "help_changed",
                "route_changed",
                "blips_changed",
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
        assert len(kept) >= 4
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
