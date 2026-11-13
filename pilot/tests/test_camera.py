import argparse
import importlib.util
import json
import math
from collections import Counter
from concurrent.futures import Future
from dataclasses import replace
from pathlib import Path
from typing import ClassVar

import numpy as np
import pytest

from pilot import cli
from pilot.camera import (
    SetFarView,
    StartupCamera,
    ViewBand,
    ViewReading,
    Watch,
    read_observation,
    read_tilt,
    read_view,
    startup_plan,
)
from pilot.conductor import Conductor
from pilot.contract import Detection, Hud, Observation, Pad, Reading, SkillResult
from pilot.head import SkillCall, parse_response
from pilot.skills import REGISTRY, SkillRunner, make_skill

LAB = Path(__file__).resolve().parents[2] / "lab/camera"
FRAME = np.zeros((720, 1280, 3), dtype=np.uint8)
FLAT = Reading("flat", "none", None, None, 0.0, False, 0.9)
TILTED = Reading("tilted", "none", None, None, 0.0, False, 0.9)


def figure(height, feet, *, cx=0.46, aspect=0.4, confidence=0.93, shape=(720, 1280)):
    h, w = shape
    box_h = height * h
    box_w = aspect * box_h
    return Detection(
        "person", (cx * w - box_w / 2, feet * h - box_h, cx * w + box_w / 2, feet * h), confidence
    )


# What the sample shows: a far figure stands about 0.28 high with its feet at 0.72, a middle one
# 0.44 and 0.90, a near one 0.58 and cut by the lower edge.
LOOK = {"far": (0.28, 0.72), "middle": (0.44, 0.90), "near": (0.58, 0.995)}


def look(view):
    return figure(*LOOK[view])


# The frames labelled by eye: the confusion table of the reading, as counts.


def evaluation():
    spec = importlib.util.spec_from_file_location("camera_evaluate", LAB / "evaluate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_labelled_frames_are_named_right_or_not_at_all():
    ev = evaluation()
    found = ev.load()
    counts = ev.table(found)
    named = ("far", "middle", "near")
    wrong = sum(counts[v, c] for v in named for c in named if c != v)
    wrong += sum(counts["first", c] for c in named)
    total = sum(counts[v, c] for v in named for c in ev.COLUMNS)
    right = sum(counts[v, v] for v in named)
    assert total == 50 and len(found) == 98
    assert wrong == 0
    assert right >= 0.75 * total  # three of four of the far, middle and near frames
    # No figure in the picture is read as none: all eighteen frames of first person.
    assert counts["first", "none"] == 18 == sum(c for (label, _), c in counts.items() if label == "first")
    # The motorcycle frames of the sample are not read.
    sample = json.loads((LAB / "sample/labels.json").read_text())["frames"]
    stored = json.loads((LAB / "sample/detections.json").read_text())
    riders = [item["n"] for item in sample if item.get("why") == "on a motorcycle"]
    assert len(riders) == 4
    for n in riders:
        assert ev.read(ev.detections(stored[str(n)])).view not in {"far", "middle", "near"}


def test_the_bands_hold_for_a_recording_they_were_not_fitted_on():
    ev = evaluation()
    found = ev.load()
    held = Counter()
    for group in {g for g, _, _ in found}:
        bands = {"foot": ev.fit([item for item in found if item[0] != group])}
        held += ev.table([item for item in found if item[0] == group], bands)
    named = ("far", "middle", "near")
    assert sum(held[v, c] for v in named for c in named if c != v) == 0
    assert sum(held[v, v] for v in named) >= 0.75 * sum(held[v, c] for v in named for c in ev.COLUMNS)


@pytest.mark.parametrize("view", LOOK)
def test_each_view_is_read_at_any_frame_size(view):
    for shape in ((720, 1280), (360, 640), (1080, 1920)):
        assert read_view(figure(*LOOK[view], shape=shape), shape).view == view


def test_no_figure_is_none_and_a_figure_between_the_bands_is_unknown():
    assert read_view(None, FRAME.shape) == ViewReading("none", "no-figure")
    # Between far (0.345) and middle (0.38) the figure is on its way, or pushed, and is named nothing.
    assert read_view(figure(0.36, 0.84), FRAME.shape).view == "unknown"
    assert read_view(figure(0.50, 0.99), FRAME.shape).view == "unknown"
    assert read_view(figure(0.28, 0.72), (10, 10)).reason == "invalid-frame"


@pytest.mark.parametrize(
    "box",
    [
        figure(0.28, 0.72, cx=0.83),  # at the edge, where an onlooker stands
        figure(0.28, 0.72, aspect=1.2),  # lying, or seen from a side that no band knows
        figure(0.28, 0.72, confidence=0.7),  # the detector is not sure of it
        Detection("person", (590, float("nan"), 650, 500), 0.93),
        Detection("person", (590, 300, 580, 500), 0.93),
        Detection("person", (590, 300, 650, 900), 0.93),
    ],
)
def test_a_figure_that_does_not_fit_is_not_named(box):
    assert read_view(box, FRAME.shape).view == "unknown"


def test_a_rider_is_not_read_and_a_pedestrian_in_front_of_a_truck_is():
    person = look("far")
    x0, y0, x1, y1 = person.box
    under = Detection("motorcycle", (x0 - 10, y0 + 120, x1 + 30, y1 + 40), 0.8)
    assert read_view(person, FRAME.shape, vehicles=(under,)).view == "rider"
    quad = Detection("car", (x0 - 20, y0 + 80, x1 + 40, y1 + 20), 0.8)  # a quad the detector calls a car
    assert read_view(person, FRAME.shape, vehicles=(quad,)).view == "rider"
    truck = Detection("truck", (x0 - 300, y0 - 80, x1 + 400, y1 + 60), 0.9)
    assert read_view(person, FRAME.shape, vehicles=(truck,)).view == "far"
    behind = Detection(
        "car", (x0 - 60, y0 - 40, x1 + 160, y1 - 30), 0.9
    )  # further off: its wheels stand higher
    assert read_view(person, FRAME.shape, vehicles=(behind,)).view == "far"
    beside = Detection("motorcycle", (x1 + 40, y0 + 60, x1 + 240, y1 - 10), 0.9)
    assert read_view(person, FRAME.shape, vehicles=(beside,)).view == "far"


def test_an_observation_is_read_with_the_vehicles_and_people_of_its_detections():
    person = look("far")
    x0, y0, x1, y1 = person.box
    bike = Detection("motorcycle", (x0 - 10, y0 + 120, x1 + 30, y1 + 40), 0.8)
    onlooker = look("far")
    base = Observation(FLAT, False, 1.0, frame=FRAME, hud=Hud(), figure=person)
    assert read_observation(base).view == "far"
    assert read_observation(replace(base, objects=(bike,))).view == "rider"
    assert read_observation(replace(base, figure_vehicle=bike)).view == "rider"
    assert read_observation(replace(base, objects=(onlooker,))).view == "unknown"
    assert read_observation(replace(base, frame=None)).view == "far"  # the frame is the usual one


def test_a_second_person_where_the_figure_stands_makes_it_unreadable():
    assert read_view(look("far"), FRAME.shape, others=(look("far"),)).view == "unknown"
    far_off = figure(0.1, 0.55, cx=0.2)
    assert read_view(look("far"), FRAME.shape, others=(far_off,)).view == "far"


def test_a_mode_without_bands_reads_unknown_and_takes_its_own_when_given():
    assert read_view(look("far"), FRAME.shape, mode="car").reason == "uncalibrated-mode:car"
    bands = {"car": (ViewBand("far", (0.27, 0.29), (0.7, 0.74)),)}
    assert read_view(look("far"), FRAME.shape, mode="car", calibrations=bands).view == "far"


def test_a_view_is_named_over_half_a_second_and_not_by_one_reading():
    watch = Watch()
    far, near, none = ViewReading("far"), ViewReading("near"), ViewReading("none")
    for stamp in (0.0, 0.1, 0.2, 0.3, 0.4):
        watch.add(stamp, far)
        assert watch.view() is None
    watch.add(0.5, far)
    assert watch.view() == "far"
    watch.add(0.6, near)  # one reading of another view within the second, and none is named
    assert watch.view() is None
    for stamp in (0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7):
        watch.add(stamp, far)
    assert watch.view() == "far"  # a second later it is far again
    watch.reset()
    for stamp in (0.0, 0.2, 0.4, 0.6):
        watch.add(stamp, none)
    assert watch.view() is None and math.isclose(watch.hidden(), 0.6)
    watch.add(0.8, ViewReading("unknown"))
    assert watch.hidden() == 0.0 and watch.figure_seen()


# A model of the game's camera, as the touchpad steps it: far, first person, near, middle. The
# picture needs more than a second to follow a press, a press now and then is lost, the figure is
# hidden for a while, and after a press the camera may look at the figure from the front until a
# step forward swings it behind.


class Game:
    CYCLE = ("far", "first", "near", "middle")
    FOLLOW = 1.2

    def __init__(self, view, *, lose=(), hidden=(), front_after_press=False, swing=True):
        self.view, self.lose, self.hidden = view, set(lose), tuple(hidden)
        self.front_after_press, self.swing = front_after_press, swing
        self.presses = 0
        self.changes = [(-math.inf, view, view)]
        self.front = False
        self.walked = 0.0
        self.mode = lambda t: "foot"

    def press(self, t):
        self.presses += 1
        if self.presses in self.lose:
            return
        old = self.view
        self.view = self.CYCLE[(self.CYCLE.index(old) + 1) % 4]
        self.changes.append((t, old, self.view))
        self.front = self.front_after_press and self.view != "first"
        self.walked = 0.0

    def walk(self, dt):
        self.walked += dt
        if self.walked >= 0.3 and self.swing:
            self.front = False

    def seen(self, t):
        """The figure the camera shows at time t, as a detector would box it."""
        if any(a <= t < b for a, b in self.hidden):
            return None
        at, old, new = max((c for c in self.changes if c[0] <= t), key=lambda c: c[0])
        if t - at < self.FOLLOW:  # the picture is still the old one
            return None if old == "first" else look(old)
        if new == "first":
            return None
        return figure(0.5, 0.9, aspect=1.3) if self.front else look(new)


def observation(t, game, **changes):
    stamp = max(0.0, math.floor(t * 10) / 10 - 0.1)  # ten detections a second, a tenth late
    base = Observation(
        FLAT,
        False,
        t,
        frame=FRAME,
        objects=(),
        objects_time=stamp,
        hud=Hud(),
        mode=game.mode(t),
        figure=game.seen(stamp),
    )
    return replace(base, **changes)


def run(game, skill=None, *, seconds=45, hz=30, **changes):
    skill = SetFarView({}) if skill is None else skill
    rows, held, dt = [], None, 1 / hz
    for index in range(int(seconds * hz)):
        t = index * dt
        result = skill.step(observation(t, game, **changes))
        down = result.pad.buttons == ("touchpad",)
        if down and held is None:
            held = t
            game.press(t)
        elif not down and held is not None:
            rows.append(("pulse", held, t))
            held = None
        if result.pad.left == (0.0, -1.0):
            game.walk(dt)
        rows.append(("tick", t, result))
        if result.status != "running":
            return skill, rows, t
    pytest.fail("the skill did not end")


def pulses(rows):
    return [(a, b) for kind, a, b in rows if kind == "pulse"]


def pads(rows):
    return [r.pad for kind, _, r in rows if kind == "tick"]


@pytest.mark.parametrize("start,presses", [("far", 0), ("middle", 1), ("near", 2), ("first", 3)])
def test_the_loop_ends_in_the_far_view_from_each_view(start, presses):
    game = Game(start)
    skill, rows, end = run(game)
    last = rows[-1][2]
    assert last.status == "done" and last.reason == f"far; presses={presses}" and last.pad == Pad()
    assert game.view == "far" and game.presses == presses == skill.presses
    assert end < 20


def test_a_press_is_a_pulse_of_a_tenth_and_the_picture_settles_before_it_is_read_again():
    game = Game("near")
    _, rows, _ = run(game)
    shots = pulses(rows)
    assert len(shots) == 2
    for a, b in shots:
        assert 0.09 <= b - a <= 0.14
    # 1.5 s of settling and then half a second of readings, before the next press
    assert shots[1][0] - shots[0][1] >= 1.5 + 0.5
    assert set(pads(rows)) <= {Pad(), Pad(buttons=("touchpad",))}


def test_a_lost_press_is_seen_and_pressed_again():
    game = Game("near", lose={1})
    _, rows, _ = run(game)
    assert rows[-1][2].status == "done" and game.view == "far" and game.presses == 3


def test_a_figure_seen_from_the_front_gets_a_short_step_and_is_then_read():
    game = Game("near", front_after_press=True)
    skill, rows, _ = run(game)
    assert rows[-1][2].reason == "far; presses=2" and skill.steps == 2
    # one step after each press: the stick is forward for about 0.4 s each time
    forward = [t for kind, t, r in rows if kind == "tick" and r.pad == Pad(left=(0.0, -1.0))]
    runs, current = [], []
    for t in forward:
        if current and t - current[-1] > 0.1:
            runs.append(current)
            current = []
        current.append(t)
    runs.append(current)
    assert len(runs) == 2 and all(0.3 <= r[-1] - r[0] + 1 / 30 <= 0.5 for r in runs)
    assert set(pads(rows)) == {Pad(), Pad(buttons=("touchpad",)), Pad(left=(0.0, -1.0))}


def test_a_figure_that_stays_unreadable_ends_the_skill_with_what_it_saw():
    game = Game("middle", front_after_press=True, swing=False)
    game.front = True  # it begins in front of the figure, and no step swings it
    skill, rows, end = run(game)
    last = rows[-1][2]
    assert last.status == "failed" and last.reason == "view-unknown; last=unknown; presses=0"
    assert skill.steps == 1 and end < 6


def test_a_figure_hidden_for_a_while_is_pressed_around_and_found():
    game = Game("far", hidden=[(0.0, 3.0)])
    _, rows, _ = run(game)
    assert rows[-1][2].status == "done" and game.view == "far"
    assert 1 <= game.presses <= 5


def test_a_figure_hidden_all_the_time_ends_after_four_presses_and_does_not_go_round_again():
    game = Game("far", hidden=[(0.0, math.inf)])
    _, rows, end = run(game)
    last = rows[-1][2]
    assert last.status == "failed" and last.reason == "no-figure; last=none; presses=4"
    assert game.presses == 4 and last.pad == Pad() and end < 30


def test_never_more_than_five_presses():
    game = Game("near", lose=set(range(1, 20)))
    _, rows, end = run(game)
    last = rows[-1][2]
    assert last.status == "failed" and last.reason == "five-presses; last=near; presses=5"
    assert game.presses == 5 and last.pad == Pad() and end < 20


def test_a_hard_time_limit_and_the_longest_a_default_run_can_be():
    game = Game("near", lose=set(range(1, 20)))
    _, rows, end = run(game, SetFarView({"duration": 8}))
    assert rows[-1][2].reason.startswith("time-limit") and 8 <= end < 8.1 and rows[-1][2].pad == Pad()
    assert SetFarView({"duration": 100}).limit == 40 and SetFarView({"duration": 1}).limit == 8
    assert SetFarView({}).limit == 30
    # A figure that flickers in and out of every view cannot keep it past the limit either.
    flicker = Game("near", hidden=[(i * 0.7, i * 0.7 + 0.3) for i in range(80)], lose=set(range(1, 20)))
    assert run(flicker)[2] <= 30.1


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"hud": None}, "hud-unread"),
        ({"hud": Hud(screen="pause")}, "screen-pause"),
        ({"hud": Hud(screen="map")}, "screen-map"),
        ({"hud": Hud(screen="phone")}, "screen-phone"),
        ({"hud": Hud(screen="loading")}, "screen-loading"),
        ({"hud": Hud(screen="wasted")}, "screen-wasted"),
        ({"mode": "vehicle"}, "not-on-foot"),
        ({"mode": None, "reading": TILTED}, "not-on-foot"),
        (
            {"figure": look("middle"), "figure_vehicle": Detection("motorcycle", (560, 450, 700, 700), 0.8)},
            "rider",
        ),
    ],
)
def test_never_a_press_where_it_is_not_safe_to_make_one(changes, reason):
    game = Game("near")  # a view it would press at once
    _, rows, end = run(game, **changes)
    assert game.presses == 0 and set(pads(rows)) == {Pad()}
    last = rows[-1][2]
    assert last.status == "failed" and last.reason.startswith(reason) and 3.9 <= end <= 4.2


def test_a_press_waits_for_the_mode_to_have_read_foot_for_a_second():
    game = Game("near")
    game.mode = lambda t: "vehicle" if t < 0.9 else "foot"
    _, rows, _ = run(game)
    assert pulses(rows)[0][0] >= 0.9 + SetFarView.FOOT_FOR - 1 / 30
    assert rows[-1][2].status == "done"


def test_a_screen_that_stops_being_the_game_lets_go_of_a_press():
    game = Game("near")
    skill = SetFarView({})
    t = 0.0
    while skill.presses == 0:
        pressed = skill.step(observation(t, game))
        t += 1 / 30
    assert skill.pulse_until is not None and pressed.pad.buttons == ("touchpad",)
    assert skill.step(observation(t, game, hud=Hud(screen="pause"))).pad == Pad()
    assert skill.pulse_until is None
    # and nothing is read for the 1.5 s the picture needs to settle after it
    after = [skill.step(observation(t + 0.05 + i / 30, game)) for i in range(40)]
    assert all(r.pad == Pad() for r in after) and skill.presses == 1


def test_a_damaged_minimap_tick_decides_nothing_and_does_not_cut_a_press_short():
    game = Game("near")
    skill = SetFarView({})
    t = 0.0
    while skill.presses == 0:
        skill.step(observation(t, game))
        t += 1 / 30
    damaged = replace(FLAT, corrupt=True)
    assert skill.step(observation(t, game, reading=damaged, mode=None)).pad.buttons == ("touchpad",)
    for i in range(20):
        result = skill.step(observation(t + (i + 1) / 30, game, reading=damaged, mode=None))
    assert result.pad == Pad() and skill.pulse_until is None and skill.unsafe_since is None


def test_stale_and_missing_detections_press_nothing():
    for changes in ({"objects_time": 0.0}, {"objects_time": None}, {"objects_time": -9.0}):
        game = Game("near")
        _, rows, end = run(game, **changes)
        assert game.presses == 0 and rows[-1][2].reason.startswith("no-detections")
        assert 1.9 <= end <= 2.7


def test_a_tick_that_comes_late_lets_go_of_the_pad():
    game = Game("near")
    skill = SetFarView({})
    t = 0.0
    while skill.presses == 0:
        skill.step(observation(t, game))
        t += 1 / 30
    assert skill.pulse_until is not None
    assert skill.step(observation(t + 0.5, game)).pad == Pad()
    assert skill.pulse_until is None and skill.settle_until > t + 0.5


def test_a_clock_that_goes_back_ends_it_neutral_and_stop_does_too():
    game = Game("near")
    skill = SetFarView({})
    skill.step(observation(1.0, game))
    result = skill.step(observation(0.5, game))
    assert result.status == "failed" and result.reason == "invalid-clock" and result.pad == Pad()
    assert skill.step(observation(2.0, game)) == result
    stopped = SetFarView({})
    assert stopped.stop("replaced").pad == Pad() and stopped.step(observation(0, game)).status == "failed"


def test_it_is_registered_cannot_be_cut_short_and_tells_the_head_what_it_does_and_when_it_fails():
    assert REGISTRY["set_far_view"] is SetFarView
    assert isinstance(make_skill(SkillCall("set_far_view", {})), SetFarView)
    assert SetFarView.uninterruptible
    assert SetFarView.prompt.count(". ") + 1 <= 2 and "Fails when" in SetFarView.prompt
    for args in (
        None,
        [],
        "duration",
        {"x": 1},
        {"duration": True},
        {"duration": "2"},
        {"duration": math.inf},
    ):
        with pytest.raises(ValueError):
            SetFarView(args)


# The opening of a session, with the real conductor and runner.


class Pending:
    def __init__(self):
        self.jobs = []

    def __call__(self, fn, request):
        future = Future()
        self.jobs.append((future, request))
        return future


class NoEvents:
    def update(self, *args, **kwargs):
        return []


class Stub:
    """A skill that ends after `seconds` with `status`."""

    parameters: ClassVar = {"duration": (1.0, 10.0, 1.0)}
    uninterruptible: ClassVar = True
    prompt = "A stub."
    status = "done"
    seconds = 1.0

    def __init__(self, args):
        self.started = None
        self.limit = 10

    def step(self, obs):
        if self.started is None:
            self.started = obs.time
        if obs.time - self.started >= self.seconds:
            return SkillResult(status=self.status, reason="stub")
        return SkillResult(Pad(right=(0.0, -0.5)))

    def stop(self, reason):
        return SkillResult(status="failed", reason=reason)


def stub(name, status, seconds, **more):
    return type(name, (Stub,), {"name": name, "status": status, "seconds": seconds, **more})


Walk = stub("walk", "done", 3.0, uninterruptible=False)
Breaks = stub("breaks", "failed", 0.5, uninterruptible=False)


def answer(*steps):
    return parse_response({"plan": [{"name": n, "args": a} for n, a in steps], "sentence": "Weiter."})


def session(tmp_path, monkeypatch, view_status, *, opening=True):
    monkeypatch.setitem(REGISTRY, "set_far_view", stub("set_far_view", view_status, 0.5))
    monkeypatch.setitem(REGISTRY, "level_camera", stub("level_camera", "done", 1.0))
    monkeypatch.setitem(REGISTRY, "walk", Walk)
    monkeypatch.setitem(REGISTRY, "breaks", Breaks)
    pending, now = Pending(), [0.0]
    calls = (SkillCall("set_far_view", {}), SkillCall("level_camera", {})) if opening else ()
    conductor = Conductor(tmp_path, submit=pending, detector=NoEvents(), clock=lambda: now[0], opening=calls)

    def tick(t):
        now[0] = t
        return conductor.tick(Observation(FLAT, True, t), FRAME)

    return conductor, pending, tick


def skills_run(conductor, tick, seconds, *, answer_at=None, plan=None, pending=None):
    """Tick at 30 Hz and name the skills in the order they ran."""
    names = []
    for i in range(int(seconds * 30)):
        if answer_at is not None and i == int(answer_at * 30):
            pending.jobs[0][0].set_result(plan)
        tick(i / 30)
        active = conductor.runner.active
        if active is not None and (not names or names[-1] != active.name):
            names.append(active.name)
    return names


def head_rows(tmp_path):
    return [json.loads(line) for line in (tmp_path / "head.jsonl").read_text().splitlines()]


@pytest.mark.parametrize("view_status", ["done", "failed"])
def test_the_first_plan_runs_after_an_opening_that_succeeded_or_failed(tmp_path, monkeypatch, view_status):
    conductor, pending, tick = session(tmp_path, monkeypatch, view_status)
    try:
        tick(0.0)
        assert len(pending.jobs) == 1  # the head is asked at once, as in every session
        names = skills_run(
            conductor, tick, 7.0, answer_at=1 / 30, plan=answer(("walk", {"duration": 3})), pending=pending
        )
        # the view skill, the levelling that follows it either way, then the head's first plan
        assert names == ["set_far_view", "level_camera", "walk"]
        rows = head_rows(tmp_path)
        response = next(r for r in rows if r.get("type") == "response")
        assert response["disposition"] == "appended" and response["overtaken"] is False
        failed = [r for r in rows if r.get("type") == "opening_failed"]
        assert len(failed) == (view_status == "failed")
        if failed:
            assert failed[0]["name"] == "set_far_view" and failed[0]["queue"] == ["level_camera", "walk"]
        # the failure of the opening was no news for the head, and took no answer of its own with it
        assert conductor.epoch == 0
        assert all(e["kind"] != "skill_failed" for job in pending.jobs for e in job[1].events)
        assert all(
            job[1].last_skill is None or job[1].last_skill["status"] != "failed" for job in pending.jobs
        )
    finally:
        conductor.close()


def test_the_first_plan_that_arrives_after_an_opening_that_failed_still_runs(tmp_path, monkeypatch):
    conductor, pending, tick = session(tmp_path, monkeypatch, "failed")
    try:
        tick(0.0)
        names = skills_run(
            conductor, tick, 8.0, answer_at=4.0, plan=answer(("walk", {"duration": 3})), pending=pending
        )
        assert names == ["set_far_view", "level_camera", "walk"]
        assert conductor.runner.last["name"] == "walk" and conductor.runner.last["status"] == "done"
        assert conductor.epoch == 0
    finally:
        conductor.close()


def test_a_skill_of_the_heads_plan_that_fails_keeps_its_old_behaviour(tmp_path, monkeypatch):
    conductor, pending, tick = session(tmp_path, monkeypatch, "done", opening=False)
    try:
        tick(0.0)
        plan = answer(("breaks", {}), ("walk", {"duration": 3}))
        names = skills_run(conductor, tick, 3.0, answer_at=1 / 30, plan=plan, pending=pending)
        assert names == ["breaks"]  # the plan behind the failed skill is thrown away
        last = conductor.runner.last
        assert last["status"] == "failed" and last["queue"] == [] and last["dropped"] == ["walk"]
        assert last["queue_disposition"] == "cleared" and not conductor.runner.queue
        assert conductor.epoch >= 1 and not conductor.runner.opening_failures
        assert any(e["kind"] == "skill_failed" for job in pending.jobs[1:] for e in job[1].events)
        assert not any(r.get("type") == "opening_failed" for r in head_rows(tmp_path))
    finally:
        conductor.close()


def test_the_runner_lets_only_a_failed_opening_skill_go_and_keeps_what_follows(monkeypatch):
    monkeypatch.setitem(REGISTRY, "breaks", Breaks)
    monkeypatch.setitem(REGISTRY, "walk", Walk)
    runner = SkillRunner()
    runner.replace((SkillCall("breaks", {}), SkillCall("walk", {})), opening=True)
    t = 0.0
    while runner.active is None or runner.active.name != "walk":
        runner.tick(Observation(FLAT, True, t))
        t += 0.1
    assert runner.last is None and not runner.completed
    assert runner.opening_failures == [{"name": "breaks", "reason": "stub", "queue": ["walk"]}]
    # the same skill in the head's plan clears what follows it
    runner.replace((SkillCall("breaks", {}), SkillCall("walk", {})))
    assert runner.opening == ()
    while runner.last is None or runner.last["name"] != "breaks":
        runner.tick(Observation(FLAT, True, t))
        t += 0.1
    assert runner.last["status"] == "failed" and not runner.queue and runner.completed


@pytest.mark.parametrize(
    "flags,names",
    [
        ({}, ["start_camera"]),
        ({"no_view": True}, ["start_camera"]),
        ({"no_objects": True}, []),  # no detections, no correction to verify
        ({"no_hud_flow": True}, []),  # no verified game screen
        ({"no_level": True}, []),
    ],
)
def test_the_cli_opening_reads_before_it_corrects_the_camera(flags, names):
    given = {"no_level": False, "no_view": False, "no_objects": False, "no_hud_flow": False, **flags}
    assert [call.name for call in cli.opening(argparse.Namespace(**given))] == names


@pytest.mark.parametrize(
    "height,feet,tilt,names",
    [
        (0.28, 0.72, "level", []),
        (0.44, 0.90, "level", ["set_far_view"]),
        (0.40, 0.99, "sky", ["level_camera"]),
        (0.30, 0.60, "ground", ["level_camera"]),
    ],
)
def test_startup_plans_only_the_correction_the_frame_calls_for(height, feet, tilt, names):
    frame = FRAME.copy()
    if tilt == "level":
        frame[::5] = 255
    obs = Observation(FLAT, False, 0, frame=frame, figure=figure(height, feet), mode="foot")
    assert read_tilt(obs) == tilt
    assert [call.name for call in startup_plan(obs)] == names


def test_a_level_far_start_finishes_without_a_camera_skill_or_pad_input():
    skill = StartupCamera({})
    for t in (0.0, 0.25, 0.5):
        result = skill.step(
            Observation(
                FLAT,
                False,
                t,
                frame=FRAME,
                figure=look("far"),
                objects_time=t,
                mode="foot",
                hud=Hud(),
            )
        )
        assert result.pad == Pad()
    assert result.status == "done"
    assert skill.planned == []


def test_sky_start_selects_level_camera_after_stable_fresh_frames():
    skill = StartupCamera({})
    for t in (0.0, 0.25, 0.5):
        result = skill.step(
            Observation(
                FLAT,
                False,
                t,
                frame=FRAME,
                figure=figure(0.40, 0.99),
                objects_time=t,
                mode="foot",
                hud=Hud(),
            )
        )
        assert result.pad == Pad()
    assert skill.planned == ["level_camera"]
    result = skill.step(
        Observation(
            FLAT,
            False,
            0.55,
            frame=FRAME,
            figure=figure(0.40, 0.99),
            objects_time=0.55,
            mode="foot",
            hud=Hud(),
        )
    )
    assert result.pad.right == (0.0, -1.0)


def test_missing_or_stale_startup_detections_never_move_the_camera():
    for missing in (False, True):
        skill = StartupCamera({})
        for t in (0.0, 0.5, 1.0, 2.0):
            result = skill.step(
                Observation(
                    FLAT,
                    False,
                    t,
                    frame=FRAME,
                    figure=None if missing else figure(0.40, 0.99),
                    objects_time=0.0,
                    mode="foot",
                    hud=Hud(),
                )
            )
            assert result.pad == Pad()
        assert result.status == "done"
        assert skill.planned == []
