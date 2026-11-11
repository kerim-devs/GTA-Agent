"""Screen ownership, recovery and stale answers through the real conductor."""

import json
from concurrent.futures import Future

import cv2
import numpy as np
import pytest

from pilot.conductor import Conductor
from pilot.contract import NEUTRAL_PAD, Hud, Reading
from pilot.flow import Flow
from pilot.head import parse_response, response_schema
from pilot.scene import SceneText
from pilot.skills import REGISTRY, Observation, RegisteredSkill, SkillResult, SkillRunner
from pilot.waypoint import SetWaypoint
from tools.sim_flow import simulate_conductor

RGB = np.zeros((720, 1280, 3), dtype=np.uint8)
FLAT = Reading("flat", None, None, None, None, False, 1)


class NoEvents:
    def update(self, *args, **kwargs):
        return []


class Pending:
    def __init__(self):
        self.jobs = []

    def __call__(self, function, *args):
        future = Future()
        self.jobs.append((future, function, args))
        return future


def walk_plan():
    return parse_response(
        {"plan": [{"name": "walk", "args": {"y": -0.6, "duration": 30}}], "sentence": "Weiter."}
    )


@pytest.fixture
def session(tmp_path):
    pending = Pending()
    conductor = Conductor(
        tmp_path, flow=Flow(), detector=NoEvents(), submit=pending, notebook=tmp_path / "notebook.txt"
    )
    conductor.pending.clear()
    conductor.last_request_time = 0
    conductor.head_latency = 0
    yield conductor, pending
    conductor.close()


def tick(conductor, t, screen="game", **kwargs):
    return conductor.tick(Observation(FLAT, True, t, hud=Hud(screen=screen)), RGB, **kwargs)


def rows(conductor, kind):
    return [
        row
        for line in (conductor.directory / "head.jsonl").read_text().splitlines()
        if (row := json.loads(line))["type"] == kind
    ]


@pytest.mark.parametrize(
    "screen,event,button", [("failed", "failure", "cross"), ("pause", "menu_closed", "circle")]
)
@pytest.mark.parametrize("read_delay", [0, 2, 4])
def test_button_machine_recovers_once(tmp_path, screen, event, button, read_delay):
    report = simulate_conductor(tmp_path, screen, read_delay=read_delay)
    assert [press["buttons"] for press in report["presses"]] == [[button]]
    assert len(report["requests"]) == 1
    request = report["requests"][0]
    assert request["request"]["hud"]["screen"] == "game"
    assert [item["kind"] for item in request["request"]["events"]] == [event]
    assert request["request"]["events"][0]["seconds"] >= 0.14
    if event == "failure":
        assert request["request"]["events"][0]["count"] == 1
    else:
        assert request["request"]["events"][0]["seconds"] >= 0.14
    assert [row["type"] for row in report["flow"]] == ["flow_enter", "flow_exit"]
    takeover = [row for row in report["trace"] if row["skill"] and row["skill"]["name"] == "flow"]
    assert takeover
    assert all(row["pad"]["left"] == [0.0, 0.0] or row["pad"]["left"] == (0.0, 0.0) for row in takeover)
    assert all(row["pad"]["right"] == (0.0, 0.0) for row in takeover)
    assert request["t"] == report["flow"][-1]["t"]


def test_takeover_stops_once_never_ticks_runner_or_carries(session, monkeypatch):
    conductor, _ = session
    conductor.runner.replace(walk_plan().plan)
    tick(conductor, 0)
    assert tick(conductor, 0.1).pad != NEUTRAL_PAD
    skill = conductor.runner.active
    stopped = []
    original_stop = skill.stop
    monkeypatch.setattr(skill, "stop", lambda reason: (stopped.append(reason), original_stop(reason))[1])
    monkeypatch.setattr(conductor.runner, "tick", lambda *_: pytest.fail("runner ticked during flow"))
    conductor.carry_allowed, conductor.carry_started = True, 0.1
    # The first reading of a screen costs one neutral tick and nothing else.
    result = tick(conductor, 0.2, "pause")
    assert result.pad == NEUTRAL_PAD and result.reason == "flow"
    assert stopped == [] and conductor.runner.has_plan and not rows(conductor, "flow_enter")
    for t in (0.25, 0.3, 0.4):
        result = tick(conductor, t, "pause")
        assert result.pad.left == (0, 0) and result.pad.right == (0, 0)
        assert result.reason == "flow"
        assert not conductor.carry_allowed
    assert stopped == ["flow"]
    assert not conductor.runner.has_plan
    assert len(rows(conductor, "flow_enter")) == 1


def test_head_answer_arriving_on_takeover_is_discarded(session):
    conductor, pending = session
    conductor.pending.append({"kind": "test"})
    tick(conductor, 0)
    pending.jobs[0][0].set_result(walk_plan())
    assert tick(conductor, 0.1, "pause").pad == NEUTRAL_PAD
    tick(conductor, 0.15, "pause")
    response = rows(conductor, "response")[0]
    assert response["disposition"] == "discarded" and not response["applied"]
    assert not conductor.runner.has_plan


def test_recovery_does_not_wait_for_obsolete_head(session):
    conductor, pending = session
    conductor.pending.append({"kind": "test"})
    tick(conductor, 0)
    tick(conductor, 0.1, "pause")
    tick(conductor, 0.2, "pause")
    tick(conductor, 0.4)
    tick(conductor, 0.5)
    tick(conductor, 0.75)
    assert len(pending.jobs) == 2
    assert rows(conductor, "request")[-1]["t"] == 0.75
    assert pending.jobs[0][0].cancelled()


def test_transient_game_read_does_not_split_takeover(session):
    conductor, pending = session
    assert tick(conductor, 0, "phone").reason == "flow"
    assert tick(conductor, 0.05).reason == "flow"
    result = conductor.tick(Observation(FLAT, True, 0.1), RGB)
    assert result.reason == "flow" and result.pad == NEUTRAL_PAD
    assert tick(conductor, 0.15, "phone").reason == "flow"
    assert tick(conductor, 0.2, "phone").pad.buttons == ("circle",)
    assert tick(conductor, 0.4).reason == "flow"
    assert tick(conductor, 0.45).reason == "flow"
    assert not pending.jobs
    tick(conductor, 0.75)
    assert len(pending.jobs) == 1
    assert len(rows(conductor, "flow_enter")) == 1
    assert len(rows(conductor, "flow_exit")) == 1


def press_plan():
    return parse_response(
        {"plan": [{"name": "press", "args": {"button": "cross", "duration": 0.2}}], "sentence": "Ich drücke."}
    )


def test_a_stuck_screen_is_handed_to_the_head_and_taken_back_when_it_changes(session):
    conductor, pending = session
    conductor.flow = Flow(response_timeout=0.2, wait_timeout=0.3)
    tick(conductor, 0, "pause")
    assert tick(conductor, 0.05, "pause").pad.buttons == ("circle",)
    assert tick(conductor, 0.3, "pause").pad.buttons == ("circle",)
    assert not pending.jobs
    assert tick(conductor, 0.55, "pause").pad == NEUTRAL_PAD
    assert len(pending.jobs) == 1
    event = rows(conductor, "request")[0]["request"]["events"][0]
    assert event["kind"] == "stuck"
    # Until the head answers, nothing is pressed.
    assert tick(conductor, 0.6, "pause").pad == NEUTRAL_PAD
    pending.jobs[0][0].set_result(press_plan())
    pads = [tick(conductor, t, "pause").pad for t in (0.65, 0.68, 0.71, 0.75)]
    assert any(pad.buttons == ("cross",) for pad in pads)
    assert rows(conductor, "response")[-1]["applied"]
    # Another screen is the reflex's again, and what is left of the head's plan is dropped.
    conductor.runner.replace(walk_plan().plan)
    tick(conductor, 0.8, "pause")
    assert tick(conductor, 0.9, "map").reason == "flow"
    assert tick(conductor, 0.95, "map").reason == "flow"
    assert not conductor.runner.has_plan
    assert len(rows(conductor, "flow_enter")) == 1


def test_the_heads_plan_for_a_stuck_screen_ends_when_the_game_is_back(session):
    conductor, pending = session
    conductor.flow = Flow(response_timeout=0.2, wait_timeout=0.3)
    for t in (0, 0.05, 0.3, 0.55):
        tick(conductor, t, "pause")
    pending.jobs[0][0].set_result(walk_plan())
    tick(conductor, 0.6, "pause")
    assert conductor.runner.has_plan
    for t in (0.7, 0.75, 1.1):
        tick(conductor, t)
    assert not conductor.runner.has_plan
    assert [row["type"] for row in rows(conductor, "flow_exit")] == ["flow_exit"]
    assert rows(conductor, "request")[-1]["request"]["events"][0]["kind"] == "menu_closed"


NEW_SKILLS = {
    "enter_vehicle": {"duration": 25, "kind": "any"},
    "fight": {"duration": 30, "cover": "no"},
    "melee": {"duration": 10, "cover": "no"},
    "punch": {"duration": 15, "hits": 3},
}


@pytest.mark.parametrize("name", NEW_SKILLS)
def test_a_plan_from_the_head_starts_and_stops_every_new_skill(name):
    args = NEW_SKILLS[name]
    plan = parse_response({"plan": [{"name": name, "args": args}], "sentence": "Los."}).plan
    runner = SkillRunner()
    runner.replace(plan)
    assert runner.tick(Observation(FLAT, True, 0)).pad == NEUTRAL_PAD
    assert runner.tick(Observation(FLAT, True, 0.1)).status == "running"
    assert runner.active.name == name
    assert runner.remaining(0.1) == args["duration"]
    runner.stop("flow")
    assert runner.last == {"name": name, "status": "failed", "reason": "flow"}


def test_the_head_can_only_ask_for_whole_punches():
    variants = {
        v["properties"]["name"]["enum"][0]: v
        for v in response_schema()["properties"]["plan"]["items"]["anyOf"]
    }
    assert variants["punch"]["properties"]["args"]["properties"]["hits"]["type"] == "integer"
    with pytest.raises(ValueError, match="hits must be an integer"):
        parse_response(
            {"plan": [{"name": "punch", "args": {"duration": 15, "hits": 2.5}}], "sentence": "Los."}
        )


def test_waypoint_owns_both_menus_and_expectation_ends_with_skill(session):
    conductor, _ = session
    assert RegisteredSkill.opens == ()
    assert REGISTRY["set_waypoint"] is SetWaypoint
    skill = SetWaypoint({"target": "mission", "duration": 5})
    conductor.runner.queue.append(skill)
    tick(conductor, 0)
    assert conductor.runner.active is skill
    tick(conductor, 0.1, "pause")
    tick(conductor, 0.2, "map")
    assert not rows(conductor, "flow_enter")
    assert conductor.runner.active is skill
    conductor.runner.stop("cancelled")
    assert tick(conductor, 0.3, "map").reason == "flow"
    assert tick(conductor, 0.4, "map").pad.buttons == ("circle",)


def test_expect_accepts_several_screens_and_expires():
    flow = Flow()
    flow.expect("pause", "map", until=1)
    for t, screen in ((0, "pause"), (0.1, "map")):
        assert flow.tick(Observation(FLAT, True, t, hud=Hud(screen=screen))) is None
    assert flow.tick(Observation(FLAT, True, 1, hud=Hud(screen="map"))) is not None


def test_expectation_ends_on_early_skill_completion(session, monkeypatch):
    conductor, _ = session
    skill = SetWaypoint({"target": "mission", "duration": 45})
    conductor.runner.queue.append(skill)
    tick(conductor, 0)
    monkeypatch.setattr(skill, "step", lambda observation: SkillResult(status="done"))
    assert tick(conductor, 0.1, "map").reason != "flow"
    assert conductor.runner.active is None
    assert tick(conductor, 0.2, "map").reason == "flow"
    assert tick(conductor, 0.3, "map").pad.buttons == ("circle",)


def test_old_and_future_injected_text_never_presses_retry(session):
    conductor, _ = session
    for t in (2, 2.1):
        assert tick(conductor, t, "failed", text=SceneText(help="Retry X"), text_time=0).pad == NEUTRAL_PAD
    assert tick(conductor, 2.2, "failed", text=SceneText(help="Retry X"), text_time=5).pad == NEUTRAL_PAD
    assert tick(conductor, 2.3, "failed", text=SceneText(help="Retry X")).pad == NEUTRAL_PAD
    assert tick(conductor, 2.4, "failed").pad.buttons == ("cross",)


def test_background_text_uses_capture_not_completion_time(session):
    conductor, pending = session
    conductor.ocr = True
    tick(conductor, 0, frame_time=-0.2)
    pending.jobs[0][0].set_result(SceneText(help="Retry X"))
    assert tick(conductor, 2, "failed").pad == NEUTRAL_PAD
    assert conductor.text_time == -0.2
    assert tick(conductor, 2.1, "failed").pad == NEUTRAL_PAD


def test_low_health_needs_continuous_half_second(session):
    conductor, _ = session

    def health(t, value):
        return conductor._hud_events(Observation(FLAT, True, t, hud=Hud(health=value)))

    assert health(0, 0.2) == []
    assert health(0.49, 0.2) == []
    assert health(0.5, 0.8) == []
    assert health(0.6, 0.2) == []
    assert health(1.09, 0.2) == []
    assert health(1.1, 0.2) == [{"kind": "low_health", "health": 0.2}]
    assert health(2, 0.2) == []
    health(2.1, 0.8)
    health(2.2, 0.2)
    assert health(2.7, 0.2) == [{"kind": "low_health", "health": 0.2}]


def test_without_flow_preserves_runner_and_screen_events(tmp_path):
    conductor = Conductor(tmp_path, detector=NoEvents(), submit=Pending())
    try:
        conductor.runner.replace(walk_plan().plan)
        tick(conductor, 0)
        result = tick(conductor, 0.1, "pause")
        assert result.pad != NEUTRAL_PAD
        assert conductor.runner.has_plan
        assert {"kind": "screen_changed", "screen": "pause"} in conductor.pending
        assert not rows(conductor, "flow_enter")
    finally:
        conductor.close()


@pytest.mark.parametrize("disabled", [False, True])
def test_cli_attaches_reader_and_flow(monkeypatch, disabled):
    from pilot import cli

    class Bridge:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    calls = []
    monkeypatch.setattr(cli, "Bridge", Bridge)
    monkeypatch.setattr(cli, "Pipeline", lambda **kwargs: None)
    monkeypatch.setattr(cli, "ObjectReader", lambda: "detector")
    monkeypatch.setattr(cli, "run_play", lambda *args, **kwargs: calls.append(kwargs))
    off = ["--no-hud-flow", "--no-objects"] if disabled else []
    cli.main(["play", "--no-record", "--no-ocr", *off])
    assert (calls[0]["hud"] is None) is disabled
    assert (calls[0]["flow"] is None) is disabled
    assert calls[0]["objects"] == (None if disabled else "detector")


def test_cli_plays_without_the_detector_when_its_weights_are_missing(monkeypatch, capsys):
    from pilot import cli

    class Bridge:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def missing():
        raise RuntimeError("YOLOX weights missing or corrupt")

    calls = []
    monkeypatch.setattr(cli, "Bridge", Bridge)
    monkeypatch.setattr(cli, "Pipeline", lambda **kwargs: None)
    monkeypatch.setattr(cli, "ObjectReader", missing)
    monkeypatch.setattr(cli, "run_play", lambda *args, **kwargs: calls.append(kwargs))
    cli.main(["play", "--no-record", "--no-ocr"])
    assert calls[0]["objects"] is None
    assert "object detector off: YOLOX weights missing" in capsys.readouterr().err


def test_replay_hud_once_per_frame_and_text_capture_clock(tmp_path, monkeypatch):
    from tools import conductor_replay

    recording, output = tmp_path / "recording", tmp_path / "output"
    recording.mkdir()
    writer = cv2.VideoWriter(str(recording / "video.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 4, (1280, 720))
    assert writer.isOpened()
    for _ in range(5):
        writer.write(RGB)
    writer.release()
    (recording / "frames.jsonl").write_text(
        "".join(json.dumps({"i": i, "frame_id": i, "t": i / 4}) + "\n" for i in range(5))
    )
    text_calls, hud_calls = [], []

    class Reader:
        def read(self, rgb):
            text_calls.append(rgb.shape)
            return SceneText(objective=str(len(text_calls)))

    def read_hud(rgb, text):
        hud_calls.append(text.objective)
        return Hud(screen="game", health=1)

    monkeypatch.setattr(conductor_replay.hud, "read", read_hud)
    report = conductor_replay.run_offline(recording, output, hud_flow=True, text_reader=Reader())
    assert report["frames"] == 5 and report["takeovers"] == 0
    assert len(text_calls) == 3
    assert hud_calls == ["1", "1", "2", "2", "3"]
    play = [json.loads(line) for line in (output / "play.jsonl").read_text().splitlines()]
    assert [row["text_time"] for row in play] == [0, 0, 0.5, 0.5, 1]
    assert (output / "flow.json").exists()


def test_replay_cli_forwards_hud_flow(monkeypatch, tmp_path):
    from tools import conductor_replay

    calls = []
    monkeypatch.setattr(conductor_replay, "run_offline", lambda *args, **kwargs: calls.append(kwargs))
    monkeypatch.setattr(
        "sys.argv", ["conductor_replay", str(tmp_path), "--out", str(tmp_path / "out"), "--hud-flow"]
    )
    conductor_replay.main()
    assert calls[0]["hud_flow"] is True


def test_live_hud_reads_only_fresh_frames_and_logs_flow(tmp_path):
    from test_conductor import Clock, FakeBridge, FakePipeline

    from pilot.conductor import run_play

    clock = Clock()
    bridge = FakeBridge(tmp_path / "recording", clock, freeze=True)
    calls = []

    class HudSource:
        def read(self, rgb, text):
            calls.append(rgb.shape)
            return Hud(screen="pause")

    run_play(
        bridge,
        seconds=0.2,
        pipeline=FakePipeline(),
        head=None,
        notebook=tmp_path / "notebook.txt",
        ocr=False,
        flow=Flow(),
        hud=HudSource(),
        clock=clock,
        sleep=clock.sleep,
    )
    assert len(calls) == 5
    play = [json.loads(line) for line in (bridge.path / "play.jsonl").read_text().splitlines()]
    assert len(calls) == sum(row["fresh"] for row in play) < len(play)
    assert all(row["skill"]["name"] == "flow" for row in play if row["fresh"])
    assert any(row["skill"]["action"] == "back" for row in play if row["fresh"])


def test_one_odd_reading_costs_one_neutral_tick_and_keeps_the_plan(session):
    conductor, pending = session
    conductor.runner.replace(walk_plan().plan)
    tick(conductor, 0)
    assert tick(conductor, 0.1).pad != NEUTRAL_PAD
    skill = conductor.runner.active
    # As at t=153.59 of recording 093238: one reading of a phone, then the game again.
    assert tick(conductor, 0.13, "phone").pad == NEUTRAL_PAD
    for t in (0.16, 0.2):
        tick(conductor, t)
    assert tick(conductor, 0.23).pad != NEUTRAL_PAD
    assert conductor.runner.active is skill
    assert not rows(conductor, "flow_enter") and not pending.jobs
