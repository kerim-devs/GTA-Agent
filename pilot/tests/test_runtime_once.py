"""One press asked for is one press at the console, whatever the ticks do (loop.ControllerRuntime)."""

import pytest

from pilot import profile
from pilot.contract import NEUTRAL_PAD, Pad
from pilot.loop import ControllerRuntime


class Bridge:
    def __init__(self, status=200):
        self.calls, self.status = [], status

    def pad(self, pad=None):
        self.calls.append(pad)
        return self.status


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture(autouse=True)
def gta5():
    profile.use("gta5")
    yield
    profile.use("gta5")


def run(runtime, clock, steps):
    """(seconds since the last tick, pad) for each tick; the pads that left for the console."""
    for gap, pad in steps:
        clock.now += gap
        runtime.last_fresh = clock.now  # what observe() does with a fresh frame
        runtime.tick(pad, fresh=True, received=clock.now)
    return [call.buttons for call in runtime.bridge.calls]


def presses(sent, button):
    """How often the button went down, in the pads sent."""
    return sum(
        1
        for before, after in zip([(), *sent], sent, strict=False)
        if button in after and button not in before
    )


def test_a_press_over_quick_ticks_is_sent_as_asked():
    clock = Clock()
    runtime = ControllerRuntime(Bridge(), clock=clock)
    cross = Pad(buttons=("cross",))
    sent = run(runtime, clock, [(0.033, cross)] * 4 + [(0.033, NEUTRAL_PAD)])
    assert sent == [("cross",)] * 4 + [()]
    assert runtime.cut == 0


def test_a_press_that_spans_a_slow_tick_is_cut_short_and_not_pressed_twice():
    # The legend's cross of 13 November: two ticks 0.37 s apart, each asking for the cross.
    clock = Clock()
    runtime = ControllerRuntime(Bridge(), clock=clock)
    cross = Pad(buttons=("cross",))
    sent = run(runtime, clock, [(0.033, cross), (0.37, cross), (0.033, cross), (0.033, NEUTRAL_PAD)])
    assert sent == [("cross",), (), (), ()]
    assert runtime.cut == 1


def test_the_button_is_free_again_once_the_skill_has_let_go_of_it():
    clock = Clock()
    runtime = ControllerRuntime(Bridge(), clock=clock)
    cross = Pad(buttons=("cross",))
    steps = [(0.033, cross), (0.4, cross), (0.033, NEUTRAL_PAD), (0.033, cross), (0.033, cross)]
    sent = run(runtime, clock, steps)
    assert sent == [("cross",), (), (), ("cross",), ("cross",)]
    assert presses(sent, "cross") == 2  # two presses were asked for: one before the gap, one after


def test_a_gap_cuts_only_what_was_down_and_leaves_sticks_and_triggers_alone():
    clock = Clock()
    runtime = ControllerRuntime(Bridge(), clock=clock)
    first = Pad(buttons=("square",), left=(0.0, -1.0), r2=1.0)
    second = Pad(buttons=("square", "cross"), left=(0.0, -1.0), r2=1.0)
    run(runtime, clock, [(0.033, first), (0.5, second)])
    last = runtime.bridge.calls[-1]
    # Square was down before the gap and is not pressed again; the cross is a new press.
    assert last.buttons == ("cross",)
    assert last.left[1] < 0 and last.r2 > 0


def test_a_press_begun_after_a_gap_is_a_press():
    clock = Clock()
    runtime = ControllerRuntime(Bridge(), clock=clock)
    sent = run(runtime, clock, [(0.033, NEUTRAL_PAD), (0.6, Pad(buttons=("triangle",)))])
    assert sent == [(), ("triangle",)]


def test_a_pad_the_bridge_refused_left_nothing_down():
    clock = Clock()
    bridge = Bridge(status=409)
    runtime = ControllerRuntime(bridge, clock=clock)
    cross = Pad(buttons=("cross",))
    run(runtime, clock, [(0.033, cross)])
    assert runtime.down == frozenset()


def test_a_sprint_that_is_held_is_a_state_and_comes_back_after_a_gap():
    profile.use("gta6")
    clock = Clock()
    runtime = ControllerRuntime(Bridge(), clock=clock)
    held = Pad(buttons=("l3",), left=(0.0, -1.0))
    sent = run(runtime, clock, [(0.033, held), (0.5, held), (0.033, held)])
    assert sent == [("l3",)] * 3


def test_the_calibration_s_raw_pads_leave_as_asked():
    clock = Clock()
    runtime = ControllerRuntime(Bridge(), clock=clock, raw=True)
    cross = Pad(buttons=("cross",))
    sent = run(runtime, clock, [(0.033, cross), (0.5, cross)])
    assert sent == [("cross",), ("cross",)]
