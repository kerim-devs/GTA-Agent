"""Recorded judgments and injected transports; no server or controller is contacted."""

import base64
import copy
import json
import threading
import time
from concurrent.futures import Future
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
import pytest

from pilot.conductor import Conductor
from pilot.contract import Judgment, Observation, Reading, player_mode
from pilot.head import HeadResponse, SkillCall
from pilot.judge import JOINT, QUESTIONS, SYSTEM, ModeFilter, Reader, endpoint, parse, post

RGB = np.zeros((720, 1280, 3), dtype=np.uint8)
READING = Reading("tilted", "none", None, None, None, False, 1.0)
SEQUENCES = Path(__file__).resolve().parents[2] / "lab" / "judge" / "sequences"


def recorded():
    return [
        json.loads(line)
        for path in sorted(SEQUENCES.glob("*.jsonl"))
        for line in path.read_text().splitlines()
    ]


def choice(mode="A", confidence=0.7):
    import math

    answers = [mode, "B", "B", "B", "A", "B"]
    return {
        "message": {"content": " ".join(answers)},
        "logprobs": {
            "content": [
                {
                    "token": answer,
                    "top_logprobs": [
                        {
                            "token": letter,
                            "logprob": math.log(
                                confidence if letter == answer else (1 - confidence) / (len(meaning) - 1)
                            ),
                        }
                        for letter in meaning
                    ],
                }
                for answer, (_, meaning) in zip(answers, QUESTIONS.values(), strict=True)
            ]
        },
    }


def judgment(t, mode="A", confidence=0.7):
    return parse(choice(mode, confidence), t, 0.1, "http://localhost:8000=test")


def wait_for(function):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        result = function()
        if result:
            return result
        time.sleep(0.001)
    pytest.fail("background request did not finish")


def test_recorded_answers_and_question_probabilities():
    rows = recorded()
    assert len(rows) == 269
    for row in rows:
        result = parse(row["choice"], row["time"], row["seconds"], "recorded")
        assert set(result.answers) == set(QUESTIONS)
        for name, (_, meaning) in QUESTIONS.items():
            assert result.answers[name].value in meaning.values()
            assert result.answers[name].probability is not None
            assert set(result.probabilities[name]) == set(meaning)
            assert sum(result.probabilities[name].values()) == pytest.approx(1)


@pytest.mark.parametrize("content", ["A B B B A", "D B B B A B", "A C B B A B", "A B B B A B explanation"])
def test_incomplete_or_invalid_letters_cannot_accept_mode(content):
    reply = copy.deepcopy(recorded()[0]["choice"])
    reply["message"]["content"] = content
    modes = ModeFilter()
    with pytest.raises(ValueError):
        modes.update(parse(reply, 0, 0.1, "recorded"), 0)
    assert modes.mode is None


def test_tilted_map_stays_on_foot_after_initial_confirmation():
    modes = ModeFilter()
    rows = [row for row in recorded() if 15600 <= row["frame"] <= 17400]
    assert len(rows) == 121
    accepted = [
        modes.update(parse(row["choice"], row["time"], row["seconds"], "recorded"), row["time"])
        for row in rows
    ]
    assert accepted[0] is None
    assert accepted[1:] == ["foot"] * 120


def test_a_mode_needs_two_judgments_in_a_row_and_lapses_with_its_frame():
    modes = ModeFilter()
    assert modes.update(judgment(0), 0) is None
    assert modes.update(judgment(0), 0.1) is None  # the same frame is not two votes
    assert modes.update(judgment(0.25), 0.25) == "foot"
    assert modes.update(judgment(0.5, "B"), 0.5) == "foot"
    assert modes.update(judgment(0.75, "A"), 0.75) == "foot"
    # No probability lets one judgment through: the recorded wrong answer came with 0.9997.
    assert modes.update(judgment(1, "B", 0.9997), 1) == "foot"
    assert modes.update(judgment(1.25, "B"), 1.25) == "vehicle"
    assert modes.update(judgment(0.5, "A", 0.99), 1.3) == "vehicle"  # an older frame is no vote
    assert modes.update(None, 2.26) is None
    assert modes.update(judgment(1.0, "A", 0.99), 2.3) is None
    observation = Observation(READING, True, 0, mode="foot")
    assert player_mode(observation) == "foot"
    assert player_mode(replace(observation, mode=None)) == "vehicle"
    assert player_mode(replace(observation, mode="none")) == "none"


def test_hung_request_never_blocks_and_late_answer_is_discarded():
    now = [0.0]
    entered, release = threading.Event(), threading.Event()
    sent = []

    def transport(url, model, image):
        sent.append(url)
        entered.set()
        release.wait(5)
        return choice(), 0.1

    reader = Reader(["http://localhost:8000=test"], transport=transport, clock=lambda: now[0])
    try:
        started = time.monotonic()
        assert reader.poll(RGB, 0) is None
        assert time.monotonic() - started < 0.1
        assert entered.wait(1)
        for tick in range(1, 40):
            now[0] = tick / 30
            started = time.monotonic()
            assert reader.poll(RGB, now[0]) is None
            assert time.monotonic() - started < 0.1
        failures = reader.drain_failures()
        assert len(failures) == 1 and failures[0]["error"] == "timeout"
        assert failures[0]["duration"] == pytest.approx(1)
        reader.close()
        release.set()
        now[0] = 5
        assert reader.poll(RGB, 5) is None
        assert len(sent) == 1
    finally:
        release.set()
        reader.close()


def test_close_during_encoding_prevents_request(monkeypatch):
    from pilot import judge

    entered, release, finished = threading.Event(), threading.Event(), threading.Event()

    def encode(*args):
        entered.set()
        release.wait(2)
        finished.set()
        return "image"

    sent = []
    monkeypatch.setattr(judge, "encode", encode)
    reader = Reader(["http://localhost=model"], transport=lambda *args: sent.append(args))
    try:
        reader.poll(RGB, 0)
        assert entered.wait(1)
        reader.close()
        release.set()
        assert finished.wait(1)
        assert reader.poll(RGB, 1) is None
        assert sent == []
    finally:
        release.set()
        reader.close()


def test_failure_falls_back_cools_down_and_results_are_delivered_once():
    now, sent = [0.0], []

    def transport(url, model, image):
        sent.append((url, now[0]))
        if url.endswith("8000"):
            raise OSError("offline")
        decoded = cv2.imdecode(np.frombuffer(base64.b64decode(image), dtype=np.uint8), cv2.IMREAD_COLOR)
        assert decoded.shape == (360, 640, 3)
        assert decoded[100, 100, 2] > 240 and decoded[100, 100, 0] < 10
        return choice(), 0.1

    reader = Reader(
        ["http://localhost:8000=first", "http://127.0.0.1:8001=second"],
        transport=transport,
        clock=lambda: now[0],
    )
    red = RGB.copy()
    red[:, :, 0] = 255
    try:
        reader.poll(red, 0)
        failures = wait_for(lambda: (reader.poll(red, 0), reader.drain_failures())[1])
        assert failures[0]["server"].endswith("=first")
        now[0] = 0.25
        result = wait_for(lambda: reader.poll(red, 0.25))
        assert isinstance(result, Judgment)
        assert result.capture == 0.25 and result.server.endswith("=second")
        assert reader.poll(red, 0.25) is None
        now[0] = 1.9
        assert wait_for(lambda: reader.poll(red, 1.9)).server.endswith("=second")
        assert [url for url, _ in sent].count("http://localhost:8000") == 1
        now[0] = 2.2
        wait_for(lambda: (reader.poll(red, 2.2), reader.drain_failures())[1])
        assert sent[-1] == ("http://localhost:8000", 2.2)
        reader.close()
        now[0] = 10
        reader.poll(red, 10)
        assert len(sent) == 4
    finally:
        reader.close()


@pytest.mark.parametrize(
    "server",
    [
        "http://8.8.8.8=model",
        "https://example.com=model",
        "http://0.0.0.0=model",
        "http://169.254.169.254=model",
        "http://224.0.0.1=model",
        "http://[2001:4860:4860::8888]=model",
        "http://localhost@8.8.8.8=model",
        "http://localhost:bad=model",
    ],
)
def test_public_or_ambiguous_addresses_are_refused(server):
    with pytest.raises(ValueError):
        Reader([server], transport=lambda *args: pytest.fail("validation sent a request"))


@pytest.mark.parametrize(
    "server",
    [
        "http://localhost:8000=model",
        "http://127.0.0.1=model",
        "http://10.0.0.1=model",
        "http://172.16.0.1=model",
        "http://192.168.1.2=model",
        "http://[::1]=model",
        "http://[fd00::1]=model",
    ],
)
def test_local_addresses_are_accepted(server):
    assert endpoint(server)[1] == "model"


def test_request_preserves_measured_prompt_and_disables_redirects_and_proxy(monkeypatch):
    import io
    import urllib.request

    seen = {}

    class Opener:
        def open(self, request, timeout):
            seen.update(body=json.loads(request.data), url=request.full_url, timeout=timeout)
            return io.StringIO(json.dumps({"choices": [choice()]}))

    def opener(*handlers):
        assert handlers[0].proxies == {}
        with pytest.raises(ValueError, match="redirect"):
            handlers[1].redirect_request(None, None, 302, "", {}, "http://8.8.8.8")
        return Opener()

    monkeypatch.setattr(urllib.request, "build_opener", opener)
    post("http://localhost:8000", "model", "image", JOINT, 14, timeout=1)
    assert seen["url"] == "http://localhost:8000/v1/chat/completions"
    assert seen["timeout"] == 1
    assert seen["body"] == {
        "model": "model",
        "temperature": 0,
        "max_tokens": 14,
        "logprobs": True,
        "top_logprobs": 5,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,image"}},
                    {"type": "text", "text": JOINT},
                ],
            },
        ],
    }


def test_conductor_logs_judgments_and_emits_only_accepted_changes(tmp_path):
    jobs, captures = [], []

    class Judge:
        closed = False
        replies = iter(
            [
                judgment(0),
                judgment(0.25),
                judgment(0.5, "B"),
                judgment(0.75, "B"),
                judgment(1, "B"),
                None,
                None,
            ]
        )

        def poll(self, rgb, capture):
            captures.append(capture)
            return next(self.replies)

        def drain_failures(self):
            return []

        def close(self):
            self.closed = True

    class Detector:
        def update(self, *args, **kwargs):
            return ()

    def submit(function, request):
        future = Future()
        jobs.append((future, request))
        return future

    judge = Judge()
    conductor = Conductor(tmp_path, judge=judge, submit=submit, detector=Detector())
    try:
        for t in (0, 0.25, 0.5, 0.75, 1):
            conductor.tick(Observation(READING, True, t), RGB, frame_time=t - 0.1)
        assert captures == pytest.approx([-0.1, 0.15, 0.4, 0.65, 0.9])
        # The judge's first word is no news: the head is told of a change between two modes.
        assert not [event for event in jobs[0][1].events if event["kind"] == "mode_changed"]
        jobs[0][0].set_result(HeadResponse((SkillCall("wait", {"duration": 5}),), "Wait."))
        conductor.tick(Observation(READING, True, 1.1), RGB)
        assert jobs[1][1].events == [{"kind": "mode_changed", "old": "foot", "new": "vehicle"}]
        assert jobs[1][1].judgment["mode"] == "vehicle"
        assert jobs[1][1].judgment["age"] == pytest.approx(0.1)
        # A judge that falls silent lets the mode lapse and tells the head nothing.
        conductor.tick(Observation(READING, True, 2.01), RGB)
        assert conductor.mode_filter.mode is None
        assert not [event for event in conductor.pending if event["kind"] == "mode_changed"]
    finally:
        conductor.close()
    assert judge.closed
    rows = [json.loads(line) for line in (tmp_path / "judge.jsonl").read_text().splitlines()]
    assert len(rows) == 5
    assert [row["mode"] for row in rows] == [None, "foot", "foot", "vehicle", "vehicle"]
    assert set(rows[0]) == {"t", "capture", "answers", "probabilities", "duration", "server", "mode"}


def test_cli_preserves_judge_server_order_and_defaults_to_off(monkeypatch):
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
    cli.main(
        [
            "play",
            "--no-objects",
            "--judge",
            "http://10.0.0.1=first",
            "--judge",
            "http://localhost:8000=second",
        ]
    )
    assert calls[0]["judge"].servers == [("http://10.0.0.1", "first"), ("http://localhost:8000", "second")]
    calls[0]["judge"].close()
    cli.main(["play", "--no-objects"])
    assert calls[1]["judge"] is None
    with pytest.raises(SystemExit):
        cli.main(["play", "--judge", "https://8.8.8.8=model"])
    assert len(calls) == 2
