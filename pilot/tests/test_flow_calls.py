"""A call on the phone: taken when it rings, left to run, and the figure plays on meanwhile."""

from concurrent.futures import Future

import numpy as np
import pytest

from pilot.conductor import Conductor
from pilot.contract import NEUTRAL_PAD, Hud, Observation, Reading
from pilot.flow import CALL_SECONDS, PHONE_SECONDS, Flow
from pilot.head import parse_response
from pilot.scene import SceneText, TextLine

FLAT = Reading("flat", "none", None, None, 0.0, False, 1)
RGB = np.zeros((720, 1280, 3), dtype=np.uint8)
# What the reader gave on Kerim's recordings of 11 November.
RINGS = (
    SceneText(
        lines=(
            TextLine("EINtsEHENDER", 0.5, (1093, 493, 79, 10), "phone"),
            TextLine("ANRUF", 0.5, (1092, 509, 37, 9), "phone"),
        )
    ),
    SceneText(lines=(TextLine("ANBUF", 0.5, (1092, 509, 37, 9), "phone"),)),
    SceneText(lines=(TextLine("It¥1 ANRUF", 0.5, (1047, 505, 82, 26), "phone"),)),
)
TALKS = (
    SceneText(lines=(TextLine("VER8UNDEN", 0.5, (1092, 494, 67, 9), "phone"),)),
    SceneText(lines=(TextLine("WIRD QEWAHLT..", 0.5, (1092, 494, 67, 9), "phone"),)),
    SceneText(lines=(TextLine("WIRDßEWAHLT .", 0.5, (1092, 494, 67, 9), "phone"),)),
)
UNREAD = SceneText(lines=(TextLine("ge", 0.5, (1118, 603, 31, 27), "phone"),))
CONTACTS = SceneText(lines=(TextLine("Kontakte", 0.5, (1092, 300, 60, 12), "phone"),))
SPOKEN = SceneText(
    lines=(TextLine("Ich warte auf deinen Anruf.", 0.5, (420, 640, 440, 21), "subtitle"),),
    subtitle="Ich warte auf deinen Anruf.",
)


def obs(t, screen="phone"):
    return Observation(FLAT, True, t, hud=Hud(screen=screen))


def run(flow, start, end, text, screen="phone", step=1 / 30):
    results, presses, down = [], [], False
    t = start
    while t < end:
        result = flow.tick(obs(t, screen), text)
        results.append(result)
        pressed = result is not None and bool(result.pad.buttons)
        if pressed and not down:
            presses.append((round(t, 2), result.pad.buttons))
        down = pressed
        t += step
    return results, presses


@pytest.mark.parametrize("rings", RINGS)
def test_a_call_that_rings_is_taken_with_one_press_of_the_cross(rings):
    flow = Flow(calls=True)
    results, presses = run(flow, 0.0, 1.5, rings)
    assert [buttons for _, buttons in presses] == [("cross",)]
    assert 0.45 <= presses[0][0] <= 0.6
    assert {result.action for result in results if result is not None} == {"answer"}
    # It says connected: nothing more is pressed for as long as the call runs.
    results, presses = run(flow, 1.5, 40.0, TALKS[0])
    assert presses == [] and all(result is None for result in results)


def test_a_call_that_still_rings_is_taken_once_more_and_then_left_alone():
    flow = Flow(calls=True)
    _, presses = run(flow, 0.0, 12.0, RINGS[0])
    assert [buttons for _, buttons in presses] == [("cross",), ("cross",)]
    assert presses[1][0] - presses[0][0] >= 1.95


@pytest.mark.parametrize("talks", TALKS)
def test_a_call_that_runs_is_never_hung_up_on(talks):
    flow = Flow(calls=True)
    results, presses = run(flow, 0.0, 45.0, talks)
    assert presses == [] and all(result is None for result in results)


def test_a_call_whose_phone_cannot_be_read_any_more_is_left_to_run():
    # 20261111-172549: "ANBUF" for half a second, the cross, then thirty seconds with nothing read.
    flow = Flow(calls=True)
    _, presses = run(flow, 0.0, 0.8, RINGS[1])
    assert [buttons for _, buttons in presses] == [("cross",)]
    results, presses = run(flow, 0.8, 32.0, UNREAD)
    assert presses == [] and all(result is None for result in results)
    # The call is over and the phone goes by itself.
    results, presses = run(flow, 32.0, 36.0, None, screen="game")
    assert presses == [] and all(result is None for result in results)


def test_a_phone_with_no_call_on_it_is_left_by_the_way_back_after_its_seconds():
    flow = Flow(calls=True)
    results, presses = run(flow, 0.0, PHONE_SECONDS - 0.1, CONTACTS)
    assert presses == [] and all(result is None for result in results)
    _, presses = run(flow, PHONE_SECONDS - 0.1, PHONE_SECONDS + 1.0, CONTACTS)
    assert [buttons for _, buttons in presses] == [("circle",)]


def test_a_phone_forgotten_after_a_call_is_put_away_in_the_end():
    flow = Flow(calls=True)
    run(flow, 0.0, 1.0, TALKS[0])
    _, presses = run(flow, 1.0, CALL_SECONDS + 4.0, CONTACTS)
    assert [buttons for _, buttons in presses][:1] == [("circle",)]
    assert presses[0][0] >= CALL_SECONDS


def test_the_word_spoken_in_a_scene_is_no_call():
    flow = Flow(calls=True)
    _, presses = run(flow, 0.0, 4.0, SPOKEN)
    assert [buttons for _, buttons in presses] == [("circle",)]  # a phone with no call: the way back


def test_a_call_is_only_what_stands_on_a_phone():
    flow = Flow(calls=True)
    results, presses = run(flow, 0.0, 6.0, RINGS[0], screen="game")
    assert presses == [] and all(result is None for result in results)


def test_a_damaged_picture_presses_nothing_and_forgets_nothing():
    flow = Flow(calls=True)
    run(flow, 0.0, 0.4, RINGS[0])
    damaged = Observation(
        Reading("flat", "none", None, None, 0.0, True, 1), True, 0.45, hud=Hud(screen="phone")
    )
    result = flow.tick(damaged, RINGS[0])
    assert result is None or result.pad == NEUTRAL_PAD
    _, presses = run(flow, 0.5, 1.2, RINGS[0])
    assert [buttons for _, buttons in presses] == [("cross",)]


def test_without_the_option_every_phone_is_left_at_once_as_before():
    flow = Flow()
    _, presses = run(flow, 0.0, 1.0, RINGS[0])
    assert [buttons for _, buttons in presses] == [("circle",)]
    assert presses[0][0] < 0.3


class NoEvents:
    def update(self, *args, **kwargs):
        return []


class Pending:
    def __init__(self):
        self.jobs = []

    def __call__(self, function, *args):
        future = Future()
        self.jobs.append((future, function, args))
        return future


def session(directory):
    conductor = Conductor(
        directory,
        flow=Flow(calls=True),
        detector=NoEvents(),
        submit=Pending(),
        notebook=directory / "notebook.txt",
    )
    conductor.pending.clear()
    conductor.last_request_time = 0
    conductor.head_latency = 0
    conductor.runner.replace(
        parse_response(
            {"plan": [{"name": "walk", "args": {"y": -0.6, "duration": 60}}], "sentence": "Weiter."}
        ).plan
    )
    return conductor


def test_the_figure_walks_on_through_a_call_and_the_plan_is_kept(tmp_path):
    """Beside a session with no phone at all: the call changes nothing but the one press."""
    (tmp_path / "call").mkdir()
    (tmp_path / "plain").mkdir()
    called, plain = session(tmp_path / "call"), session(tmp_path / "plain")
    try:

        def tick(conductor, t, screen, text=None):
            reads = {} if text is None else {"text": text, "text_time": t}
            return conductor.tick(Observation(FLAT, True, t, hud=Hud(screen=screen)), RGB, **reads)

        crosses, walked, t = 0, 0, 0.0
        while t < 20.0:
            text = None if t < 0.1 else RINGS[0] if t < 1.2 else TALKS[0]
            pad = tick(called, t, "game" if t < 0.1 else "phone", text).pad
            beside = tick(plain, t, "game").pad
            if pad.buttons == ("cross",):
                crosses += 1
            else:
                assert pad == beside, t
                walked += pad != NEUTRAL_PAD
            t += 1 / 30
        assert 2 <= crosses <= 4  # one press, held for the console to see
        assert walked > 300
        assert called.runner.describe() == plain.runner.describe()  # the walk went as far as without
        rows = (called.directory / "head.jsonl").read_text()
        assert '"flow_answer"' in rows and '"flow_enter"' not in rows
        assert not any(event.get("kind") == "screen_changed" for event in called.pending)
    finally:
        called.close()
        plain.close()
