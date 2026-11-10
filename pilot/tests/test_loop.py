import json
import signal
from dataclasses import asdict

import httpx
import numpy as np
import pytest

from pilot.bridge import Bridge
from pilot.contract import Command, Reading
from pilot.loop import Pipeline, run_drive

READING = Reading("tilted", "yellow", 12.0, 20.0, 0.0, False, 0.9)
COMMAND = Command(0.4, 0.5, 0.0, "follow")


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class Driver:
    def __init__(self, command=COMMAND):
        self.calls = []
        self.command = command

    def step(self, reading, t, moving):
        self.calls.append((reading, t, moving))
        return self.command


class Harness:
    def __init__(self, tmp_path):
        self.clock = Clock()
        self.destination = tmp_path / "20261110-120000"
        self.events = []
        self.frames = 0
        self.frame_rule = lambda request: True
        self.pad_rule = lambda body: 200
        self.age = 20
        self.driver = Driver()
        self.pipeline = Pipeline(reader=lambda crop: READING, motion=lambda a, b: 2.0, driver=self.driver)
        self.bridge = Bridge(transport=httpx.MockTransport(self.respond))

    def respond(self, request):
        body = json.loads(request.content) if request.content else None
        path = request.url.path
        if path == "/frame.raw":
            self.frames += 1
            available = self.frame_rule(request)
            self.clock.sleep(1 / 60 if available else 0.1)
            status = 200 if available else 204
            self.events.append((self.clock(), path, body, status))
            if not available:
                return httpx.Response(204)
            return httpx.Response(
                200,
                content=np.full((170, 260, 3), self.frames % 256, np.uint8).tobytes(),
                headers={
                    "X-Frame-Id": str(self.frames),
                    "X-Frame-Age-Ms": str(self.age),
                    "X-Width": "260",
                    "X-Height": "170",
                },
            )
        if path == "/pad":
            status = self.pad_rule(body)
            self.events.append((self.clock(), path, body, status))
            return httpx.Response(status, json={"ok": status == 200})
        if path == "/record":
            self.events.append((self.clock(), path, body, 200))
            if body["action"] == "start":
                self.destination.mkdir()
            return httpx.Response(200, json={"dir": str(self.destination)})
        raise AssertionError(f"Unexpected request: {request}")

    def run(self, **kwargs):
        with self.bridge:
            return run_drive(
                self.bridge,
                pipeline=self.pipeline,
                clock=self.clock,
                sleep=self.clock.sleep,
                record_dir=self.destination.parent,
                **kwargs,
            )

    def pads(self):
        return [event for event in self.events if event[1] == "/pad"]

    def rows(self):
        return [json.loads(line) for line in (self.destination / "pilot.jsonl").read_text().splitlines()]


def test_frozen_stream_releases_once_then_waits(tmp_path):
    harness = Harness(tmp_path)
    harness.age = 200
    harness.frame_rule = lambda request: harness.frames == 1
    summary = harness.run(seconds=0.85)
    pads = harness.pads()
    assert pads[0][2]["r2"] == 0.5
    assert [event[2] for event in pads[1:]] == [{}, {}]  # Stale release, then exit release.
    assert 0.28 <= pads[1][0] - pads[0][0] <= 0.4
    assert pads[2][0] - pads[1][0] > 0.3
    assert summary.ticks > len(pads)


def test_409_waits_a_second_and_resumes_only_after_accepted_neutral(tmp_path):
    harness = Harness(tmp_path)
    attempts = 0

    def pad_rule(body):
        nonlocal attempts
        attempts += 1
        return 409 if attempts <= 2 else 200

    harness.pad_rule = pad_rule
    summary = harness.run(seconds=2.3)
    pads = harness.pads()
    assert pads[0][2] and pads[0][3] == 409
    assert pads[1][2] == pads[2][2] == {}
    assert pads[1][0] - pads[0][0] >= 1
    assert pads[2][0] - pads[1][0] >= 1
    assert pads[2][3] == 200
    assert pads[3][2]["r2"] == 0.5
    assert summary.conflicts == 2
    recovery = [row for row in harness.rows() if row["status"] == 200]
    assert recovery and not recovery[0]["sent"]
    blocked = [row for row in harness.rows() if 0.1 < row["t"] < 1.9]
    assert len(blocked) > 40
    assert all(row["command"] is not None and not row["sent"] for row in blocked)


def test_shadow_never_posts_pad_and_logs_complete_readings(tmp_path, capsys):
    harness = Harness(tmp_path)
    summary = harness.run(seconds=0.5, shadow=True)
    assert not harness.pads()
    assert harness.events[0][2]["note"] == "pilot shadow"
    assert harness.events[-1][2] == {"action": "stop"}
    rows = harness.rows()
    assert rows[0]["t"] == 0
    assert len(rows) == summary.ticks
    assert rows[0]["reading"] == asdict(READING)
    assert rows[0]["command"] == asdict(COMMAND)
    assert rows[0]["frame_id"] == 1
    assert rows[0]["frame_age"] == 0.02
    assert rows[0]["time"] == pytest.approx(100 + 1 / 60 - 0.02)
    assert all(not row["sent"] and row["status"] is None for row in rows)
    assert rows[-1]["moving"] is True
    assert 29 <= summary.ticks / summary.elapsed <= 31
    assert "states={'follow':" in capsys.readouterr().out


@pytest.mark.parametrize("ending", ["normal", "exception", "keyboard", signal.SIGINT, signal.SIGTERM])
def test_every_exit_neutralizes_before_stopping_recorder(tmp_path, ending):
    harness = Harness(tmp_path)
    handlers = {signum: signal.getsignal(signum) for signum in (signal.SIGINT, signal.SIGTERM)}

    def frame_rule(request):
        if harness.frames == 2:
            if ending == "exception":
                raise ValueError("reader failed")
            if ending == "keyboard":
                raise KeyboardInterrupt
            if isinstance(ending, signal.Signals):
                signal.raise_signal(ending)
        return True

    harness.frame_rule = frame_rule
    error = ValueError if ending == "exception" else KeyboardInterrupt if ending == "keyboard" else None
    if error:
        with pytest.raises(error):
            harness.run(seconds=0.2)
    else:
        harness.run(seconds=0.2)
    assert harness.events[-2][1:3] == ("/pad", {})
    assert harness.events[-1][1:3] == ("/record", {"action": "stop"})
    assert all(signal.getsignal(signum) == handler for signum, handler in handlers.items())


def test_failed_cleanup_still_stops_recorder_and_preserves_original_error(tmp_path):
    harness = Harness(tmp_path)
    harness.pipeline.reader = lambda crop: (_ for _ in ()).throw(ValueError("original"))
    harness.pad_rule = lambda body: 500
    with pytest.raises(ValueError, match="original"):
        harness.run(seconds=0.2)
    assert harness.events[-1][1:3] == ("/record", {"action": "stop"})


def test_old_frames_never_drive_and_no_record_does_not_touch_recorder(tmp_path):
    harness = Harness(tmp_path)
    harness.age = 500
    harness.run(seconds=0.5, record=False)
    assert not harness.driver.calls
    assert all(event[2] == {} for event in harness.pads())
    assert not any(event[1] == "/record" for event in harness.events)


def test_motion_uses_frame_times_and_preserves_unknown():
    driver = Driver()
    pairs = []

    def motion(a, b):
        pairs.append((int(a[0, 0, 0]), int(b[0, 0, 0])))
        return None

    pipeline = Pipeline(reader=lambda crop: READING, motion=motion, driver=driver)
    for index in range(12):
        pipeline.step(np.full((170, 260, 3), index, np.uint8), 10 + index / 30)
    assert pairs[-1] == (5, 11)
    assert all(call[2] is None for call in driver.calls)


def test_route_end_waits_for_stop_and_driver_neutral(tmp_path):
    harness = Harness(tmp_path)
    harness.pipeline.reader = lambda crop: Reading("tilted", "none", None, None, 0, False, 1)
    harness.pipeline.motion = lambda a, b: 0
    harness.driver.command = Command(0, 0, 0, "route_gone")
    summary = harness.run(seconds=5)
    assert 2 <= summary.elapsed < 2.2


def test_no_route_does_not_end_while_driver_is_braking(tmp_path):
    harness = Harness(tmp_path)
    harness.pipeline.reader = lambda crop: Reading("tilted", "none", None, None, 0, False, 1)
    harness.pipeline.motion = lambda a, b: 0
    harness.driver.command = Command(0, 0, 0.2, "brake")
    summary = harness.run(seconds=2.2)
    assert summary.elapsed >= 2.2


def test_a_recording_that_could_not_be_started_is_not_stopped(tmp_path):
    harness = Harness(tmp_path)
    respond = harness.respond

    def busy(request):
        if request.url.path == "/record" and json.loads(request.content)["action"] == "start":
            harness.events.append((harness.clock(), "/record", {"action": "start"}, 409))
            return httpx.Response(409, json={"ok": False, "error": "already recording"})
        return respond(request)

    harness.bridge = Bridge(transport=httpx.MockTransport(busy))
    with pytest.raises(httpx.HTTPStatusError):
        harness.run(seconds=0.2)
    assert [event[2] for event in harness.events if event[1] == "/record"] == [{"action": "start"}]
