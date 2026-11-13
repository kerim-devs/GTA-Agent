"""The two strips beside the figure, asked of the model one at a time and never on the tick's way."""

import base64
import math
import threading
import time

import cv2
import numpy as np
import pytest

from pilot import sides
from pilot.sides import Sides, choose, open_share

SERVER = ["http://127.0.0.1:1234=model"]


def reply(letter, **shares):
    """A choice as the server sends it: the answer's letter and what it gave each alternative."""
    top = [{"token": key, "logprob": math.log(share)} for key, share in shares.items()]
    return {"message": {"content": letter}, "logprobs": {"content": [{"token": letter, "top_logprobs": top}]}}


def picture():
    """A frame whose left strip is white and whose right strip is black."""
    frame = np.full((720, 1280, 3), 128, np.uint8)
    frame[sides.LEFT] = 255
    frame[sides.RIGHT] = 0
    return frame


def waited(asked):
    deadline = time.monotonic() + 2.0
    while asked.busy and time.monotonic() < deadline:
        time.sleep(0.001)
    return not asked.busy


def test_how_open_a_strip_is_comes_from_what_the_model_gave_each_letter():
    assert open_share(reply("A", A=0.9, B=0.1)) == pytest.approx(0.9, abs=1e-3)
    assert open_share(reply("B", A=0.03, B=0.97)) == pytest.approx(0.03, abs=1e-3)
    # A server that sends no shares still says a letter; one that says nothing says nothing.
    assert open_share({"message": {"content": "B"}}) == 0.0
    assert open_share({"message": {"content": "A"}}) == 1.0
    assert open_share({"message": {"content": ""}}) is None


def test_a_side_is_chosen_only_where_it_is_clearly_the_more_open():
    assert choose(1.0, 0.03) == -1 and choose(0.1, 0.9) == 1
    # At a building's wall by night it said 1.00 and 0.97, at a fence 0.49 and 0.29: no side.
    assert choose(1.0, 0.97) is None and choose(0.49, 0.29) is None
    assert choose(None, 0.9) is None and choose(0.9, None) is None


def test_each_strip_is_asked_alone_and_the_answer_belongs_to_its_frame():
    seen = []

    def transport(url, model, image):
        strip = cv2.imdecode(np.frombuffer(base64.b64decode(image), np.uint8), cv2.IMREAD_GRAYSCALE)
        seen.append((url, model, strip.shape, float(strip.mean())))
        return reply("A", A=0.9, B=0.1) if len(seen) == 1 else reply("B", A=0.2, B=0.8)

    asked = Sides(SERVER, transport=transport)
    assert asked.answer(0.0) is None
    assert asked.ask(picture(), 12.0) and waited(asked)
    assert [(url, model, shape) for url, model, shape, _ in seen] == [
        ("http://127.0.0.1:1234", "model", (sides.WIDTH, sides.WIDTH))
    ] * 2
    assert seen[0][3] > 240 and seen[1][3] < 15
    assert asked.answer(12.0) == pytest.approx((0.9, 0.2), abs=1e-3)
    # What was said of an earlier frame is no answer about a later obstacle.
    assert asked.answer(12.5) is None
    assert asked.log[-1]["side"] == -1 and asked.log[-1]["error"] is None


def test_one_question_at_a_time_and_none_about_what_is_no_frame():
    go, calls = threading.Event(), []

    def transport(url, model, image):
        calls.append(image)
        go.wait(2.0)
        return reply("A", A=1.0)

    asked = Sides(SERVER, transport=transport)
    assert asked.ask(picture(), 1.0)
    assert not asked.ask(picture(), 1.1)
    go.set()
    assert waited(asked) and len(calls) == 2
    for bad in (None, np.zeros((10, 10, 3), np.uint8), "frame"):
        assert not asked.ask(bad, 2.0)
    assert not Sides([], transport=transport).ask(picture(), 3.0)
    assert len(calls) == 2


def test_a_server_that_fails_leaves_no_answer_and_the_next_question_can_be_asked():
    def transport(url, model, image):
        raise OSError("unreachable")

    asked = Sides(SERVER, transport=transport)
    assert asked.ask(picture(), 1.0) and waited(asked)
    assert asked.answer(0.0) is None and "OSError" in asked.log[-1]["error"]
    assert asked.ask(picture(), 2.0) and waited(asked)


def test_a_session_without_a_judge_asks_nobody(monkeypatch):
    monkeypatch.setattr(sides, "_active", None)
    assert sides.use([]) is None and sides.active() is None
    assert sides.use(SERVER) is sides.active() and isinstance(sides.active(), Sides)
    with pytest.raises(ValueError):
        sides.use(["http://example.com=model"])
