"""The way straight ahead, asked of the model about one frame at a time and never on the tick's way."""

import base64
import threading
import time

import cv2
import numpy as np
import pytest
from test_sides import SERVER, reply

from pilot import ahead
from pilot.ahead import Ahead


def frame(value=90):
    return np.full((720, 1280, 3), value, np.uint8)


def waited(asked):
    deadline = time.monotonic() + 2.0
    while asked.busy and time.monotonic() < deadline:
        time.sleep(0.001)
    return not asked.busy


def test_the_whole_frame_is_asked_about_once_and_the_answer_belongs_to_that_frame():
    seen = []

    def transport(url, model, image):
        picture = cv2.imdecode(np.frombuffer(base64.b64decode(image), np.uint8), cv2.IMREAD_COLOR)
        seen.append((url, model, picture.shape))
        return reply("B", A=0.04, B=0.96)

    asked = Ahead(SERVER, transport=transport)
    assert asked.answer(0.0) is None
    assert asked.ask(frame(), 12.0) and waited(asked)
    assert seen == [("http://127.0.0.1:1234", "model", (360, ahead.WIDTH, 3))]
    share, error = asked.answer(12.0)
    assert share == pytest.approx(0.04, abs=1e-3) and error is None
    # What was said of an earlier view is no answer about a later one.
    assert asked.answer(12.5) is None and asked.log[-1]["open"] == pytest.approx(0.04, abs=1e-3)


def test_one_question_at_a_time_and_none_about_what_is_no_frame():
    go, calls = threading.Event(), []

    def transport(url, model, image):
        calls.append(image)
        go.wait(2.0)
        return reply("A", A=1.0)

    asked = Ahead(SERVER, transport=transport)
    assert asked.ask(frame(), 1.0) and not asked.ask(frame(), 1.1)
    go.set()
    assert waited(asked) and len(calls) == 1
    for bad in (None, np.zeros((10, 10, 3), np.uint8), "frame"):
        assert not asked.ask(bad, 2.0)
    assert not Ahead([], transport=transport).ask(frame(), 3.0)


def test_a_server_that_fails_answers_with_its_error_and_the_next_question_can_be_asked():
    def transport(url, model, image):
        raise OSError("unreachable")

    asked = Ahead(SERVER, transport=transport)
    assert asked.ask(frame(), 1.0) and waited(asked)
    share, error = asked.answer(1.0)
    assert share is None and "OSError" in error
    assert asked.ask(frame(), 2.0) and waited(asked)


def test_a_session_without_a_judge_asks_nobody(monkeypatch):
    monkeypatch.setattr(ahead, "_active", None)
    assert ahead.use([]) is None and ahead.active() is None
    assert ahead.use(SERVER) is ahead.active() and isinstance(ahead.active(), Ahead)
