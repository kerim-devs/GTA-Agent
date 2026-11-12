import argparse
import importlib.util
import itertools
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
    FORWARD,
    Look,
    SetFarView,
    ViewBand,
    ViewReading,
    Watch,
    alike,
    far_of,
    look_at,
    read_observation,
    read_view,
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


def lab_script(name):
    spec = importlib.util.spec_from_file_location(f"camera_{name}", LAB / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evaluation():
    return lab_script("evaluate")


def test_the_labelled_frames_are_named_right_or_not_at_all():
    ev = evaluation()
    found = ev.load()
    counts = ev.table(found)
    named = ("far", "middle", "near")
    wrong = sum(counts[v, c] for v in named for c in named if c != v)
    wrong += sum(counts["first", c] for c in named)
    total = sum(counts[v, c] for v in named for c in ev.COLUMNS)
    right = sum(counts[v, v] for v in named)
    assert total == 92 and len(found) == 148
    assert wrong == 0
    assert right >= 0.75 * total  # three of four of the far, middle and near frames
    # No figure in the picture is read as none: all 25 frames of first person.
    assert counts["first", "none"] == 25 == sum(c for (label, _), c in counts.items() if label == "first")
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


def sessions():
    return json.loads((LAB / "sessions/pilot-sessions.json").read_text())


# The five sessions of the pilot on 12 November, 14:10 to 14:16, with the detector's output at the time.
# Two of them ended failed although the far view stood for six seconds: in the camera that
# level_camera leaves the far figure is 0.35 high, and the far band ended at 0.345.
STANDS = {"20261112-141353": 4.6, "20261112-141430": 7.4}  # when the far view stands, by eye


@pytest.mark.parametrize("name", STANDS)
def test_the_far_view_that_the_levelled_camera_shows_is_named_within_two_seconds(name):
    ev = evaluation()
    watch, named = Watch(), None
    for sample in sessions()[name]["samples"]:
        if sample["t"] >= STANDS[name]:
            watch.add(sample["t"], ev.read(ev.detections_of(sample["dets"])))
            if named is None and watch.view() == "far":
                named = sample["t"]
    assert named is not None and named - STANDS[name] <= 2.0
    # and it stays named, not in and out of it
    assert watch.view() == "far"


def test_a_far_figure_of_the_levelled_camera_and_one_of_a_sprint_are_told_apart():
    assert read_view(figure(0.352, 0.837), FRAME.shape).view == "far"
    assert read_view(figure(0.34, 0.825), FRAME.shape).view == "far"
    assert read_view(figure(0.375, 0.844), FRAME.shape).view == "unknown"  # neither, by eye
    assert read_view(figure(0.40, 0.87), FRAME.shape).view == "middle"


@pytest.mark.parametrize("view", LOOK)
def test_each_view_is_read_at_any_frame_size(view):
    for shape in ((720, 1280), (360, 640), (1080, 1920)):
        assert read_view(figure(*LOOK[view], shape=shape), shape).view == view


def test_no_figure_is_none_and_a_figure_between_the_bands_is_unknown():
    assert read_view(None, FRAME.shape) == ViewReading("none", "no-figure")
    # Between far (0.365) and middle (0.385) the figure is on its way, or pushed, and is named nothing.
    assert read_view(figure(0.375, 0.84), FRAME.shape).view == "unknown"
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
    far, near = ViewReading("far"), ViewReading("near")
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


# A model of the game's camera, as the touchpad steps it: far, first person, near, middle. The
# picture needs more than a second to follow a press, a press now and then is lost, the figure is
# hidden for a while, and after a press the camera may look at the figure from the front until a
# step forward swings it behind. `looks` is how the camera shows the figure in each view: the
# camera the bands were fitted on by default, or one pitched so that they name the wrong view.

# A camera that looks up at the figure: its far figure stands where the bands put a middle one, its
# middle one where they put a near one, and its near one is larger than any near band.
PITCHED = {"far": (0.42, 0.88), "middle": (0.52, 0.97), "near": (0.74, 0.996)}


class Game:
    CYCLE = ("far", "first", "near", "middle")
    FOLLOW = 1.2

    def __init__(self, view, *, lose=(), hidden=(), front_after_press=False, swing=True, looks=None):
        self.view, self.lose, self.hidden = view, set(lose), tuple(hidden)
        self.front_after_press, self.swing = front_after_press, swing
        self.looks = LOOK if looks is None else looks
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
            return None if old == "first" else figure(*self.looks[old])
        if new == "first":
            return None
        return figure(0.5, 0.9, aspect=1.3) if self.front else figure(*self.looks[new])


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


def run(game, skill=None, *, seconds=60, hz=30, **changes):
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


def test_a_far_view_that_the_bands_name_clearly_is_done_at_once_without_a_press():
    game = Game("far")
    _, rows, end = run(game)
    last = rows[-1][2]
    assert last.status == "done" and last.reason == "far; presses=0" and last.pad == Pad()
    assert game.presses == 0 and 0.4 <= end <= 1.2 and set(pads(rows)) == {Pad()}


@pytest.mark.parametrize("start,presses", [("middle", 5), ("near", 6), ("first", 7)])
def test_from_any_other_view_the_survey_steps_round_once_and_presses_on_to_the_far_one(start, presses):
    # four presses make a round and end where they began; the far view lies zero to three presses on
    game = Game(start)
    skill, rows, end = run(game)
    last = rows[-1][2]
    assert last.status == "done" and last.reason.startswith(f"far; presses={presses}; survey=")
    assert last.pad == Pad() and game.view == "far" and game.presses == presses == skill.presses
    assert 2.0 <= end < 30


def test_the_survey_reports_what_it_measured_in_the_order_of_the_presses():
    game = Game("middle")
    _, rows, _ = run(game)
    # far, first person, near and middle again, whole figure, none, cut, whole
    assert rows[-1][2].reason == "far; presses=5; survey=0.28/none/0.58cut/0.44"


@pytest.mark.parametrize("start,presses", [("far", 4), ("middle", 5), ("near", 6), ("first", 7)])
def test_a_camera_the_bands_misread_is_carried_by_the_survey(start, presses):
    # Pitched, the camera shows the far figure where the bands put the middle one, and the bands
    # name the middle view near. The skill names no band during the survey and ends in the far view.
    assert read_view(figure(*PITCHED["far"]), FRAME.shape).view == "middle"
    assert read_view(figure(*PITCHED["middle"]), FRAME.shape).view == "near"
    assert read_view(figure(*PITCHED["near"]), FRAME.shape).view == "unknown"
    game = Game(start, looks=PITCHED)
    _, rows, end = run(game)
    last = rows[-1][2]
    assert last.status == "done" and last.reason.startswith(f"far; presses={presses}; survey=")
    assert game.view == "far" and game.presses == presses and end < 30


def test_the_survey_does_not_begin_before_the_bands_had_two_seconds_on_foot():
    game = Game("near")
    _, rows, _ = run(game)
    assert 2.0 <= pulses(rows)[0][0] < 2.2


def test_a_press_is_a_pulse_of_a_tenth_and_the_picture_settles_before_it_is_measured():
    game = Game("near")
    _, rows, _ = run(game)
    shots = pulses(rows)
    assert len(shots) == 6
    for a, b in shots:
        assert 0.09 <= b - a <= 0.14
    # 1.5 s of settling and then a second of readings, before the next press
    assert all(b[0] - a[1] >= 1.5 + 1.0 for a, b in itertools.pairwise(shots))
    assert set(pads(rows)) <= {Pad(), Pad(buttons=("touchpad",))}


def test_a_press_that_was_lost_shows_as_two_equal_neighbours_and_costs_one_more_press():
    game = Game("middle", lose={2})  # the second press of the round does nothing
    _, rows, _ = run(game)
    last = rows[-1][2]
    assert last.status == "done" and game.view == "far" and game.presses == 6
    assert last.reason == "far; presses=6; survey=0.28/none/0.58cut/0.44"  # the same four, in the same order


def test_a_press_lost_on_the_way_to_the_far_view_is_met_by_measuring_and_not_by_counting():
    game = Game("near", lose={5})  # the first press after the round
    _, rows, _ = run(game)
    assert rows[-1][2].status == "done" and game.view == "far" and game.presses == 7


def test_a_figure_seen_from_the_front_gets_a_short_step_and_is_then_measured():
    game = Game("near", front_after_press=True)
    skill, rows, _ = run(game)
    assert rows[-1][2].status == "done" and game.view == "far"
    assert skill.steps == game.presses - 1  # one after each press but the one that showed first person
    runs, current = [], []
    forward = [t for kind, t, r in rows if kind == "tick" and r.pad == FORWARD]
    for t in forward:
        if current and t - current[-1] > 0.1:
            runs.append(current)
            current = []
        current.append(t)
    runs.append(current)
    assert len(runs) == skill.steps and all(0.3 <= r[-1] - r[0] + 1 / 30 <= 0.5 for r in runs)
    assert set(pads(rows)) == {Pad(), Pad(buttons=("touchpad",)), FORWARD}


def test_a_figure_that_stays_unreadable_ends_the_skill_with_what_it_saw():
    game = Game("middle", front_after_press=True, swing=False)
    skill, rows, end = run(game)
    last = rows[-1][2]
    assert last.status == "failed" and last.reason == "views-unread; last=unknown; presses=1; survey=?"
    assert skill.steps == 1 and end < 12 and last.pad == Pad()


def test_a_figure_hidden_for_a_while_is_surveyed_when_it_comes_back():
    game = Game("far", hidden=[(0.0, 3.0)])
    _, rows, _ = run(game)
    assert rows[-1][2].status == "done" and game.view == "far"


def test_a_figure_hidden_all_the_time_ends_after_a_round_and_does_not_go_round_again():
    game = Game("far", hidden=[(0.0, math.inf)])
    _, rows, end = run(game)
    last = rows[-1][2]
    assert last.status == "failed" and last.reason == "no-figure; last=none; presses=4; survey=none"
    assert game.presses == 4 and last.pad == Pad() and end < 20


def test_two_views_that_look_alike_end_the_survey_with_the_measurements():
    # a middle view as small as the far one: the smallest is not clearly smaller than the next
    game = Game("near", looks={**LOOK, "middle": (0.30, 0.72)})
    _, rows, _ = run(game)
    last = rows[-1][2]
    assert (
        last.status == "failed"
        and last.reason == "views-alike; last=far; presses=5; survey=0.30/none/0.58cut/0.30"
    )


def test_a_press_that_never_moves_the_camera_ends_after_six_presses():
    game = Game("near", lose=set(range(1, 20)))
    _, rows, _ = run(game)
    last = rows[-1][2]
    assert last.status == "failed" and last.reason == "views-alike; last=near; presses=6; survey=0.58cut"
    assert game.presses == 6 and last.pad == Pad()


def test_a_hard_time_limit_and_the_longest_a_default_run_can_be():
    game = Game("near", lose=set(range(1, 20)))
    _, rows, end = run(game, SetFarView({"duration": 10}))
    assert rows[-1][2].reason.startswith("time-limit") and 10 <= end < 10.1 and rows[-1][2].pad == Pad()
    assert SetFarView({"duration": 100}).limit == 60 and SetFarView({"duration": 1}).limit == 10
    assert SetFarView({}).limit == 50
    # the longest a survey that finds the far view takes: a round, three presses on, and one lost
    longest = Game("first", lose={6})
    assert run(longest)[2] < 30
    # and with the camera in front of the figure after every press, and a second press lost
    assert run(Game("first", lose={6}, front_after_press=True))[2] < 50
    # A figure that flickers in and out of every view cannot keep it past the limit either.
    flicker = Game("near", hidden=[(i * 0.7, i * 0.7 + 0.3) for i in range(80)], lose=set(range(1, 20)))
    assert run(flicker)[2] <= 50.1


# The pieces of the survey, apart from the skill.


def figures(*items):
    return [ViewReading("unknown", "between-bands", h, f) for h, f in items]


def test_a_window_is_a_whole_figure_a_cut_one_none_or_nothing_that_can_be_used():
    assert look_at(figures(*[(0.35, 0.83)] * 8)) == Look("figure", 0.35, False)
    assert look_at(figures(*[(0.73, 0.99)] * 8)) == Look("figure", 0.73, True)
    assert look_at([ViewReading("none", "no-figure")] * 8) == Look("none")
    # the median of the figures that can be read; the odd reading of the detector does not move it
    assert look_at(figures(*[(0.35, 0.83)] * 6, (0.6, 0.99), (0.2, 0.7))).height == 0.35
    # figures that no measurement takes (another person, off the middle) leave a window unread
    unread = [ViewReading("unknown", "second-person", 0.5, 0.9)] * 5 + figures((0.35, 0.83))
    assert look_at(unread) == Look("unclear") and look_at([]) == Look("unclear")
    mixed = [ViewReading("none", "no-figure")] * 4 + figures(*[(0.35, 0.83)] * 4)
    assert look_at(mixed).kind == "unclear"


def test_the_far_view_is_the_smallest_whole_figure_well_below_the_next_larger_one():
    none, near, middle, far = (
        Look("none"),
        Look("figure", 0.57, True),
        Look("figure", 0.45),
        Look("figure", 0.35),
    )
    assert far_of([none, near, middle, far]) == (3, "far")
    assert far_of([middle, far, none, near]) == (1, "far")  # the round begins in any view
    assert far_of([Look("figure", 0.30), none, Look("figure", 0.73, True), Look("figure", 0.42)]) == (
        0,
        "far",
    )
    # a cut figure is never the far one, and a cut box smaller than its neighbour proves no larger view
    assert far_of([none, Look("figure", 0.30, True), middle, Look("figure", 0.38)]) == (None, "views-alike")
    assert far_of([none, near, middle, Look("figure", 0.40)]) == (None, "views-alike")
    assert far_of([none, none, none, none]) == (None, "no-figure")
    assert far_of([none, near, Look("figure", 0.60, True), none]) == (None, "no-whole-figure")
    assert far_of([none, near, none, none]) == (None, "no-whole-figure")
    assert far_of([none, none, middle, none]) == (None, "one-view-only")
    assert far_of([none, near, middle, Look("unclear")]) == (None, "views-unread")
    # first person comes right after far: when the one view without a figure is elsewhere, they disagree
    assert far_of([far, near, none, middle]) == (None, "views-disagree")
    assert far_of([far, none, none, middle]) == (0, "far")  # two views without a figure: nothing to check


def test_two_neighbouring_windows_of_one_view_are_alike_and_two_views_are_not():
    assert alike(Look("none"), Look("none"))
    assert alike(Look("figure", 0.35), Look("figure", 0.37))
    assert not alike(Look("figure", 0.35), Look("figure", 0.45))  # far and middle
    assert not alike(Look("figure", 0.57, True), Look("figure", 0.57))
    assert not alike(Look("unclear"), Look("unclear")) and not alike(Look("none"), Look("figure", 0.3))


# What the pilot's own sessions of 12 November show: lab/camera/survey.py reads the first two seconds
# and the stretches after the recorded presses from the detections stored for sixteen sessions.


def survey_lab():
    return lab_script("survey")


def test_the_first_two_seconds_name_far_only_where_the_view_was_far():
    lab = survey_lab()
    named = {}
    for name, session in sessions().items():
        named[name] = [v for v, _ in lab.opening(lab.readings(session["samples"]))]
    far = [name for name, views in named.items() if "far" in views]
    # two sessions began in the far view and the bands named it within a second ...
    assert set(far) == {"20261112-143047", "20261112-141836"}
    # ... in the others the far view was not the one the camera showed at the start (every one of
    # them was done or failed by what came after), so that the bands name it nowhere else
    for name in far:
        assert next(t for v, t in lab.opening(lab.readings(sessions()[name]["samples"])) if v == "far") < 1.0


@pytest.mark.parametrize(
    "name,shown",
    [("20261112-143356", (0.70, 0.78)), ("20261112-143406", (0.62, 0.72)), ("20261112-143436", (0.70, 0.78))],
)
def test_a_near_figure_in_daylight_is_a_large_one_cut_by_the_lower_edge_and_is_measured(name, shown):
    # The skill named nothing for the whole ten seconds: the figure stood 0.66 to 0.74 high, and the
    # near band ends at 0.65, so every reading was between the bands, and in -143436 a second person
    # on the pavement made some of them unreadable too. The detector's confidence was 0.95 throughout.
    lab = survey_lab()
    session = sessions()[name]
    seen = [(t, r) for t, r in lab.readings(session["samples"]) if t < 5.0]  # where the figure stood
    watch, named = Watch(), set()
    for t, reading in seen:
        watch.add(t, reading)
        named.add(watch.view())
    assert named == {None}  # the bands name nothing, as in the recorded run
    assert {r.reason for _, r in seen if r.height} <= {"between-bands", "in-band", "second-person"}
    assert sum(r.reason == "between-bands" for _, r in seen) > 0.6 * len(seen)
    look = lab.stretches(seen, [])[0][1]
    assert look.kind == "figure" and look.cut and shown[0] <= look.height <= shown[1]
    if name == "20261112-143436":
        assert any(r.reason == "second-person" for _, r in seen)


def test_the_survey_replayed_on_the_pictures_of_two_recorded_rounds_ends_far():
    replay = lab_script("replay")
    # the game's idle camera first (141056): the first two seconds name nothing, a round, and the far
    # view where the survey began
    end, result, made = replay.replay(sessions()["20261112-141056"])
    assert result.status == "done" and result.reason == "far; presses=4; survey=none/0.57cut/0.49/0.34"
    assert len(made) == 4 and end < 20
    # first person first (141430): a round and three presses on to the far view, which the recorded
    # skill had found but not named
    end, result, made = replay.replay(sessions()["20261112-141430"])
    assert result.status == "done" and result.reason == "far; presses=7; survey=0.56cut/0.45/0.35/none"
    assert len(made) == 7 and end < 25
    # the other sessions do not show four different views, and are not replayed
    assert replay.replay(sessions()["20261112-143232"]) is None


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
        ({}, ["set_far_view", "level_camera"]),
        ({"no_view": True}, ["level_camera"]),
        ({"no_objects": True}, ["level_camera"]),  # no detections, no view to read
        ({"no_hud_flow": True}, ["level_camera"]),  # no screen to know that it is the game's
        ({"no_level": True}, []),
    ],
)
def test_the_cli_opening_sets_the_view_and_then_levels_the_camera(flags, names):
    given = {"no_level": False, "no_view": False, "no_objects": False, "no_hud_flow": False, **flags}
    assert [call.name for call in cli.opening(argparse.Namespace(**given))] == names
