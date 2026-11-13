"""Scripted landings and stairs; no model or console is contacted."""

from dataclasses import replace

import numpy as np
import pytest

from pilot import ahead, sides
from pilot.ahead import View
from pilot.contract import NEUTRAL_PAD, Observation, Reading
from pilot.descend import Descend
from pilot.wayround import WayRound


def place(name):
    return View(where=tuple(float(value == name) for value in ahead.PLACES))


class Asker:
    def __init__(self, *views, silent=False):
        self.views = list(views)
        self.silent = silent
        self.calls = []
        self.answers = []

    def ask(self, frame, capture, **kwargs):
        self.calls.append((capture, kwargs))
        return True

    def answer(self, capture):
        self.answers.append(capture)
        if self.silent:
            return None
        return self.views[min(len(self.calls) - 1, len(self.views) - 1)]


@pytest.fixture(autouse=True)
def no_models(monkeypatch):
    monkeypatch.setattr(ahead, "active", lambda: None)
    monkeypatch.setattr(ahead, "place", lambda: None)
    monkeypatch.setattr(sides, "active", lambda: None)


def tick(now, **changes):
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame[0, :8, 0] = np.frombuffer(np.float64(now).tobytes(), dtype=np.uint8)
    return replace(
        Observation(Reading("flat", "none", None, None, None, False, 1.0), True, now, frame=frame),
        **changes,
    )


def skill(monkeypatch, *places, stairs=None, duration=40, silent=False):
    model = Asker(*(places or (place("landing"),)), silent=silent)
    monkeypatch.setattr(ahead, "place", lambda: model)
    monkeypatch.setattr(ahead, "active", lambda: stairs)
    return Descend({"duration": duration}), model


def step(walk, now, **changes):
    result = walk.step(tick(now, **changes))
    assert not {"square", "cross", "ps", "create"}.intersection(
        button.lower() for button in result.pad.buttons
    )
    if result.status != "running":
        assert result.pad == NEUTRAL_PAD
    return result


def ended(walk, result, status, reason):
    assert (result.status, result.reason, result.pad) == (status, reason, NEUTRAL_PAD)
    assert walk.step(tick(1000)) is result
    assert walk.stop("replaced") is result


def test_missing_asker_waits_for_valid_tick_then_fails():
    walk = Descend({})
    assert step(walk, 0, reading=None).status == "running"
    ended(walk, step(walk, 0.1), "failed", "place-unread")


def test_eight_valid_seconds_without_a_place(monkeypatch):
    walk, model = skill(monkeypatch, silent=True)
    for index in range(80):
        assert step(walk, index / 10).status == "running"
    ended(walk, step(walk, 8), "failed", "place-unread")
    assert all(kwargs == {"where": True} for _, kwargs in model.calls)


@pytest.mark.parametrize("name,status,reason", [("street", "done", "street"), ("room", "failed", "in-room")])
def test_place_at_start(monkeypatch, name, status, reason):
    walk, model = skill(monkeypatch, place(name))
    for now in (0, 0.1, 0.3, 0.6):
        assert step(walk, now).pad == NEUTRAL_PAD
    ended(walk, step(walk, 0.7), status, reason)
    assert len(model.calls) == 2


def test_stairs_scan_turns_each_view_and_only_asks_stairs():
    model = Asker(View(exit=0))
    guard = WayRound(climb=False, ahead=model)
    guard.descend(tick(0))
    turns = []
    for index in range(160):
        now = index / 10
        steer = guard.step(tick(now), guard.AHEAD)
        assert not steer.buttons
        if steer.right[0]:
            turns.append((now, steer.right[0]))
        if "wall" in guard.views:
            break
    assert len(model.calls) == guard.LOOKS + 1
    assert len(turns) >= guard.LOOKS
    assert all(kwargs == {"indoors": False, "ahead": False, "stairs": True} for _, kwargs in model.calls)
    assert "wall" in guard.views
    assert all(b[0] - a[0] >= guard.LOOK_SETTLE for a, b in zip(model.calls, model.calls[1:], strict=False))
    pads = [guard.step(tick(now + offset / 10), guard.AHEAD) for offset in range(1, 21)]
    assert any(pad.left == guard.AHEAD for pad in pads)
    assert all(not pad.buttons for pad in pads)


def test_stairs_left_then_run_and_watch_nudges_right():
    model = Asker(View(exit=1, parts=(1, 0, 0)), View(exit=1, parts=(0, 0, 1)))
    guard = WayRound(climb=False, ahead=model)
    guard.descend(tick(0))
    assert guard.step(tick(0.1), guard.AHEAD).left == (0, 0)
    steer = guard.step(tick(0.3), guard.AHEAD)
    assert steer.left == (0, 0) and steer.right == (-1, 0)
    assert guard.step(tick(0.4), guard.AHEAD).right == (-1, 0)
    assert guard.step(tick(0.5), guard.AHEAD).left == guard.AHEAD
    guard.step(tick(1.0), guard.AHEAD)
    steer = guard.step(tick(1.1), guard.AHEAD)
    assert steer.left == guard.AHEAD and steer.right == (1, 0)
    assert all(kwargs == {"indoors": False, "ahead": False, "stairs": True} for _, kwargs in model.calls)
    assert guard.outside is None


@pytest.mark.parametrize("model", [None, Asker(View(exit=0), silent=True)])
def test_no_stairs_answer_uses_edges(model):
    guard = WayRound(climb=False, ahead=model)
    guard.descend(tick(0))
    # A view without an answer is looked at a second time before the edges are felt for.
    pads = [guard.step(tick(index / 10), guard.AHEAD) for index in range(1, 80)]
    assert "wall" in guard.views
    assert any(pad.left == guard.AHEAD for pad in pads)
    assert all(not pad.buttons for pad in pads)


def test_street_confirmation_walks_clear_then_finishes(monkeypatch):
    walk, _ = skill(monkeypatch, place("landing"), place("landing"), place("street"))
    clear_at = None
    for index in range(60):
        now = index / 10
        result = step(walk, now)
        if walk.clear is not None:
            clear_at = walk.clear if clear_at is None else clear_at
            if result.status == "running":
                assert result.pad.left == walk.guard.AHEAD
                assert result.pad.right == (0, 0)
        if result.status != "running":
            break
    assert clear_at is not None and now - clear_at >= walk.guard.CLEAR
    ended(walk, result, "done", "street")


def test_one_street_followed_by_landing_never_finishes(monkeypatch):
    walk, _ = skill(monkeypatch, place("landing"), place("landing"), place("street"), place("landing"))
    for index in range(60):
        assert step(walk, index / 10).status == "running"
        assert walk.clear is None


def test_room_after_start_fails(monkeypatch):
    walk, _ = skill(monkeypatch, place("landing"), place("landing"), place("room"))
    for index in range(40):
        result = step(walk, index / 10)
        if result.status != "running":
            break
    ended(walk, result, "failed", "entered-room")


def test_time_limit(monkeypatch):
    walk, _ = skill(monkeypatch, duration=5)
    for index in range(50):
        assert step(walk, index / 10).status == "running"
    ended(walk, step(walk, 5), "failed", "time-limit")


def test_guard_exhaustion_is_no_stairs(monkeypatch):
    walk, _ = skill(monkeypatch)
    # Shorten the edge budget to exercise its exhaustion before the skill's hard limit.
    monkeypatch.setattr(walk.guard, "WALL_TURNS", 2)
    for index in range(200):
        result = step(walk, index / 10, moving=False)
        if result.status != "running":
            break
    ended(walk, result, "failed", "no-stairs")


@pytest.mark.parametrize(
    "args",
    [
        None,
        [],
        {"other": 1},
        {"duration": True},
        {"duration": "5"},
        {"duration": float("nan")},
        {"duration": float("inf")},
    ],
)
def test_bad_parameters(args):
    with pytest.raises(ValueError):
        Descend(args)


def test_parameter_contract_and_stop():
    assert Descend({}).limit == 40
    assert Descend({"duration": 1}).limit == 5
    assert Descend({"duration": 99}).limit == 60
    assert Descend.name == "descend"
    assert Descend.parameters == {"duration": (5.0, 60.0, 40.0)}
    assert 0 < len(Descend.prompt) <= 400
    walk = Descend({})
    ended(walk, walk.stop("interrupted"), "failed", "interrupted")


@pytest.mark.parametrize(
    "bad",
    [
        {"time": None},
        {"time": True},
        {"time": "later"},
        {"time": float("nan")},
        {"time": float("inf")},
        {"time": 0.1},
        {"time": 0.0},
        {"time": 1.2},
        {"reading": None},
        {"reading": replace(tick(0).reading, corrupt=True)},
        {"reading": replace(tick(0).reading, confidence=0.5)},
        {"reading": replace(tick(0).reading, confidence=float("nan"))},
        {"reading": replace(tick(0).reading, minimap="tilted")},
        {"mode": "vehicle"},
        {"frame": None},
        {"frame": "not a picture"},
        {"frame": np.zeros((10, 10, 3), dtype=np.uint8)},
        {"frame": np.zeros((720, 1280, 3), dtype=float)},
        {"frame": tick(0.1).frame},
    ],
    ids=[
        "missing-time",
        "bool-time",
        "text-time",
        "nan-time",
        "infinite-time",
        "repeated-time",
        "backward-time",
        "gap",
        "missing-map",
        "corrupt-map",
        "low-confidence",
        "nan-confidence",
        "tilted-map",
        "not-foot",
        "missing-frame",
        "text-frame",
        "wrong-size",
        "wrong-dtype",
        "repeated-frame",
    ],
)
def test_invalid_tick_is_neutral_and_breaks_place_confirmation(monkeypatch, bad):
    walk, model = skill(monkeypatch, place("street"))
    step(walk, 0)
    assert step(walk, 0.1).status == "running"
    result = walk.step(replace(tick(0.2), **bad))
    assert result.pad == NEUTRAL_PAD and result.status == "running"
    assert len(model.calls) == 1
    # Re-establish after even the gap case; a single new answer must not finish.
    assert step(walk, 1.3).status == "running"
    assert step(walk, 1.4).status == "running"
    assert step(walk, 1.5).status == "running"
    assert walk.clear is None


@pytest.mark.parametrize(
    "bad_view",
    [
        View(),
        View(where=(0.2, 0.25, 0.55)),
        View(where=(0, 0, 1), error="bad"),
        View(where=(0, float("nan"), 1)),
    ],
)
def test_unreadable_answers_break_consecutive_places(monkeypatch, bad_view):
    walk, _ = skill(monkeypatch, place("street"), bad_view, place("street"), place("landing"))
    for index in range(40):
        assert step(walk, index / 10).status == "running"


def test_threshold_is_inclusive(monkeypatch):
    walk, _ = skill(monkeypatch, View(where=(0.2, 0.2, 0.6)))
    for now in (0, 0.1, 0.6):
        assert step(walk, now).status == "running"
    ended(walk, step(walk, 0.7), "done", "street")


def test_place_requests_are_spaced_and_each_answer_consumed_once(monkeypatch):
    walk, model = skill(monkeypatch)
    for index in range(60):
        step(walk, index / 10)
    assert len(model.calls) > 5
    assert all(kwargs == {"where": True} for _, kwargs in model.calls)
    assert all(b[0] - a[0] >= 0.6 for a, b in zip(model.calls, model.calls[1:], strict=False))
    assert len(model.answers) == len(set(model.answers))


def test_pending_place_is_not_replaced_and_late_answer_does_not_count(monkeypatch):
    walk, model = skill(monkeypatch, place("street"), silent=True)
    for index in range(20):
        assert step(walk, index / 10).status == "running"
    assert len(model.calls) == 1
    model.silent = False
    assert step(walk, 2).status == "running"
    assert step(walk, 2.1).status == "running"
    assert len(model.calls) == 2
    assert step(walk, 2.6).status == "running"
    ended(walk, step(walk, 2.7), "done", "street")


def test_invalid_ticks_do_not_spend_the_eight_valid_seconds(monkeypatch):
    walk, _ = skill(monkeypatch, silent=True)
    for index in range(100):
        result = step(walk, index / 10, reading=None) if index % 2 else step(walk, index / 10)
        assert result.status == "running"
    for index in range(100, 180):
        assert step(walk, index / 10).status == "running"
    ended(walk, step(walk, 18.0), "failed", "place-unread")


@pytest.mark.parametrize("interrupt", ["frame", "landing", "unreadable"])
def test_street_must_stay_clear_after_confirmation(monkeypatch, interrupt):
    walk, model = skill(monkeypatch, place("landing"), place("landing"), place("street"))
    for index in range(30):
        now = index / 10
        assert step(walk, now).status == "running"
        if walk.clear is not None:
            break
    assert walk.clear is not None
    if interrupt == "frame":
        assert step(walk, now + 0.1, frame=None).pad == NEUTRAL_PAD
        assert walk.clear is None
        model.views = [place("landing")]
    else:
        model.views = [place("landing") if interrupt == "landing" else View(error="unreadable")]
    for offset in range(2, 25):
        assert step(walk, now + offset / 10).status == "running"
    assert walk.clear is None


@pytest.mark.parametrize("method", ["leave", "enter", "leave_heading"])
def test_other_search_modes_still_ask_their_own_question(method):
    model = Asker(View(exit=1, parts=(0, 1, 0), indoors=1))
    guard = WayRound(climb=False, ahead=model)
    guard.descend(tick(0))
    if method == "leave_heading":
        guard.leave_heading(tick(0), 0)
        guard.step(tick(0.1), guard.AHEAD)
        guard.step(tick(0.7), guard.AHEAD)
    else:
        getattr(guard, method)(tick(0))
        guard.step(tick(0.3), guard.AHEAD)
    assert model.calls
    assert all(not kwargs.get("stairs") for _, kwargs in model.calls)


@pytest.mark.parametrize("view", [View(exit=1, parts=(0, 0, 1), error="bad"), View(exit=0, parts=(0, 0, 1))])
def test_unreadable_or_empty_stairs_do_not_nudge(view):
    model = Asker(View(exit=1, parts=(0, 1, 0)), view)
    guard = WayRound(climb=False, ahead=model)
    guard.descend(tick(0))
    guard.step(tick(0.3), guard.AHEAD)
    guard.step(tick(1.0), guard.AHEAD)
    assert guard.step(tick(1.1), guard.AHEAD).right == (0, 0)


def test_a_look_back_through_the_door_is_not_a_step_into_the_room(monkeypatch):
    # The search stands and turns; a picture of the room behind the open door is not the figure's
    # place while the stick has not been pushed.
    stairs = Asker(View(exit=0.0))
    walk, _ = skill(monkeypatch, place("landing"), place("landing"), place("room"), stairs=stairs)
    results = [step(walk, index / 10) for index in range(26)]
    assert all(result.status == "running" for result in results)
    assert all(result.pad.left == (0, 0) for result in results)
