"""What the model sees in a view, asked about one frame at a time and never on the tick's way."""

import base64
import threading
import time

import cv2
import numpy as np
import pytest
from test_sides import SERVER, reply

from pilot import ahead
from pilot.ahead import Ahead, View


def frame(value=90):
    return np.full((720, 1280, 3), value, np.uint8)


def waited(asked):
    deadline = time.monotonic() + 2.0
    while asked.busy and time.monotonic() < deadline:
        time.sleep(0.001)
    return not asked.busy


class Model:
    """Answers each question by its wording; keeps what it was shown."""

    def __init__(self, indoors, *, opened=0.04, exits=(0.0,)):
        self.indoors, self.opened, self.exits, self.seen = indoors, opened, list(exits), []

    def __call__(self, url, model, image, question):
        picture = cv2.imdecode(np.frombuffer(base64.b64decode(image), np.uint8), cv2.IMREAD_COLOR)
        self.seen.append((question, picture.shape[1]))
        if question == ahead.INDOORS:
            share = self.indoors
        elif question == ahead.QUESTION:
            share = self.opened
        else:
            share = self.exits.pop(0)
        return reply("A" if share >= 0.5 else "B", A=max(share, 1e-6), B=max(1 - share, 1e-6))


def test_outdoors_the_way_straight_ahead_is_asked_about_and_the_answer_belongs_to_its_frame():
    model = Model(0.01)
    asked = Ahead(SERVER, transport=model)
    assert asked.answer(0.0) is None
    assert asked.ask(frame(), 12.0) and waited(asked)
    assert model.seen == [(ahead.INDOORS, ahead.WIDTH), (ahead.QUESTION, ahead.WIDTH)]
    view = asked.answer(12.0)
    assert view.open == pytest.approx(0.04, abs=1e-3) and view.indoors == pytest.approx(0.01, abs=1e-3)
    assert view.exit is None and view.parts is None and view.error is None
    # What was said of an earlier view is no answer about a later one.
    assert asked.answer(12.5) is None and asked.log[-1]["open"] == pytest.approx(0.04, abs=1e-3)
    # A place that is known is not asked for again, nor a way the feet have judged.
    model.seen.clear()
    assert asked.ask(frame(), 13.0, indoors=False, ahead=False) and waited(asked)
    assert model.seen == [] and asked.answer(13.0) == View()


def test_in_a_room_the_way_out_is_asked_for_and_then_which_part_of_the_picture_it_is_in():
    model = Model(0.99, exits=[0.97, 0.9, 0.2, 0.0])
    asked = Ahead(SERVER, transport=model)
    assert asked.ask(frame(), 1.0) and waited(asked)
    whole, part = ahead.EXIT.format(what="a screenshot"), ahead.EXIT.format(what="part of a screenshot")
    assert [question for question, _ in model.seen] == [ahead.INDOORS, whole, part, part, part]
    assert [width for _, width in model.seen[2:]] == [ahead.PART_WIDTH] * 3
    view = asked.answer(1.0)
    assert view.open is None and view.exit == pytest.approx(0.97, abs=1e-3)
    assert view.parts == pytest.approx((0.9, 0.2, 0.0), abs=1e-3)
    # No way out in the picture: its parts are not asked about.
    model = Model(0.99, exits=[0.02])
    asked = Ahead(SERVER, transport=model)
    assert asked.ask(frame(), 2.0, indoors=True) and waited(asked)
    assert len(model.seen) == 1 and asked.answer(2.0).parts is None


def test_entrance_asks_for_an_outside_door_and_its_picture_part():
    model = Model(0.01, exits=[0.97, 0.1, 0.2, 0.98])
    asked = Ahead(SERVER, transport=model)
    assert asked.ask(frame(), 1.0, indoors=False, ahead=False, entrance=True) and waited(asked)
    whole = ahead.ENTRANCE.format(what="a screenshot")
    part = ahead.ENTRANCE.format(what="part of a screenshot")
    assert [question for question, _ in model.seen] == [whole, part, part, part]
    assert asked.answer(1.0).parts == pytest.approx((0.1, 0.2, 0.98), abs=1e-3)


def test_one_frame_at_a_time_and_none_that_is_no_frame():
    go, calls = threading.Event(), []

    def transport(url, model, image, question):
        calls.append(question)
        go.wait(2.0)
        return reply("B", A=0.01, B=0.99)

    asked = Ahead(SERVER, transport=transport)
    assert asked.ask(frame(), 1.0) and not asked.ask(frame(), 1.1)
    go.set()
    assert waited(asked) and len(calls) == 2
    for bad in (None, np.zeros((10, 10, 3), np.uint8), "frame"):
        assert not asked.ask(bad, 2.0)
    assert not Ahead([], transport=transport).ask(frame(), 3.0)


def test_a_server_that_fails_answers_with_its_error_and_the_next_frame_can_be_asked_about():
    def transport(url, model, image, question):
        raise OSError("unreachable")

    asked = Ahead(SERVER, transport=transport)
    assert asked.ask(frame(), 1.0) and waited(asked)
    view = asked.answer(1.0)
    assert view.open is None and view.indoors is None and "OSError" in view.error
    assert asked.ask(frame(), 2.0) and waited(asked)


def test_a_walk_asks_for_the_place_alone_and_keeps_an_asker_of_its_own_for_it(monkeypatch):
    # Once a second while the figure runs: one question, whatever the place is.
    for share in (0.99, 0.02):
        model = Model(share, exits=(1.0, 1.0, 1.0, 1.0))
        asked = Ahead(SERVER, transport=model)
        assert asked.ask(frame(), 4.0, ahead=False, exit=False) and waited(asked)
        assert model.seen == [(ahead.INDOORS, ahead.WIDTH)]
        view = asked.answer(4.0)
        assert view.indoors == pytest.approx(share, abs=1e-3) and view.exit is None and view.open is None
    # Its answers and the guard's are kept apart: each asker has its one frame.
    monkeypatch.setattr(ahead, "_active", None)
    monkeypatch.setattr(ahead, "_place", None)
    ahead.use(SERVER)
    assert isinstance(ahead.place(), Ahead) and ahead.place() is not ahead.active()


def test_a_session_without_a_judge_asks_nobody(monkeypatch):
    monkeypatch.setattr(ahead, "_active", None)
    monkeypatch.setattr(ahead, "_place", None)
    assert ahead.use([]) is None and ahead.active() is None and ahead.place() is None
    assert ahead.use(SERVER) is ahead.active() and isinstance(ahead.active(), Ahead)


def striped():
    """A frame whose three parts are told apart by how bright they are."""
    picture = np.zeros((720, 1280, 3), np.uint8)
    picture[:, :450], picture[:, 450:830], picture[:, 830:] = 20, 120, 230
    return picture


class Staircase:
    """Stairs in the middle and the right part of the picture; `up` says which of them lead up."""

    def __init__(self, up):
        self.up, self.asked = up, []

    def __call__(self, url, model, image, question):
        picture = cv2.imdecode(np.frombuffer(base64.b64decode(image), np.uint8), cv2.IMREAD_COLOR)
        whole = picture.shape[1] == ahead.WIDTH
        part = "whole" if whole else "LMR"[int(np.digitize(picture.mean(), (70, 170)))]
        way = question in {ahead.WAY.format(what=what) for what in ("a screenshot", "part of a screenshot")}
        self.asked.append((part, "way" if way else "stairs"))
        share = float(part in self.up) if way else float(part != "L")
        return reply("A" if share >= 0.5 else "B", A=max(share, 1e-6), B=max(1 - share, 1e-6))


def test_stairs_that_lead_up_are_no_way_down():
    # 13 November, 16:00: on the half landing of an outside staircase the model said yes to the
    # flight that led back up to the door, and the figure ran up it into the apartment it had left.
    model = Staircase(up="M")
    asked = Ahead(SERVER, transport=model)
    assert asked.ask(striped(), 1.0, indoors=False, ahead=False, stairs=True) and waited(asked)
    view = asked.answer(1.0)
    assert view.exit == pytest.approx(1.0, abs=1e-3)
    assert view.parts == pytest.approx((0.0, 0.0, 1.0), abs=1e-3)
    # A part without stairs is not asked which way they lead.
    assert ("L", "way") not in model.asked and ("M", "way") in model.asked
    model = Staircase(up="MR")
    asked = Ahead(SERVER, transport=model)
    assert asked.ask(striped(), 2.0, indoors=False, ahead=False, stairs=True) and waited(asked)
    view = asked.answer(2.0)
    assert view.exit == 0.0 and max(view.parts) < 1e-3


def test_what_holds_the_figure_up_is_asked_about_alone():
    seen = []

    def transport(url, model, image, question):
        seen.append(question)
        return reply("A", A=0.8, B=0.2)

    asked = Ahead(SERVER, transport=transport)
    assert asked.ask(frame(), 3.0, low=True) and waited(asked)
    assert seen == [ahead.LOW]
    view = asked.answer(3.0)
    assert view.low == pytest.approx(0.8, abs=1e-3) and view.exit is None and view.where is None
