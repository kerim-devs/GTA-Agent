"""What a review of the tick path broke on 13 November, each as it was reproduced."""

from concurrent.futures import Future
from dataclasses import replace

import numpy as np

from pilot import profile
from pilot.conductor import Conductor
from pilot.contract import NEUTRAL_PAD, Detection, Hud, Observation, Pad, Reading
from pilot.flow import Flow
from pilot.guard import Guard
from pilot.head import parse_response
from pilot.loop import ControllerRuntime
from pilot.scene import SceneText

RGB = np.zeros((720, 1280, 3), dtype=np.uint8)
FLAT = Reading("flat", "none", None, None, 0.0, False, 1.0)
BAD = replace(FLAT, corrupt=True)
STEP = 1 / 30


class NoEvents:
    def update(self, *args, **kwargs):
        return ()


class Answers:
    """A head that answers at once, always with the same plan."""

    def __init__(self, *plan):
        self.plan = list(plan)

    def __call__(self, function, *args):
        future = Future()
        future.set_result(parse_response({"plan": self.plan, "sentence": "x"}))
        return future


class Bridge:
    def __init__(self):
        self.calls, self.status = [], 200

    def pad(self, pad=None):
        self.calls.append(pad)
        return self.status


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


def conductor(tmp_path, *plan, **kwargs):
    directory = tmp_path / f"session-{len(list(tmp_path.iterdir()))}"
    directory.mkdir()
    return Conductor(
        directory, submit=Answers(*plan), detector=NoEvents(), flow=Flow(), quiet_seconds=10**6, **kwargs
    )


def see(session, t, reading=FLAT, screen="game", **reads):
    return session.tick(
        Observation(reading, False, t, hud=Hud(wanted=0, health=1.0, screen=screen)), RGB, **reads
    )


def test_one_odd_screen_reading_and_one_damaged_frame_keep_the_plan(tmp_path):
    session = conductor(tmp_path, {"name": "press", "args": {"button": "square", "duration": 1.0}})
    try:
        for index in range(10):
            see(session, index * STEP)
        assert session.runner.has_plan
        see(session, 10 * STEP, screen="pause")
        result = see(session, 11 * STEP, reading=BAD)
        assert session.runner.has_plan and session.flow_started is None
        assert result.pad.buttons in ((), ("square",))
    finally:
        session.close()


def test_one_odd_screen_reading_does_not_cut_a_press_in_two(tmp_path):
    profile.use("gta5")
    clock, bridge = Clock(), Bridge()
    runtime = ControllerRuntime(bridge, clock=clock)
    session = conductor(
        tmp_path, {"name": "press", "args": {"button": "cross", "duration": 0.5}}, clock=clock
    )
    try:
        down = []
        for index in range(19):
            clock.now = runtime.last_fresh = index * STEP
            result = see(session, clock.now, screen="pause" if index == 8 else "game")
            runtime.tick(result.pad, fresh=True, received=clock.now)
            down.append("cross" in bridge.calls[-1].buttons)
        edges = sum(1 for before, after in zip([False, *down], down, strict=False) if after and not before)
        assert edges == 1
    finally:
        session.close()


def test_nothing_new_is_pressed_on_a_damaged_picture_and_a_held_button_stays(tmp_path):
    session = conductor(tmp_path, {"name": "press", "args": {"button": "square", "duration": 0.4}})
    try:
        t, held = 0.0, None
        while held is None and t < 1.0:  # until the press is down on a clean picture
            if see(session, t).pad.buttons == ("square",):
                held = t
            t += STEP
        assert held is not None
        assert see(session, t, reading=BAD).pad.buttons == ("square",)  # down before: stays down
    finally:
        session.close()
    fresh = conductor(tmp_path, {"name": "press", "args": {"button": "square", "duration": 0.4}})
    try:
        pads = [see(fresh, index * STEP, reading=BAD).pad for index in range(12)]
        assert all(pad.buttons == () for pad in pads)  # never down on a clean picture: not pressed
    finally:
        fresh.close()


def test_the_reflex_does_not_spend_its_presses_on_a_pad_that_is_refused(tmp_path):
    session = conductor(tmp_path, {"name": "wait", "args": {"duration": 3}})
    footer = SceneText(help="Erneut versuchen")
    try:
        pressed, t = [], 0.0

        def run(until, refused, text):
            nonlocal t
            while t < until:
                session.refuse(t, refused)
                result = see(session, t, screen="failed", text=text, text_time=t)
                if result.pad.buttons and not refused:
                    pressed.append(round(t, 1))
                assert not (refused and result.pad.buttons)
                t += STEP

        run(1.0, False, SceneText())  # the banner, and no footer to press into yet
        run(12.0, True, footer)  # the footer comes with a hand on the controller, for eleven seconds
        assert pressed == []
        run(20.0, False, footer)
        assert pressed, "the retry is pressed once the pad is the pilot's again"
    finally:
        session.close()


def test_a_freeze_in_the_middle_of_a_long_press_does_not_press_twice():
    profile.use("gta5")
    clock, bridge = Clock(), Bridge()
    runtime = ControllerRuntime(bridge, clock=clock)
    cross, t = Pad(buttons=("cross",)), 0.0
    for _ in range(6):
        clock.now = runtime.last_fresh = t
        runtime.tick(cross, fresh=True, received=t)
        t += STEP
    end = t + 0.35
    while t < end:  # the pictures stop, and the runtime lets go of everything
        clock.now = t
        runtime.tick(None, fresh=False, received=t)
        t += STEP
    for _ in range(6):  # they are back, and the skill still asks for its one press
        clock.now = runtime.last_fresh = t
        runtime.tick(cross, fresh=True, received=t)
        t += STEP
    down = [pad is not None and "cross" in pad.buttons for pad in bridge.calls]
    edges = sum(1 for before, after in zip([False, *down], down, strict=False) if after and not before)
    assert edges == 1
    # Let go of once by the skill, it can be pressed again.
    for pad in (NEUTRAL_PAD, cross):
        clock.now = runtime.last_fresh = t
        runtime.tick(pad, fresh=True, received=t)
        t += STEP
    assert "cross" in bridge.calls[-1].buttons


def test_the_guard_keeps_its_fists_down_in_a_mission_when_one_reading_misses_the_objective():
    guard, t = Guard(), 0.0

    def observe(health):
        return Observation(
            FLAT,
            False,
            t,
            objects=(Detection("person", (500, 200, 700, 700), 0.9),),
            objects_time=t,
            hud=Hud(wanted=0, health=health, screen="game"),
            mode="foot",
        )

    for _ in range(90):
        guard.tick(observe(1.0), objective="Folge dem Auto")
        t += STEP
    for index in range(60):
        verdict = guard.tick(observe(0.6), objective="" if index % 6 == 5 else "Folge dem Auto")
        assert verdict.pad is None, index
        assert not any(event["kind"] == "guard_start" for event in verdict.events)
        t += STEP
