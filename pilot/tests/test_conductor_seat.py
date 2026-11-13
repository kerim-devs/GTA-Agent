"""Seat evidence and picture recovery from the 13 November connection loss."""

from concurrent.futures import Future
from dataclasses import replace

import numpy as np
import pytest

from pilot.conductor import Conductor
from pilot.contract import NEUTRAL_PAD, Answer, Detection, Hud, Judgment, Observation, Pad, Reading
from pilot.judge import ModeFilter
from pilot.scene import EventDetector
from pilot.vehicle_entry import EnterVehicle

RGB = np.zeros((720, 1280, 3), dtype=np.uint8)
# Capture times from 20261113-163218/judge.jsonl, joined to play.jsonl.
# At 223.612 the old pilot actually pressed Triangle; flat readings after that are real.
INCIDENT = (
    (220.27, "vehicle", "tilted", "purple"),
    (220.603, "vehicle", "tilted", "purple"),
    (220.902, "vehicle", "tilted", "purple"),
    (221.174, "vehicle", "tilted", "purple"),
    (221.426, "vehicle", "tilted", "purple"),
    (221.693, "vehicle", "tilted", "purple"),
    (221.961, "foot", "tilted", "purple"),
    (222.215, "vehicle", "tilted", "purple"),
    (222.474, "vehicle", "tilted", "purple"),
    (222.75, "foot", "tilted", "purple"),
    (223.011, "foot", "tilted", "purple"),
    (223.268, "foot", "tilted", "purple"),
    (223.536, "vehicle", "tilted", "purple"),
    (223.784, "vehicle", "tilted", "purple"),
    (224.051, "vehicle", "tilted", "purple"),
    (224.317, "vehicle", "tilted", "purple"),
    (224.579, "vehicle", "tilted", "purple"),
    (224.835, "foot", "tilted", "purple"),
    (225.105, "foot", "tilted", "none"),
    (225.37, "foot", "flat", "none"),
    (225.628, "foot", "flat", "none"),
    (225.883, "foot", "flat", "none"),
    (226.149, "foot", "flat", "none"),
    (226.429, "foot", "flat", "none"),
    (226.683, "foot", "flat", "none"),
    (226.918, "foot", "flat", "none"),
    (227.39, "foot", "flat", "none"),
    (227.719, "vehicle", "flat", "none"),
    (227.989, "vehicle", "tilted", "purple"),
    (228.26, "vehicle", "tilted", "purple"),
    (228.505, "vehicle", "tilted", "purple"),
    (228.772, "vehicle", "tilted", "purple"),
    (229.031, "vehicle", "tilted", "purple"),
    (229.304, "vehicle", "tilted", "purple"),
    (229.562, "vehicle", "tilted", "purple"),
    (229.814, "vehicle", "tilted", "purple"),
)


def reading(minimap="tilted", route="purple", *, corrupt=False):
    return Reading(minimap, route, None, None, None, corrupt, 1.0)


def judgment(t, mode):
    return Judgment(t, {"mode": Answer(mode, 0.99)}, {}, 0.3, "recorded")


@pytest.mark.parametrize("suppress_old_triangle", [False, True])
def test_incident_has_no_false_exit(tmp_path, suppress_old_triangle):
    class Judge:
        def __init__(self):
            self.rows = iter(INCIDENT)

        def poll(self, rgb, capture):
            t, answer, _, _ = next(self.rows)
            return judgment(t, answer)

        def drain_failures(self):
            return []

        def close(self):
            pass

    class Detector(EventDetector):
        def __init__(self):
            super().__init__()
            self.exits = []

        def update(self, reading, t, **kwargs):
            events = super().update(reading, t, **kwargs)
            self.exits.extend(e.timestamp for e in events if e.kind == "vehicle_exit")
            return events

    detector = Detector()
    conductor = Conductor(tmp_path, detector=detector, judge=Judge(), submit=lambda *args: Future())
    try:
        for t, _, minimap, route in INCIDENT:
            if suppress_old_triangle:
                # Preventing the old Triangle leaves the car and its route in view.
                minimap, route = "tilted", "purple"
            conductor.tick(Observation(reading(minimap, route), None, t), RGB)
        assert detector.exits == ([] if suppress_old_triangle else [225.370])
    finally:
        conductor.close()


def test_sustained_foot_can_resolve_a_map_that_never_flattens():
    detector, modes = EventDetector(), ModeFilter()
    detector.update(reading(), 0, mode="vehicle")
    modes.update(judgment(0, "vehicle"), 0, vehicle=True)
    modes.update(judgment(0.25, "vehicle"), 0.25, vehicle=True)
    exits = []
    for i in range(14):
        t = 0.5 + i * 0.25
        mode = modes.update(judgment(t, "foot"), t, vehicle=True)
        if t < 3.5:
            assert mode == "unknown"
        exits.extend(
            e.timestamp
            for e in detector.update(reading(), t, mode=mode, exit_confirmed=modes.exit_confirmed)
            if e.kind == "vehicle_exit"
        )
    assert exits == [3.5]


def test_a_lapsed_or_interrupted_foot_run_cannot_confirm_an_exit():
    for interruption in ("vehicle", "none", None):
        modes = ModeFilter()
        for t in (0, 0.5, 1, 1.5, 2):
            assert modes.update(judgment(t, "foot"), t, vehicle=True) == "unknown"
        t = 4 if interruption is None else 2.5
        modes.update(None if interruption is None else judgment(t, interruption), t, vehicle=True)
        assert modes.update(judgment(t + 0.25, "foot"), t + 0.25, vehicle=True) == "unknown"
        assert not modes.exit_confirmed


def test_acknowledged_triangle_reports_exit_when_map_flattens(tmp_path):
    conductor = Conductor(tmp_path, submit=lambda *args: Future())
    events = []
    update = conductor.detector.update

    def capture(*args, **kwargs):
        result = update(*args, **kwargs)
        events.extend(result)
        return result

    conductor.detector.update = capture
    try:
        conductor.tick(Observation(reading(), None, 0), RGB)
        conductor.tick(Observation(reading(), None, 0.5), RGB)
        conductor.tick(Observation(reading(), None, 1.01), RGB)
        conductor.sent(Pad(buttons=("triangle",)), 1.1)
        conductor.tick(Observation(reading("flat", "none"), None, 1.1 + 2.937), RGB)
        assert [e.kind for e in events] == ["vehicle_exit"]
        assert events[0].timestamp - 1.1 == pytest.approx(2.937)
    finally:
        conductor.close()


@pytest.mark.parametrize("mode", ["foot", "unknown", None])
def test_entry_finishes_without_a_press_when_map_shows_seated_figure(mode):
    skill = EnterVehicle({})
    for t in (0, 0.5, 1, 1.5, 2):
        result = skill.step(
            Observation(
                reading(),
                None,
                t,
                mode=mode,
                objects_time=t,
                objects=(Detection("car", (384, 324, 896, 648), 0.9),),
            )
        )
        assert result.pad == NEUTRAL_PAD
    assert result.status == "done"
    assert result.reason == "already in a vehicle"


@pytest.mark.parametrize(
    "figure_present,mode,minimap,expected",
    [
        (True, "foot", "flat", True),
        # The judge sees the figure standing; the detector misses it by night.
        (False, "foot", "flat", True),
        # A flat map misread as tilted, with no route on it, does not seat the figure.
        (True, "foot", "tilted", True),
        (True, "unknown", "flat", False),
        # With no judge the map and the detection have to agree.
        (True, None, "flat", True),
        (False, None, "flat", False),
    ],
)
def test_entry_press_needs_the_judges_word_or_a_visible_player_on_a_flat_map(
    figure_present, mode, minimap, expected
):
    car = Detection("car", (384, 324, 896, 648), 0.9)
    figure = Detection("person", (540, 310, 660, 690), 0.9) if figure_present else None
    skill = EnterVehicle({})
    for t in (0, 0.04):
        result = skill.step(
            Observation(
                reading(minimap, "none"), None, t, objects=(car,), objects_time=t, figure=figure, mode=mode
            )
        )
    assert bool(result.pad.buttons) is expected


def test_picture_gap_and_settling_are_neutral_and_make_no_scene_events(tmp_path):
    class Detector(EventDetector):
        def __init__(self):
            super().__init__()
            self.calls = []

        def update(self, reading, t, **kwargs):
            self.calls.append(t)
            return super().update(reading, t, **kwargs)

    class Judge:
        def poll(self, rgb, capture):
            return judgment(capture, "vehicle")

        def drain_failures(self):
            return []

        def close(self):
            pass

    requests = []

    def submit(*args):
        requests.append(args[-1])
        return Future()

    detector = Detector()
    conductor = Conductor(tmp_path, detector=detector, judge=Judge(), submit=submit, awake=1)
    try:
        conductor.tick(Observation(reading(), None, 0), RGB)
        calls = len(detector.calls)
        for t in (0.3, 0.5, 10, 20):
            assert conductor.missing(t).pad == NEUTRAL_PAD
        # Invalid frames do not count as recovery.
        assert conductor.tick(Observation(reading(), None, 20.1), None).pad == NEUTRAL_PAD
        for t in (20.245, 20.5, 21.244):
            assert conductor.tick(Observation(reading(), None, t), RGB).pad == NEUTRAL_PAD
        assert len(detector.calls) == calls
        assert not conductor.pending
        assert len(requests) == 1
        conductor.tick(Observation(reading(), None, 21.246), RGB)
        events = [e for r in requests for e in r.events]
        assert [e["kind"] for e in events].count("picture_returned") == 1
        assert not [e for e in events if e["kind"] == "vehicle_exit"]
        # A map read as damaged on a picture that is there is no gap: on 13 November the reader said
        # so for 45 s on end on a landing, and the figure has to walk on through it.
        before = len(detector.calls)
        corrupt = replace(reading(), corrupt=True)
        for i in range(30):
            conductor.tick(Observation(corrupt, None, 21.25 + i / 30), RGB)
        assert len(detector.calls) == before + 30
        assert conductor.picture_missing_since is None
    finally:
        conductor.close()


def test_the_judges_word_about_the_pause_map_is_no_word_on_the_figure(tmp_path):
    """13 November, 17:20: the pilot's own map stood for 22 s with the figure on foot beside a car and
    the judge said vehicle at 1.0 throughout; the drive planned on that word stood for 30 s."""

    class Judge:
        # An answer is of the picture a third of a second back, and of a map it says vehicle.
        def poll(self, rgb, capture):
            pictured = capture - 0.3
            return judgment(pictured, "vehicle" if 1.0 <= pictured < 4.0 else "foot")

        def drain_failures(self):
            return []

        def close(self):
            pass

    conductor = Conductor(tmp_path, judge=Judge(), submit=lambda *args: Future(), awake=1)
    try:
        seen = {}
        for i in range(64):
            t = i / 8
            menu = 1.0 <= t < 4.0
            conductor.tick(
                Observation(
                    reading("none" if menu else "flat", "none"),
                    None,
                    t,
                    hud=Hud(screen="map" if menu else "game"),
                ),
                RGB,
            )
            seen[t] = conductor.mode_filter.mode
        assert seen[0.875] == "foot"
        assert "vehicle" not in seen.values()
        # Over a long map the mode lapses like over a silent server, and is back with the game.
        assert seen[3.875] is None
        assert seen[5.0] == "foot"
    finally:
        conductor.close()


def test_mode_filter_takes_no_answer_that_is_not_of_the_game():
    modes = ModeFilter()
    assert modes.update(judgment(0.0, "foot"), 0.1) is None
    assert modes.update(judgment(0.3, "foot"), 0.4) == "foot"
    for i in range(3):
        assert modes.update(judgment(0.6 + 0.3 * i, "vehicle"), 0.7 + 0.3 * i, game=False) == "foot"
    assert modes.update(None, 2.0, game=False) is None


# 20261113-172004/judge.jsonl on the play clock: a car on its purple route, the map tilted throughout.
SEATED = (
    "338.2 v 338.4 v 338.7 v 338.9 v 339.2 f 339.4 f 339.7 f 340.0 v 340.2 f 340.5 f 340.8 f 341.0 f "
    "341.3 f 341.6 f 341.8 f 342.0 f 342.3 f 342.6 v 342.9 v 343.1 v 343.4 v 343.6 v 343.9 v 344.2 v "
    "344.4 v 344.7 f 345.0 f 345.2 f 345.5 f 345.7 f 346.0 f 346.3 f 346.5 f 346.7 f 347.1 f 347.3 f "
    "347.6 f 347.8 f 348.1 f 348.3 v 348.6 v 348.9 v 349.2 v 349.4 f 349.7 f 349.9 f"
).split()


def test_no_length_of_the_judges_foot_stands_against_a_sound_tilted_map_with_a_route(tmp_path):
    """The head was told of an exit at 347.6 s, planned a walk, and of an entry a second later."""
    rows = [
        (float(t), {"v": "vehicle", "f": "foot"}[a]) for t, a in zip(SEATED[::2], SEATED[1::2], strict=True)
    ]

    class Judge:
        def __init__(self):
            self.rows = iter(rows)

        def poll(self, rgb, capture):
            return judgment(*next(self.rows))

        def drain_failures(self):
            return []

        def close(self):
            pass

    conductor = Conductor(tmp_path, judge=Judge(), submit=lambda *args: Future())
    events, modes = [], set()
    update = conductor.detector.update

    def capture(*args, **kwargs):
        result = update(*args, **kwargs)
        events.extend(e.kind for e in result)
        modes.add(kwargs.get("mode"))
        return result

    conductor.detector.update = capture
    try:
        for t, _ in rows:
            conductor.tick(Observation(reading(), None, t), RGB)
        assert "vehicle_exit" not in events
        assert "foot" not in modes
    finally:
        conductor.close()
