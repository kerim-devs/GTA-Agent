"""Recorded decisions joined across a fixed mission trip; no console or model calls."""

import json
from concurrent.futures import Future
from copy import deepcopy
from dataclasses import fields, replace
from pathlib import Path

import numpy as np

from pilot.conductor import Conductor
from pilot.contract import (
    NEUTRAL_PAD,
    Answer,
    Blip,
    Detection,
    Hud,
    Judgment,
    Observation,
    Reading,
    SkillResult,
)
from pilot.head import HeadRequest, SkillCall
from pilot.mission import MissionHead
from pilot.skills import DriveRoute, SkillRunner, make_skill

FIXTURES = Path(__file__).parent / "fixtures"
RGB = np.zeros((720, 1280, 3), dtype=np.uint8)


def load(name):
    return json.loads((FIXTURES / name).read_text())


def sequence(name):
    return load("mission-trip-requests.json")["sequences"][name]


def request(raw):
    accepted = {field.name for field in fields(HeadRequest)} - {"notebook", "jpeg_path"}
    return HeadRequest(
        **{key: deepcopy(value) for key, value in raw.items() if key in accepted},
        notebook="",
        jpeg_path="unused.jpg",
    )


def shifted(value, seconds):
    """Join independent recordings on one clock without changing any sensor values or ages."""
    minimap, judgment = deepcopy(value.minimap), deepcopy(value.judgment)
    if minimap.get("gps_time") is not None:
        minimap["gps_time"] += seconds
    if judgment and judgment.get("capture") is not None:
        judgment["capture"] += seconds
    return replace(value, time=value.time + seconds, minimap=minimap, judgment=judgment)


def observation(value):
    minimap = dict(value.minimap)
    minimap["blips"] = tuple(Blip(**item) for item in minimap.get("blips", ()))
    judgment = None
    # P93 keeps only the observed mode; it has no raw judge response to reconstruct.
    if value.judgment and set(value.judgment) != {"mode"}:
        raw = value.judgment
        judgment = Judgment(
            raw["capture"],
            {key: Answer(**answer) for key, answer in raw["answers"].items()},
            raw["probabilities"],
            raw["duration"],
            raw["server"],
        )
    return Observation(
        Reading(**minimap),
        None,
        value.time,
        objects=tuple(Detection(**item) for item in value.objects),
        hud=Hud(**value.hud) if value.hud else None,
        judgment=judgment,
        mode=(value.judgment or {}).get("mode"),
        place=value.place,
    )


def plans(response):
    return [call.name for call in response.plan]


def travelling():
    """A real seated start and observed waypoint, before the recorded P93 approach."""
    head = MissionHead(goal_seed=7, task="mission-drive")
    start, waypoint = [request(row["request"]) for row in sequence("arrival_setup")]
    first = head.decide(start)
    assert plans(first) == ["set_waypoint"]
    following = head.decide(waypoint)
    assert plans(following) == ["drive_route"]
    assert following.goal["place"] == "Fremde und Freaks"
    return head, waypoint, following.goal


def assert_neutral_finish(response, step, value):
    assert response.step == step
    assert response.reason
    assert plans(response) == ["wait"]
    for call in response.plan:
        assert make_skill(call).step(observation(value)).pad == NEUTRAL_PAD


def complete_wait(response, value):
    """Execute a newly planned wait; the old recording cannot contain its result."""
    assert plans(response) == ["wait"]
    runner = SkillRunner()
    runner.replace(response.plan)
    for _ in range(2):
        assert runner.tick(observation(value)).pad == NEUTRAL_PAD
    # Only the clock advances. No fresh image or new judge answer is invented.
    value = replace(value, time=value.time + response.plan[0].args["duration"] + 0.1)
    result = runner.tick(observation(value))
    assert (result.status, result.reason, result.pad) == ("done", "time-limit", NEUTRAL_PAD)
    assert not runner.has_plan
    receipt = runner.describe()
    return replace(value, last_skill=receipt, events=[{"kind": "skill_ended", "skill": receipt}])


def test_recorded_own_car_is_taken_without_rewalking_the_reached_blue_marker():
    head = MissionHead(goal_seed=7, task="mission-drive")
    responses = [head.decide(request(row["request"])) for row in load("own-car-1957.json")]
    assert any("enter_vehicle" in plans(response) for response in responses)
    assert all("walk_to" not in plans(response) for response in responses[2:])
    assert all(
        not {"drive_route", "drive_on", "set_waypoint"}.intersection(plans(response))
        for response in responses
    )


def test_recorded_tilted_map_after_menu_does_not_prove_the_figure_entered_a_car():
    head = MissionHead(goal_seed=7, task="mission-drive")
    rows = sequence("foot_after_map")
    assert rows[1]["request"]["minimap"]["minimap"] == "tilted"
    assert rows[1]["request"]["judgment"]["mode"] == "unknown"
    for row in rows:
        response = head.decide(request(row["request"]))
        assert not {"drive_route", "drive_on", "set_waypoint"}.intersection(plans(response))


class NoEvents:
    def update(self, *args, **kwargs):
        return ()


class Delivery:
    def __init__(self, *, deferred=False):
        self.deferred = deferred
        self.jobs = []

    def __call__(self, function, *args):
        future = Future()
        future.set_running_or_notify_cancel()
        self.jobs.append((future, function, args))
        if not self.deferred:
            future.set_result(function(*args))
        return future


def recorded_drive(tmp_path, *, deferred=False):
    head, waypoint, goal = travelling()
    rows = sequence("quiet_and_waypoint_failures")
    first, quiet = [request(row["request"]) for row in rows[:2]]
    offset = waypoint.time + 1 - first.time
    first, quiet = shifted(first, offset), shifted(quiet, offset)
    # These are the three actual queued drive calls before the 20:21 quiet replacement.
    runner = SkillRunner()
    runner.replace(tuple(SkillCall(**item) for item in rows[0]["recorded_plan"]))
    delivery = Delivery(deferred=deferred)
    now = [first.time]
    conductor = Conductor(
        tmp_path / "session",
        head=head,
        runner=runner,
        detector=NoEvents(),
        submit=delivery,
        quiet_seconds=60,
        notebook=tmp_path / "notebook.txt",
        clock=lambda: now[0],
    )
    return conductor, delivery, now, first, quiet, goal


def test_recorded_sixty_second_quiet_check_keeps_the_trip_and_remaining_drives(tmp_path):
    conductor, delivery, now, first, quiet, goal = recorded_drive(tmp_path)
    try:
        for _ in range(3):
            conductor.tick(observation(first), RGB)
        before = conductor.runner.describe()
        assert before["name"] == "drive_route" and before["status"] == "running"
        assert before["queue"] == ["drive_route", "drive_route"]
        now[0] = quiet.time
        for _ in range(2):
            result = conductor.tick(observation(quiet), RGB)
        after = conductor.runner.describe()
        assert after["name"] == "drive_route" and after["status"] == "running"
        assert after["queue"] == before["queue"]
        assert not result.pad.buttons
        assert conductor.goal["place"] == goal["place"]
        delivered = [future.result() for future, _, _ in delivery.jobs]
        assert len(delivered) >= 2
        assert all(response.action == "go_on" for response in delivered)
    finally:
        conductor.close()


def test_recorded_waypoint_failures_end_neutrally_without_choosing_another_errand():
    head = MissionHead(goal_seed=7, task="mission-drive")
    rows = sequence("quiet_and_waypoint_failures")
    value = request(rows[1]["request"])
    opening = head.decide(value)
    assert plans(opening) == ["set_waypoint"]
    responses = [opening]
    for row in rows[2:]:
        if plans(responses[-1]) == ["wait"] and responses[-1].step != "failed":
            value = complete_wait(responses[-1], value)
            assert value.time < row["request"]["time"]
            responses.append(head.decide(value))
        value = request(row["request"])
        responses.append(head.decide(value))
    assert sum("set_waypoint" in plans(response) for response in responses) <= 2
    terminal = False
    for response in responses:
        if response.step == "failed":
            terminal = True
        if terminal:
            assert_neutral_finish(response, "failed", value)
        elif response.goal:
            assert response.goal["name"] == opening.goal["name"]
            assert response.goal["started"] == opening.goal["started"]
    assert terminal


def test_two_completed_waits_do_not_continue_an_empty_plan():
    """Known product regression: distinct real waits currently collide on equal receipts."""
    head = MissionHead(goal_seed=7, task="mission-drive")
    rows = [request(row["request"]) for row in sequence("unclosed_map")]
    for value in rows[:2]:
        response = head.decide(value)
    assert plans(response) == ["wait"]
    goal = response.goal
    # Hold the recorded map observation for the new waits; this is not a physical replay.
    first = complete_wait(response, rows[2])
    response = head.decide(first)
    assert plans(response) == ["wait"]
    second = complete_wait(response, first)
    assert second.time > first.time
    assert second.last_skill == first.last_skill
    response = head.decide(second)
    assert response.action != "go_on", "Both real waits ended; there is no active plan to continue"
    assert plans(response) == ["wait"]
    if response.goal:
        assert (response.goal["name"], response.goal["started"]) == (goal["name"], goal["started"])
    assert_neutral_finish(response, response.step, second)


def test_recorded_drive_arrival_reaches_a_terminal_mission_outcome():
    head, _, goal = travelling()
    data = load("p93_arrival.json")
    head.decide(request(data["seed_request"]))
    skill = DriveRoute({})
    base = Reading("tilted", "purple", 0, 0, 0, False, 0.95)
    for values in data["drive_readings"]:
        row = dict(zip(data["reading_fields"], values, strict=True))
        now = row.pop("source_t") + data["clock_offset"]
        result = skill.step(Observation(replace(base, **row), True, now, mode="vehicle"))
    assert (result.status, result.reason, result.end_distance) == ("done", "arrived", 46)
    assert result.pad == NEUTRAL_PAD
    for raw in data["head_requests"]:
        value = request(raw)
        # Connect the real skill's replayed outcome to the recorded downstream request.
        value = replace(
            value,
            last_skill={
                **value.last_skill,
                "status": result.status,
                "reason": result.reason,
                "end_distance": result.end_distance,
                "distance_age": result.distance_age,
            },
        )
        response = head.decide(value)
        assert_neutral_finish(response, "arrived", value)
        assert not response.goal or response.goal["place"] == goal["place"]


def test_recorded_unclosed_map_finishes_without_restarting_after_the_old_deadline(tmp_path, monkeypatch):
    """Recorded map failures run through the real conductor; only the final clock jump is injected."""
    rows = [request(row["request"]) for row in sequence("unclosed_map")]
    outcomes = iter(rows[1:])
    next_outcome = [next(outcomes)]

    class RecordedWaypoint:
        name = "set_waypoint"
        limit = 45
        opens = ("map", "pause")

        def step(self, seen):
            recorded = next_outcome[0]
            if recorded is None or seen.time < recorded.time:
                return SkillResult()
            next_outcome[0] = next(outcomes, None)
            return SkillResult(status=recorded.last_skill["status"], reason=recorded.last_skill["reason"])

        def stop(self, reason):
            return SkillResult(status="failed", reason=reason)

    # Replay the map skill's observed results, keeping the real wait, runner, head and conductor.
    monkeypatch.setattr(
        "pilot.skills.make_skill",
        lambda call, **kwargs: (
            RecordedWaypoint() if call.name == "set_waypoint" else make_skill(call, **kwargs)
        ),
    )
    delivery = Delivery()
    now = [rows[0].time]
    conductor = Conductor(
        tmp_path / "session",
        head=MissionHead(goal_seed=7, task="mission-drive"),
        detector=NoEvents(),
        submit=delivery,
        notebook=tmp_path / "notebook.txt",
        clock=lambda: now[0],
    )
    try:
        for _ in range(3):
            conductor.tick(observation(rows[0]), RGB)
        old_deadline = conductor.goal["deadline"]
        for value in rows[1:]:
            now[0] = value.time
            for _ in range(3):
                assert conductor.tick(observation(value), RGB).pad == NEUTRAL_PAD
        responses = [future.result() for future, _, _ in delivery.jobs]
        assert sum("set_waypoint" in plans(answer) for answer in responses) <= 2
        assert responses[-1].step == "failed"
        assert conductor.goal is None
        calls = len(delivery.jobs)
        # Reuse the final recorded map state on a later clock to exercise terminal expiry only.
        later = shifted(rows[-1], old_deadline + 1 - rows[-1].time)
        now[0] = later.time
        for _ in range(4):
            assert conductor.tick(observation(later), RGB).pad == NEUTRAL_PAD
        assert len(delivery.jobs) <= calls + 1
        assert all(plans(future.result()) == ["wait"] for future, _, _ in delivery.jobs[calls:])
        log = [json.loads(line) for line in (tmp_path / "session/head.jsonl").read_text().splitlines()]
        assert not any(row.get("type") == "goal_end" and row.get("reason") == "limit" for row in log)
    finally:
        conductor.close()


def test_human_takeover_discards_the_delayed_quiet_answer_and_releases_input(tmp_path):
    """Only the takeover and its timing are injected; the journey observations are recorded."""
    conductor, delivery, now, first, quiet, _ = recorded_drive(tmp_path, deferred=True)
    try:
        conductor.tick(observation(first), RGB)
        future, function, args = delivery.jobs[-1]
        future.set_result(function(*args))
        for _ in range(2):
            conductor.tick(observation(first), RGB)
        now[0] = quiet.time
        conductor.tick(observation(quiet), RGB)
        future, function, args = delivery.jobs[-1]
        delayed = function(*args)
        conductor.refuse(quiet.time + 0.01, True)
        future.set_result(delayed)
        now[0] += 0.02
        held = replace(observation(quiet), time=now[0])
        assert conductor.tick(held, RGB).pad == NEUTRAL_PAD
        assert not conductor.runner.has_plan
        assert conductor.goal is None
        # Returning control supplies no new seat confirmation and cannot resurrect the old queue.
        conductor.refuse(now[0] + 0.01, False)
        now[0] += 0.02
        assert conductor.tick(replace(held, time=now[0]), RGB).pad == NEUTRAL_PAD
        assert not conductor.runner.has_plan
    finally:
        conductor.close()
