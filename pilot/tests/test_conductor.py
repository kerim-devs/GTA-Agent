import json
import sys
import threading
from concurrent.futures import Future

import httpx
import numpy as np
import pytest

from pilot.bridge import Bridge, Frame
from pilot.conductor import Conductor, background, run_play
from pilot.contract import NEUTRAL_PAD, Command, Hud, Pad, Reading, SkillResult
from pilot.head import CodexHead, HeadRequest, ScriptedHead, SkillCall, parse_response
from pilot.scene import SceneEvent
from pilot.skills import Observation, Skill, SkillRunner

RGB = np.zeros((720, 1280, 3), dtype=np.uint8)
READING = Reading("tilted", "purple", 0.0, 0.0, 0.0, False, 1.0)


def observation(t):
    return Observation(READING, True, t)


def reply(*names, lesson=None):
    return {
        "plan": [
            {"name": name, "args": {"duration": 0.1, **({"button": "cross"} if name == "press" else {})}}
            for name in names
        ],
        "sentence": "Ich mache weiter.",
        "lesson": lesson,
    }


class NoEvents:
    def update(self, *args, **kwargs):
        return ()


class Pending:
    def __init__(self):
        self.jobs = []

    def __call__(self, function, *args):
        future = Future()
        self.jobs.append((future, function, args))
        return future


def rows(path):
    return [json.loads(line) for line in (path / "head.jsonl").read_text().splitlines()]


def test_event_one_request_and_sequential_plan(tmp_path):
    pending = Pending()
    conductor = Conductor(tmp_path, submit=pending, detector=NoEvents())
    try:
        conductor.tick(observation(0), RGB, events=[{"kind": "objective_changed"}])
        assert len(pending.jobs) == 1
        pending.jobs[0][0].set_result(parse_response(reply("walk", "look", "press")))
        assert conductor.tick(observation(0.01), RGB).pad == NEUTRAL_PAD
        seen = []
        for t in (0.02, 0.13, 0.14, 0.25, 0.26, 0.3):
            conductor.tick(observation(t), RGB)
            if conductor.runner.active:
                seen.append(conductor.runner.active.name)
        assert seen == ["walk", "look", "press", "press"]
        assert len(pending.jobs) == 2
        assert pending.jobs[1][2][0].events[0]["kind"] == "plan_ending"
        assert rows(tmp_path)[1]["applied"] is True
        assert (tmp_path / "head-0001.jpg").exists()
        assert "objective_changed" in (tmp_path / "head-0001.prompt.txt").read_text()
    finally:
        conductor.close()


@pytest.mark.parametrize("name", ["walk_to", "face"])
def test_appended_plan_survives_plain_time_limit(tmp_path, name):
    pending = Pending()
    now = [0.0]
    conductor = Conductor(tmp_path, submit=pending, detector=NoEvents(), clock=lambda: now[0])

    def tick(t):
        now[0] = t
        return conductor.tick(observation(t), RGB)

    try:
        tick(0)
        pending.jobs[0][0].set_result(
            parse_response(
                {
                    "plan": [{"name": name, "args": {"color": "blue", "duration": 0.5}}],
                    "sentence": "Continue.",
                }
            )
        )
        tick(0.01)
        assert pending.jobs[1][2][0].events[0]["kind"] == "plan_ending"
        tick(0.02)
        pending.jobs[1][0].set_result(
            parse_response(
                {
                    "plan": [
                        {"name": "enter_vehicle", "args": {"duration": 25}},
                        {"name": "drive_route", "args": {"duration": 60}},
                    ],
                    "sentence": "Enter the car.",
                }
            )
        )
        tick(0.1)
        result = tick(0.52)
        assert (result.status, result.reason, result.pad) == ("done", "time-limit", NEUTRAL_PAD)
        assert conductor.describe(result)["queue_disposition"] == "kept"
        assert conductor.describe(result)["queue"] == ["enter_vehicle", "drive_route"]
        assert conductor.runner.active is None
        tick(0.53)
        assert conductor.runner.active.name == "enter_vehicle"
        assert len(pending.jobs) == 2
        assert rows(tmp_path)[-1]["disposition"] == "appended"
    finally:
        conductor.close()


def test_appended_plan_is_cleared_by_target_loss(tmp_path):
    pending = Pending()
    conductor = Conductor(tmp_path, submit=pending, detector=NoEvents())
    try:
        conductor.tick(observation(0), RGB)
        pending.jobs[0][0].set_result(
            parse_response(
                {
                    "plan": [{"name": "face", "args": {"color": "blue", "duration": 4}}],
                    "sentence": "Face the target.",
                }
            )
        )
        conductor.tick(observation(0.01), RGB)
        conductor.tick(observation(0.02), RGB)
        pending.jobs[1][0].set_result(
            parse_response(
                {
                    "plan": [{"name": "enter_vehicle", "args": {"duration": 25}}],
                    "sentence": "Enter the car.",
                }
            )
        )
        conductor.tick(observation(0.1), RGB)
        epoch = conductor.epoch
        result = conductor.tick(observation(2.03), RGB)
        assert (result.status, result.reason) == ("failed", "blip-gone")
        assert conductor.describe(result)["queue_disposition"] == "cleared"
        assert conductor.describe(result)["dropped"] == ["enter_vehicle"]
        assert not conductor.runner.has_plan
        assert conductor.epoch == epoch + 1
        assert pending.jobs[2][2][0].events[0]["kind"] == "skill_failed"
    finally:
        conductor.close()


def test_replacement_arrives_on_tick_old_target_would_fail(tmp_path):
    pending = Pending()
    runner = SkillRunner()
    runner.replace((SkillCall("face", {"color": "blue", "duration": 4}),))
    conductor = Conductor(tmp_path, runner=runner, submit=pending, detector=NoEvents())
    try:
        conductor.tick(observation(0), RGB)
        conductor.tick(observation(0.01), RGB)
        old = runner.active
        pending.jobs[0][0].set_result(
            parse_response(
                {
                    "plan": [{"name": "walk", "args": {"x": 1, "duration": 10}}],
                    "sentence": "Walk right.",
                }
            )
        )
        epoch = conductor.epoch
        result = conductor.tick(observation(2.02), RGB)
        assert result.pad == NEUTRAL_PAD
        assert old.finished.reason == "replaced"
        assert conductor.describe(result)["reason"] == "replaced"
        assert rows(tmp_path)[-1]["disposition"] == "replaced"
        assert conductor.tick(observation(2.03), RGB).pad.left == (1, 0)
        assert runner.active.name == "walk"
        assert conductor.epoch == epoch
        assert len(pending.jobs) == 1
    finally:
        conductor.close()


def test_slow_head_does_not_block_and_batches_overtaking_events(tmp_path):
    pending = Pending()
    runner = SkillRunner()
    runner.replace((SkillCall("walk", {"x": 1, "duration": 10}),))
    conductor = Conductor(tmp_path, submit=pending, runner=runner, detector=NoEvents())
    try:
        conductor.tick(observation(0), RGB)
        for i in range(1, 100):
            result = conductor.tick(
                observation(i / 100), RGB, events=[{"kind": f"event-{i}"}] if i in (20, 40) else []
            )
            assert result.pad.left == (1, 0)
        assert len(pending.jobs) == 1
        pending.jobs[0][0].set_result(parse_response(reply("shoot", lesson="Must not be stored.")))
        assert conductor.tick(observation(1), RGB).pad.left == (1, 0)
        assert len(pending.jobs) == 2
        assert [event["kind"] for event in pending.jobs[1][2][0].events] == ["event-20", "event-40"]
        logged = rows(tmp_path)[1]
        assert logged["overtaken"] and not logged["applied"]
        assert conductor.runner.active.name == "walk"
    finally:
        conductor.close()


@pytest.mark.parametrize("name", ["drive_route", "wait", "press", "walk", "look", "shoot"])
def test_every_skill_releases_on_end_stop_and_replacement(name):
    args = {"duration": 0.1, **({"button": "cross"} if name == "press" else {})}
    skill = Skill(SkillCall(name, args))
    skill.step(observation(0))
    terminal = skill.step(observation(10))
    assert terminal.status in ("done", "failed") and terminal.pad == NEUTRAL_PAD
    assert skill.stop().pad == NEUTRAL_PAD
    runner = SkillRunner()
    runner.replace((SkillCall(name, args),))
    runner.tick(observation(0))
    runner.tick(observation(0.01))
    assert runner.replace((SkillCall("wait", {}),)) == NEUTRAL_PAD
    assert runner.tick(observation(0.02)).pad == NEUTRAL_PAD
    assert runner.stop() == NEUTRAL_PAD
    assert not runner.queue and runner.active is None


def test_limits_and_driver_failure_release():
    for name in ("press", "shoot"):
        args = {"duration": 1e6, "count": 999, **({"button": "cross"} if name == "press" else {})}
        skill = Skill(SkillCall(name, args))
        assert skill.duration == 1 and skill.count == 5 and skill.limit <= 10
    assert Skill(SkillCall("wait", {"duration": -20})).duration == 0.1
    for name, limit in (("wait", 60), ("walk", 10), ("look", 5), ("drive_route", 120)):
        assert Skill(SkillCall(name, {"duration": 1e9})).limit == limit
    assert Skill(SkillCall("walk", {"x": 100, "y": -100})).step(observation(0)).pad.left == (1, -1)

    class FailingDriver:
        def step(self, *args, **kwargs):
            raise ValueError("broken")

    assert Skill(SkillCall("drive_route", {}), driver=FailingDriver()).step(observation(0)).pad == NEUTRAL_PAD

    class EndDriver:
        def step(self, *args, **kwargs):
            return Command(1, 1, 1, "failed-recovery")

    result = Skill(SkillCall("drive_route", {}), driver=EndDriver()).step(observation(0))
    assert result.pad == NEUTRAL_PAD and result.status == "failed"


@pytest.mark.parametrize(
    "data",
    [
        {"plan": [{"name": "walk", "args": {}}, {"name": "unknown", "args": {}}], "sentence": "Weiter."},
        {"plan": [], "sentence": "Weiter."},
        reply(*(["wait"] * 6)),
        {"plan": [{"name": "press", "args": {"button": "invalid"}}], "sentence": "Weiter."},
        {"plan": [{"name": "wait", "args": {"duration": float("nan")}}], "sentence": "Weiter."},
        {"plan": [{"name": "wait", "args": {"duration": True}}], "sentence": "Weiter."},
        {"plan": [{"name": "walk", "args": {"secret": 1}}], "sentence": "Weiter."},
        {"plan": [{"name": "shoot", "args": {"count": 1.5}}], "sentence": "Weiter."},
    ],
)
def test_reject_entire_invalid_response(data):
    with pytest.raises(ValueError):
        parse_response(data)


def test_bad_head_keeps_existing_skill_and_logs_error(tmp_path):
    pending = Pending()
    runner = SkillRunner()
    runner.replace((SkillCall("walk", {"x": 1}),))
    conductor = Conductor(tmp_path, submit=pending, runner=runner, detector=NoEvents())
    try:
        conductor.tick(observation(0), RGB)
        pending.jobs[0][0].set_exception(ValueError("invalid response"))
        assert conductor.tick(observation(0.1), RGB).pad.left == (1, 0)
        assert "invalid response" in rows(tmp_path)[1]["error"]
        assert not rows(tmp_path)[1]["applied"]
    finally:
        conductor.close()


def test_accepted_lesson_and_quiet_timer(tmp_path):
    pending = Pending()
    notebook = tmp_path / "notes" / "notebook.txt"
    conductor = Conductor(tmp_path, submit=pending, notebook=notebook, detector=NoEvents(), quiet_seconds=60)
    try:
        conductor.tick(observation(0), RGB)
        pending.jobs[0][0].set_result(
            parse_response(
                {
                    "plan": [{"name": "drive_route", "args": {"duration": 120}}],
                    "sentence": "Ich fahre weiter.",
                    "lesson": "Follow the route.",
                }
            )
        )
        conductor.tick(observation(0.1), RGB)
        assert "Follow the route." in notebook.read_text()
        # Quiet timer independent of whether an idle runner has something to do.
        conductor.runner.stop()
        conductor.tick(observation(59), RGB)
        assert len(pending.jobs) == 1
        conductor.tick(observation(60), RGB)
        assert len(pending.jobs) == 2
    finally:
        conductor.close()


def test_text_injection_and_slow_ocr(tmp_path):
    from pilot.scene import SceneText

    pending = Pending()
    conductor = Conductor(tmp_path, submit=pending, detector=NoEvents(), ocr=True, clock=lambda: 0)
    try:
        conductor.tick(observation(0), RGB, text=SceneText(objective="Go to the car"))
        assert len(pending.jobs) == 2  # one OCR job, one head job
        assert pending.jobs[1][2][0].objective == "Go to the car"
        for i in range(1, 100):
            conductor.tick(observation(i / 30), RGB)
        assert len(pending.jobs) == 2
    finally:
        conductor.close()


def test_injected_text_drives_real_event_detector(tmp_path):
    from pilot.scene import SceneText

    pending = Pending()
    conductor = Conductor(tmp_path, submit=pending, notebook=tmp_path / "notes.txt")
    try:
        conductor.tick(observation(0), RGB, text=SceneText(objective="Go to the car"))
        pending.jobs[0][0].set_result(
            parse_response({"plan": [{"name": "wait", "args": {"duration": 60}}], "sentence": "Ich warte."})
        )
        conductor.tick(observation(1.6), RGB, text=SceneText(objective="Go to the car"))
        conductor.tick(observation(3.2), RGB, text=SceneText(objective="Go to the car"))
        conductor.tick(observation(4.8), RGB, text=SceneText(objective="Enter the car"))
        conductor.tick(observation(6.4), RGB, text=SceneText(objective="Enter the car"))
        conductor.tick(observation(8.0), RGB, text=SceneText(objective="Enter the car"))
        assert len(pending.jobs) == 2
        request = pending.jobs[-1][2][0]
        assert request.objective == "Enter the car"
        assert any(event["kind"] == "objective_changed" for event in request.events)
    finally:
        conductor.close()


def test_background_does_not_wait_for_slow_job():
    release = threading.Event()
    future = background(lambda: release.wait(2))
    try:
        assert not future.done()
    finally:
        release.set()
    assert future.result(timeout=2)


def test_shoot_aims_fires_releases_and_repeats():
    skill = Skill(SkillCall("shoot", {"duration": 0.2, "count": 2}))
    assert skill.step(observation(0)).pad == Pad(l2=1)
    assert skill.step(observation(0.25)).pad == Pad(l2=1, r2=1)
    assert skill.step(observation(0.45)).pad == NEUTRAL_PAD
    assert skill.step(observation(0.55)).pad == Pad(l2=1)
    assert skill.step(observation(0.75)).pad == Pad(l2=1, r2=1)
    assert skill.step(observation(1.1)).status == "done"
    assert skill.step(observation(1.2)).pad == NEUTRAL_PAD


def test_walk_sprints_and_look_bounds_angle():
    walking = Skill(SkillCall("walk", {"sprint": True, "y": -1}))
    assert walking.step(observation(0)).pad == Pad(left=(0, -1), buttons=("cross",))
    assert walking.step(observation(0.15)).pad == Pad(left=(0, -1))
    looking = Skill(SkillCall("look", {"angle": -999}))
    assert looking.step(observation(0)).pad.right == (-1, 0)
    assert looking.step(observation(5)).pad == NEUTRAL_PAD


@pytest.mark.parametrize(
    "route, expected",
    [("none", "wait"), ("yellow", "drive_route"), ("purple", "drive_route"), ("garbage", "wait")],
)
def test_scripted_head_uses_actual_route_literals(route, expected):
    request = HeadRequest([], "", "", "", "", {"route": route}, None, "", "unused.jpg")
    assert ScriptedHead().decide(request).plan[0].name == expected


def test_ocr_timeout_releases_live_pad_and_stops_recorder(tmp_path):
    clock = Clock()
    bridge = FakeBridge(tmp_path, clock)
    pending = Pending()

    def factory(*args, **kwargs):
        kwargs["ocr"] = True
        return Conductor(*args, **kwargs, submit=pending, ocr_timeout=0.1, detector=NoEvents())

    with pytest.raises(TimeoutError):
        run_play(
            bridge,
            seconds=1,
            pipeline=FakePipeline(),
            clock=clock,
            sleep=clock.sleep,
            conductor_factory=factory,
        )
    assert bridge.calls[-2][1:] == ("pad", {})
    assert bridge.calls[-1][1] == "stop"
    assert any(row["type"] == "ocr_error" for row in rows(tmp_path))


def test_offline_video_writes_decisions_and_frame_log_without_bridge(tmp_path, monkeypatch):
    import runpy
    from pathlib import Path

    import cv2

    def forbidden(*args, **kwargs):
        raise AssertionError("offline replay must not construct a bridge")

    monkeypatch.setattr(Bridge, "__init__", forbidden)
    recording = tmp_path / "source"
    recording.mkdir()
    writer = cv2.VideoWriter(str(recording / "video.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 30, (1280, 720))
    assert writer.isOpened()
    try:
        for _ in range(4):
            writer.write(RGB)
    finally:
        writer.release()
    (recording / "frames.jsonl").write_text(
        "".join(json.dumps({"i": i, "frame_id": i, "t": i / 30}) + "\n" for i in range(4))
    )
    module = runpy.run_path(str(Path(__file__).parents[1] / "tools" / "conductor_replay.py"))
    output = tmp_path / "out"
    result = module["run_offline"](recording, output)
    assert result["frames"] == 4 and result["requests"] == 1
    assert (output / "head-0001.jpg").is_file() and (output / "head-0001.prompt.txt").is_file()
    frames = [json.loads(line) for line in (output / "play.jsonl").read_text().splitlines()]
    assert len(frames) == 4 and all(not frame["sent"] for frame in frames)
    with pytest.raises(ValueError, match="outside the source"):
        module["run_offline"](recording, recording / "out")


def test_bridge_full_frame_and_whole_pad():
    calls = []

    def server(request):
        calls.append(request)
        if request.url.path == "/frame.raw":
            return httpx.Response(
                200,
                content=b"\0\0\0",
                headers={"X-Width": "1", "X-Height": "1", "X-Frame-Id": "2", "X-Frame-Age-Ms": "10"},
            )
        return httpx.Response(200)

    with Bridge(transport=httpx.MockTransport(server)) as bridge:
        assert bridge.frame().id == 2
        bridge.pad(Pad(buttons=("cross",), left=(0, -1), right=(1, 0), l2=0.2, r2=0.4))
    assert "x" not in calls[0].url.params
    assert json.loads(calls[1].content) == {
        "buttons": ["cross"],
        "left": [0, -1],
        "right": [1, 0],
        "l2": 0.2,
        "r2": 0.4,
        "ttl_ms": 250,
    }


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, delay):
        self.t += max(delay, 0.001)


class FakePipeline:
    def step(self, *args, **kwargs):
        return READING, True, Command(0, 0, 0, "idle")

    def close(self):
        self.closed = True


class FakeBridge:
    def __init__(self, path, clock, *, freeze=False, conflict=False, error=None):
        self.path, self.clock = path, clock
        self.freeze, self.conflict, self.error = freeze, conflict, error
        self.calls = []
        self.i = 0

    def frame(self, rect, after=None):
        self.i += 1
        if self.error and self.i == 5:
            raise self.error
        return Frame(RGB, 1 if self.freeze and self.i > 4 else self.i, 0)

    def pad(self, pad=None):
        self.calls.append((self.clock(), "pad", {} if pad is None else pad.payload()))
        if self.conflict and pad is not None and pad != NEUTRAL_PAD:
            self.conflict = False
            return 409
        return 200

    def record_start(self, directory, *, shadow):
        self.calls.append((self.clock(), "start", None))
        return self.path

    def record_stop(self):
        self.calls.append((self.clock(), "stop", None))


def instant(function, *args):
    future = Future()
    future.set_result(function(*args))
    return future


def configured_conductor(*args, **kwargs):
    kwargs["head"] = ScriptedHead(
        [{"plan": [{"name": "walk", "args": {"x": 1, "duration": 10}}], "sentence": "Ich gehe weiter."}]
    )
    return Conductor(*args, **kwargs, submit=instant, detector=NoEvents())


@pytest.mark.parametrize("mode", ["frozen", "conflict", "shadow", "error", "interrupt"])
def test_live_safety_also_applies_to_walking(tmp_path, mode):
    clock = Clock()
    error = (
        ValueError("frame failure")
        if mode == "error"
        else KeyboardInterrupt()
        if mode == "interrupt"
        else None
    )
    bridge = FakeBridge(tmp_path, clock, freeze=mode == "frozen", conflict=mode == "conflict", error=error)
    pipeline = FakePipeline()

    def run():
        return run_play(
            bridge,
            seconds=1.6,
            shadow=mode == "shadow",
            pipeline=pipeline,
            ocr=False,
            clock=clock,
            sleep=clock.sleep,
            conductor_factory=configured_conductor,
        )

    if error:
        with pytest.raises(type(error)):
            run()
    else:
        run()
    pads = [(t, data) for t, kind, data in bridge.calls if kind == "pad"]
    assert pipeline.closed
    assert bridge.calls[-1][1] == "stop"
    if mode == "shadow":
        assert not pads
        assert any(row["applied"] for row in rows(tmp_path))
    else:
        assert pads[-1][1] == {}
    if mode == "frozen":
        assert len([data for _, data in pads if data == {}]) == 2
    if mode == "conflict":
        index = next(i for i, (_, data) in enumerate(pads) if data.get("left") == [1, 0])
        assert pads[index + 1][1] == {}
        assert pads[index + 1][0] - pads[index][0] >= 1
        assert pads[index + 2][1]["left"] == [1, 0]


def test_codex_adapter_fake_executable(tmp_path):
    executable = tmp_path / "fake-codex"
    audit = tmp_path / "audit.json"
    executable.write_text(
        f"#!{sys.executable}\n"
        + "import json, pathlib, sys\n"
        + "audit = {'argv': sys.argv, 'stdin': sys.stdin.read()}\n"
        + f"pathlib.Path({str(audit)!r}).write_text(json.dumps(audit))\n"
        + f"pathlib.Path(sys.argv[sys.argv.index('-o')+1]).write_text({json.dumps(reply('wait'))!r})\n"
    )
    executable.chmod(0o755)
    request = HeadRequest([], "", "", "", "", {}, None, "", str(tmp_path / "image.jpg"))
    result = CodexHead(executable=str(executable), model="test-model").decide(request)
    assert result.plan[0].name == "wait"
    data = json.loads(audit.read_text())
    assert data["argv"][-1] == "-"
    assert 'model_reasoning_effort="low"' in data["argv"]
    assert "--output-schema" in data["argv"] and "-i" in data["argv"]
    assert "Observation" in data["stdin"] and "test-model" in data["argv"]


@pytest.mark.parametrize(
    "body",
    [
        "raise SystemExit(2)",
        "pass",
        "import pathlib, sys; pathlib.Path(sys.argv[sys.argv.index('-o')+1]).write_text('{}')",
        "import time; time.sleep(2)",
    ],
)
def test_codex_errors_reject_without_real_model(tmp_path, body):
    executable = tmp_path / "fake-codex"
    executable.write_text(f"#!{sys.executable}\n{body}\n")
    executable.chmod(0o755)
    request = HeadRequest([], "", "", "", "", {}, None, "", str(tmp_path / "image.jpg"))
    import subprocess

    with pytest.raises((ValueError, subprocess.TimeoutExpired)):
        CodexHead(executable=str(executable), timeout=0.2).decide(request)


def test_a_replaced_press_is_let_go_before_the_same_button_is_pressed_again():
    runner = SkillRunner()
    hold = (SkillCall("press", {"button": "cross", "duration": 1.0}),)
    runner.replace(hold)
    assert runner.tick(observation(0.0)).pad == NEUTRAL_PAD
    assert runner.tick(observation(0.03)).pad.buttons == ("cross",)
    runner.replace(hold)
    # without this gap the game sees one long press instead of two
    assert runner.tick(observation(0.06)).pad == NEUTRAL_PAD
    assert runner.tick(observation(0.09)).pad.buttons == ("cross",)


@pytest.mark.parametrize("fail", [False, True])
def test_optional_sources_reach_every_tick_and_close_on_error(tmp_path, fail):
    from pilot.contract import Detection, Hud

    clock = Clock()
    bridge = FakeBridge(tmp_path, clock, error=RuntimeError("source-run") if fail else None)
    pipeline = FakePipeline()
    captured = []

    class Objects:
        closed = 0

        def poll(self, frame, t):
            assert frame is RGB
            return t, (Detection("person", (0, 0, 1, 1), 0.9),)

        def close(self):
            self.closed += 1

    class HUD:
        def read(self, frame, text=None):
            assert frame is RGB
            assert text is not None
            return Hud(wanted=0, health=1)

    class ObservingRunner(SkillRunner):
        def tick(self, observation):
            captured.append(observation)
            return super().tick(observation)

    def factory(*args, **kwargs):
        kwargs["runner"] = ObservingRunner()
        return Conductor(*args, **kwargs, submit=instant, detector=NoEvents())

    objects = Objects()
    args = dict(
        seconds=0.3,
        pipeline=pipeline,
        ocr=False,
        clock=clock,
        sleep=clock.sleep,
        conductor_factory=factory,
        objects=objects,
        hud=HUD(),
    )
    if fail:
        with pytest.raises(RuntimeError, match="source-run"):
            run_play(bridge, **args)
    else:
        run_play(bridge, **args)
    assert objects.closed == 1
    assert pipeline.closed
    assert captured
    assert all(
        obs.frame is RGB
        and obs.objects[0].kind == "person"
        and obs.hud.health == 1
        and obs.objects_time is not None
        for obs in captured
    )
    assert bridge.calls[-1][1] == "stop"
    assert [call[2] for call in bridge.calls if call[1] == "pad"][-1] == {}


def test_a_rested_controller_gets_a_touch_of_the_camera(tmp_path):
    # Live on 11 November the game had left the figure for its idle scenery, the judge said
    # "vehicle" to a car park, every skill waited for a figure on foot, and the scenery stayed.
    conductor = Conductor(tmp_path / "awake", submit=Pending(), detector=NoEvents(), awake=15.0)
    quiet = Conductor(tmp_path / "quiet", submit=Pending(), detector=NoEvents())
    try:
        sent = [conductor.tick(observation(tick / 30), RGB).pad for tick in range(30 * 40)]
        touched = [tick for tick, pad in enumerate(sent) if pad != NEUTRAL_PAD]
        # At once, because a session does not know how long the controller rested, then every 15 s.
        assert [round(tick / 30) for tick in touched[::3]] == [0, 15, 30] and len(touched) == 9
        assert all(pad.left == (0.0, 0.0) and not pad.buttons and pad.right[1] == 0 for pad in sent)
        first, second, third = (sent[tick].right[0] for tick in touched[::3])
        assert first > 0 > second and third == first  # each one turns the last one back
        assert all(quiet.tick(observation(tick / 30), RGB).pad == NEUTRAL_PAD for tick in range(90))
    finally:
        conductor.close()
        quiet.close()


def test_a_working_controller_and_a_menu_get_no_touch(tmp_path):
    conductor = Conductor(tmp_path, submit=Pending(), detector=NoEvents(), awake=15.0)
    try:
        conductor.last_input = 0.0
        busy = Observation(READING, True, 20.0)
        conductor._tick = lambda *args, **reads: SkillResult(Pad(left=(0.0, -1.0)))
        assert conductor.tick(busy, RGB).pad == Pad(left=(0.0, -1.0)) and conductor.last_input == 20.0
        conductor._tick = lambda *args, **reads: SkillResult()
        menu = Observation(READING, True, 40.0, hud=Hud(wanted=0, health=1.0, screen="pause"))
        assert conductor.tick(menu, RGB).pad == NEUTRAL_PAD
        assert conductor.tick(Observation(READING, True, 40.1), RGB).pad != NEUTRAL_PAD
    finally:
        conductor.close()


class Detected:
    def __init__(self):
        self.kinds = []

    def update(self, reading, timestamp, **reads):
        return [SceneEvent(kind, timestamp, "before", "after", "test") for kind in self.kinds]


def test_a_map_the_running_skill_opened_is_no_news_for_the_head(tmp_path):
    # Live on 11 November: told that the minimap had gone, the head planned a wait for the screen,
    # the wait replaced set_waypoint, and the reflex closed the map the skill had just opened.
    pending, detector = Pending(), Detected()
    conductor = Conductor(tmp_path, submit=pending, detector=detector)
    try:
        conductor.tick(observation(0), RGB, events=[{"kind": "objective_changed"}])
        plan = {
            "plan": [{"name": "set_waypoint", "args": {"target": "away"}}],
            "sentence": "Ich setze ein Ziel.",
        }
        pending.jobs[0][0].set_result(parse_response(plan))
        conductor.tick(observation(0.03), RGB)  # the tick that lets go of the plan before
        conductor.tick(observation(0.06), RGB)
        assert conductor.runner.active.name == "set_waypoint"
        for tick, kind in enumerate(("hud_absent", "vehicle_exit", "vehicle_enter", "hud_present"), start=3):
            detector.kinds = [kind]
            conductor.tick(observation(tick * 0.03), RGB)
        assert len(pending.jobs) == 1 and conductor.runner.active.name == "set_waypoint"
        detector.kinds = ["route_vanished"]  # other news still reaches the head
        conductor.tick(observation(0.21), RGB)
        assert len(pending.jobs) == 2
    finally:
        conductor.close()
