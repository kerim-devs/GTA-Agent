"""P13: continuous planning without weakening pad release and invalidation."""

import json
from concurrent.futures import Future
from dataclasses import replace
from typing import ClassVar

import numpy as np
import pytest

from pilot.conductor import Conductor
from pilot.contract import NEUTRAL_PAD, Detection, Hud, Pad, Reading
from pilot.head import HeadRequest, build_prompt, parse_response, response_schema
from pilot.skills import REGISTRY, Observation, SkillResult, SkillRunner

RGB = np.zeros((720, 1280, 3), dtype=np.uint8)
FLAT = Reading("flat", None, None, None, None, False, 1)


class NoEvents:
    def update(self, *args, **kwargs):
        return []


class Pending:
    def __init__(self):
        self.jobs = []

    def __call__(self, fn, request):
        future = Future()
        self.jobs.append((future, request))
        return future


def response(*steps):
    return parse_response(
        {"plan": [{"name": name, "args": args} for name, args in steps], "sentence": "Weiter."}
    )


def setup(tmp_path, reading=FLAT):
    pending = Pending()
    now = [0.0]
    conductor = Conductor(tmp_path, submit=pending, detector=NoEvents(), clock=lambda: now[0])

    def tick(t, **kwargs):
        now[0] = t
        return conductor.tick(Observation(reading, True, t, **kwargs), RGB)

    tick(0)
    return conductor, pending, tick


def test_a_failed_skill_throws_the_ask_ahead_answer_away(tmp_path):
    conductor, pending, tick = setup(tmp_path)
    try:
        pending.jobs[0][0].set_result(response(("face", {"color": "blue", "duration": 4})))
        tick(1)  # four seconds are less than the head needs, so it is asked ahead at once
        assert len(pending.jobs) == 2 and pending.jobs[1][1].events[0]["kind"] == "plan_ending"
        tick(1.1)
        tick(3.5)  # no blue blip for two seconds: the skill fails
        pending.jobs[1][0].set_result(response(("walk", {"y": -1, "duration": 5})))
        assert tick(3.6).pad == NEUTRAL_PAD
        assert not conductor.runner.has_plan
        assert "skill_failed" in [event["kind"] for event in pending.jobs[2][1].events]
    finally:
        conductor.close()


def test_ahead_appends_preserves_rest_and_survives_plan_end(tmp_path):
    conductor, pending, tick = setup(tmp_path)
    try:
        pending.jobs[0][0].set_result(response(("walk", {"y": -1, "duration": 10})))
        tick(9)
        tick(9.1)
        tick(10.2)
        assert len(pending.jobs) == 2
        event = pending.jobs[1][1].events[0]
        assert event["kind"] == "plan_ending"
        assert event["steps"][0]["name"] == "walk"
        assert 0 < event["remaining_seconds"] < 9
        # Arrival before plan end appends without releasing or replacing active walking.
        pending.jobs[1][0].set_result(response(("look", {"angle": 45, "duration": 2})))
        assert tick(11).pad.left == (0, -1)
        assert conductor.runner.active.name == "walk"
        assert conductor.runner.queue[0].name == "look"
        tick(18)
        assert len(pending.jobs) == 3
        tick(19.2)
        tick(19.3)
        tick(21.4)
        assert conductor.future is pending.jobs[2][0]
        pending.jobs[2][0].set_result(response(("walk", {"y": -0.5, "duration": 10})))
        assert tick(22).pad.left == (0, -0.5)
        rows = [json.loads(line) for line in (tmp_path / "head.jsonl").read_text().splitlines()]
        answers = [row for row in rows if row["type"] == "response"]
        assert [row["disposition"] for row in answers] == ["replaced", "appended", "appended"]
        assert not any(row["overtaken"] for row in answers)
    finally:
        conductor.close()


@pytest.mark.parametrize(
    "name,reading,carry",
    [
        ("walk", FLAT, True),
        ("walk", replace(FLAT, minimap="tilted"), False),
        ("look", FLAT, False),
        ("drive_route", replace(FLAT, minimap="tilted"), False),
    ],
)
def test_carry_is_bounded_walking_only_and_releases(tmp_path, name, reading, carry):
    conductor, pending, tick = setup(tmp_path, reading)
    try:
        args = {"duration": 0.5}
        if name == "walk":
            args.update(y=-1, sprint=True)
        pending.jobs[0][0].set_result(response((name, args)))
        tick(9)
        tick(9.1)
        result = tick(9.7)
        assert len(pending.jobs) == 2
        if carry:
            assert result.pad == Pad(left=(0, -0.45))
            assert tick(13.69).pad.buttons == ()
            assert tick(13.7).pad == NEUTRAL_PAD
            assert tick(15).pad == NEUTRAL_PAD
        else:
            assert result.pad == NEUTRAL_PAD
    finally:
        conductor.close()
    assert not conductor.runner.has_plan


def test_no_carry_on_while_a_menu_is_on_screen(tmp_path):
    conductor, pending, tick = setup(tmp_path)
    try:
        pending.jobs[0][0].set_result(response(("walk", {"duration": 0.5, "y": -1})))
        menu = Hud(screen="pause")
        tick(9, hud=menu)
        tick(9.1, hud=menu)
        assert tick(9.7, hud=menu).pad == NEUTRAL_PAD
        assert tick(10, hud=menu).pad == NEUTRAL_PAD
    finally:
        conductor.close()


def test_a_carry_is_logged_once(tmp_path):
    conductor, pending, tick = setup(tmp_path)
    try:
        pending.jobs[0][0].set_result(response(("walk", {"duration": 0.5, "y": -1})))
        for t in (9, 9.1, 9.7, 9.8, 9.9, 10.0):
            tick(t)
    finally:
        conductor.close()
    rows = [json.loads(line) for line in (tmp_path / "head.jsonl").read_text().splitlines()]
    assert [row["type"] for row in rows].count("carry_on") == 1


def test_scene_invalidates_ahead_and_failed_skill_requests_immediately(tmp_path):
    conductor, pending, tick = setup(tmp_path)
    try:
        pending.jobs[0][0].set_result(response(("walk", {"duration": 10, "y": -1})))
        tick(9)
        tick(9.1)
        tick(11)
        conductor.tick(Observation(FLAT, True, 12), RGB, events=[{"kind": "changed"}])
        pending.jobs[1][0].set_result(response(("shoot", {})))
        tick(13)
        assert conductor.runner.active.name == "walk"
        assert len(pending.jobs) == 3
        pending.jobs[2][0].set_result(response(("walk_to", {"color": "red", "duration": 10})))
        tick(14)
        tick(14.1)
        tick(16.2)
        assert pending.jobs[-1][1].events[-1]["kind"] == "skill_failed"
    finally:
        conductor.close()


def test_hud_events_debounce_and_observation_payload(tmp_path):
    conductor, pending, tick = setup(tmp_path)
    try:
        conductor.last_hud = Hud(wanted=0)
        tick(0.1, hud=Hud(wanted=1))
        tick(0.4, hud=Hud(wanted=2))
        tick(0.8, hud=Hud(wanted=2))
        assert not conductor.pending
        tick(0.91, hud=Hud(wanted=2, health=0.2, screen="pause"))
        assert {event["kind"] for event in conductor.pending} == {
            "wanted_changed",
            "screen_changed",
        }
        pending.jobs[0][0].set_result(response(("wait", {})))
        detections = tuple(Detection("person", (0, 0, 1, 1), 0.8) for _ in range(20))
        tick(1.5, hud=Hud(wanted=2, health=0.2, screen="pause"), objects=detections)
        request = pending.jobs[1][1]
        assert {event["kind"] for event in request.events} == {
            "wanted_changed",
            "low_health",
            "screen_changed",
        }
        assert request.hud["screen"] == "pause"
        assert len(request.objects) == 12
    finally:
        conductor.close()


def test_registry_drives_schema_prompt_and_runner(monkeypatch):
    class Nod:
        name = "nod"
        parameters: ClassVar[dict] = {"duration": (0.1, 1, 0.5), "direction": ("left", "right")}
        prompt = "Nod toward the selected side for a bounded time."

        def __init__(self, args):
            self.limit = min(1, max(0.1, args.get("duration", 0.5)))
            self.started = None
            self.finished = None

        def step(self, observation):
            if self.started is None:
                self.started = observation.time
            return (
                SkillResult(Pad(right=(0.2, 0)))
                if observation.time - self.started < self.limit
                else SkillResult(status="done")
            )

        def stop(self, reason):
            return SkillResult(status="failed", reason=reason)

    monkeypatch.setitem(REGISTRY, "nod", Nod)
    schema = response_schema()
    variant = next(
        item
        for item in schema["properties"]["plan"]["items"]["anyOf"]
        if item["properties"]["name"]["enum"] == ["nod"]
    )
    assert variant["properties"]["args"]["properties"]["duration"]["maximum"] == 1
    request = HeadRequest([], "", "", "", "", {}, None, "", "unused.jpg")
    assert Nod.prompt in build_prompt(request)
    calls = response(("nod", {"direction": "right"})).plan
    runner = SkillRunner()
    runner.replace(calls)
    runner.tick(Observation(FLAT, True, 0))
    assert runner.tick(Observation(FLAT, True, 0.1)).pad.right == (0.2, 0)
    assert runner.tick(Observation(FLAT, True, 0.7)).pad == NEUTRAL_PAD


def test_carry_releases_on_corrupt_frame_and_new_answer(tmp_path):
    conductor, pending, tick = setup(tmp_path)
    try:
        pending.jobs[0][0].set_result(response(("walk", {"duration": 0.5, "y": -1})))
        tick(9)
        tick(9.1)
        assert tick(9.7).pad != NEUTRAL_PAD
        pending.jobs[1][0].set_result(response(("walk", {"duration": 10, "y": -1})))
        assert tick(10).pad == NEUTRAL_PAD
        assert tick(10.1).pad != NEUTRAL_PAD
    finally:
        conductor.close()

    conductor, pending, tick = setup(tmp_path / "corrupt")
    try:
        pending.jobs[0][0].set_result(response(("walk", {"duration": 0.5, "y": -1})))
        tick(9)
        tick(9.1)
        assert tick(9.7).pad != NEUTRAL_PAD
        assert conductor.tick(Observation(replace(FLAT, corrupt=True), True, 10), RGB).pad == NEUTRAL_PAD
        assert tick(10.1).pad == NEUTRAL_PAD
    finally:
        conductor.close()


def test_walk_to_carries_only_after_observed_arrival(tmp_path):
    from pilot.contract import Blip

    reading = replace(FLAT, blips=(Blip("yellow", 0, 2),))
    conductor, pending, tick = setup(tmp_path, reading)
    try:
        pending.jobs[0][0].set_result(response(("walk_to", {"color": "yellow", "duration": 10})))
        tick(9)
        assert tick(9.1).pad == Pad(left=(0, -0.45))
        assert conductor.runner.describe()["reason"] == "arrived"
        assert tick(13.1).pad == NEUTRAL_PAD
    finally:
        conductor.close()

    conductor, pending, tick = setup(tmp_path / "failed")
    try:
        pending.jobs[0][0].set_result(response(("walk_to", {"color": "yellow", "duration": 0.5})))
        tick(9)
        tick(9.1)
        assert tick(9.7).pad == NEUTRAL_PAD
        assert conductor.runner.describe()["status"] == "failed"
        assert not conductor.carry_allowed
    finally:
        conductor.close()
