"""Scripted pad traces, including every exit while the wheel is held."""

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

import pilot.switch as switching
from pilot.contract import Hud, Observation, Pad, Reading
from pilot.switch import DIRECTIONS, SLOTS, STORY, SwitchCharacter


@pytest.fixture
def rig(monkeypatch):
    state = SimpleNamespace(visible=False, highlight=None, disabled=frozenset())

    class Text:
        objective = None
        fresh = True

        def submit(self, frame, now):
            self.now = now

        def read(self):
            return (self.now, self.objective) if self.fresh else None

        def close(self):
            pass

    monkeypatch.setattr(switching, "_Objectives", Text)
    monkeypatch.setattr(switching, "wheel", lambda frame: state)
    return state


FRAME = np.zeros((720, 1280, 3), dtype=np.uint8)


def obs(time, **kwargs):
    return replace(
        Observation(
            Reading("flat", "none", None, None, None, False, 1.0),
            False,
            time,
            FRAME,
            hud=Hud(wanted=0, screen="game"),
            mode="foot",
        ),
        **kwargs,
    )


def assert_safe(trace):
    previous = Pad()
    released = None
    for time, result in trace:
        pad = result.pad
        assert pad.right[1] <= 0
        assert pad.left == (0.0, 0.0) and pad.l2 == 0 and pad.r2 == 0
        assert set(pad.buttons) <= {"down"}
        if "down" in previous.buttons and "down" not in pad.buttons:
            assert pad.right in DIRECTIONS.values()
            released = time
        if released is not None and time - released < 0.25:
            assert pad.right in DIRECTIONS.values()
        previous = pad


def enter(skill, rig, phase):
    trace = [(0, skill.step(obs(0)))]
    if phase == "opening":
        return trace
    rig.visible, rig.highlight = True, "left"
    trace.append((0.1, skill.step(obs(0.1))))
    if phase == "selecting":
        return trace
    if phase == "rescuing":
        rig.highlight = "bottom"
        trace.append((0.2, skill.step(obs(0.2))))
        return trace
    rig.highlight = "top"
    trace.extend((t, skill.step(obs(t))) for t in (0.2, 0.3))
    if phase == "releasing":
        return trace
    rig.visible = False
    trace.append((0.6, skill.step(obs(0.6))))
    return trace


@pytest.mark.parametrize("current", STORY)
def test_next_round_and_success(rig, current):
    skill = SwitchCharacter({})
    trace = [(0, skill.step(obs(0)))]
    rig.visible, rig.highlight = True, SLOTS[current]
    trace.append((0.1, skill.step(obs(0.1))))
    expected = STORY[(STORY.index(current) + 1) % 3]
    assert trace[-1][1].pad.right == DIRECTIONS[SLOTS[expected]]
    rig.highlight = SLOTS[expected]
    trace.extend((t, skill.step(obs(t))) for t in (0.2, 0.3, 0.4, 0.549))
    rig.visible = False
    # A flying camera/loading screen is not a successful return.
    trace.append((0.6, skill.step(obs(0.6, hud=Hud(screen="loading")))))
    trace.extend((t, skill.step(obs(t))) for t in (9.0, 9.9, 10.0))
    assert trace[-1][1].status == "done"
    assert trace[-1][1].reason == f"switched: {expected}; was: {current}"
    assert trace[-1][1].pad == Pad()
    assert_safe(trace)


@pytest.mark.parametrize("phase", ["opening", "selecting", "rescuing", "releasing", "returning"])
def test_external_stop_returns_story_fallback_at_every_phase(rig, phase):
    skill = SwitchCharacter({})
    trace = enter(skill, rig, phase)
    result = skill.stop()
    trace.append((trace[-1][0] + 0.01, result))
    assert result.status == "failed" and result.reason.startswith("interrupted")
    assert result.pad.right in DIRECTIONS.values() and "down" not in result.pad.buttons
    assert_safe(trace)
    # There is no drain protocol in the runner; this is only its one-pad fallback.
    assert skill.step(obs(5)).pad == Pad()


@pytest.mark.parametrize("phase", ["opening", "selecting", "rescuing", "releasing", "returning"])
@pytest.mark.parametrize("bad", ["missing", "damaged", "wrong", "shape"])
def test_bad_pictures_at_every_phase(rig, phase, bad):
    skill = SwitchCharacter({"duration": 4})
    trace = enter(skill, rig, phase)
    broken = {
        "missing": {"frame": None},
        "damaged": {"reading": replace(obs(0).reading, corrupt=True)},
        "wrong": {"hud": Hud(screen="pause")},
        "shape": {"frame": np.zeros((2, 2, 3), dtype=np.uint8)},
    }[bad]
    trace.extend((t, skill.step(obs(t, **broken))) for t in (0.7, 0.8, 1, 2.3, 2.6, 4.1, 4.4))
    assert trace[-1][1].status == "failed"
    assert trace[-1][1].pad == Pad()
    assert_safe(trace)


@pytest.mark.parametrize("kind", ["frame", "hud", "stars", "unknown-stars", "mode", "minimap", "objective"])
def test_refusal_has_no_input(rig, kind):
    skill = SwitchCharacter({})
    changes = {
        "frame": {"frame": None},
        "hud": {"hud": Hud(screen="map")},
        "stars": {"hud": Hud(wanted=1)},
        "unknown-stars": {"hud": Hud()},
        "mode": {"mode": "none"},
        "minimap": {"reading": replace(obs(0).reading, minimap="none")},
        "objective": {},
    }[kind]
    if kind == "objective":
        skill.text.objective = "Drive to the target"
    result = skill.step(obs(0, **changes))
    assert result.status == "failed" and result.reason.startswith("switch-refused:")
    assert result.pad == Pad()


def test_unread_objective_never_opens(rig):
    skill = SwitchCharacter({"duration": 4})
    skill.text.fresh = False
    results = [skill.step(obs(t)) for t in (0, 1, 3, 4)]
    assert all(result.pad == Pad() for result in results)
    assert results[-1].reason == "switch-refused: objective-unread"


def test_stop_before_opening_has_no_input(rig):
    skill = SwitchCharacter({})
    result = skill.stop()
    assert result.pad == Pad() and result.reason == "interrupted"


def test_opening_timeout_uses_top_when_previous_figure_is_unknown(rig):
    skill = SwitchCharacter({})
    trace = [(t, skill.step(obs(t))) for t in (0, 1, 3, 3.1, 3.3)]
    assert trace[2][1].pad == Pad(right=(0, -1))
    assert trace[-1][1].reason == "wheel-unread"
    assert_safe(trace)


def test_explicit_current_target_uses_current_slot_to_exit(rig):
    skill = SwitchCharacter({"to": "michael"})
    trace = [(0, skill.step(obs(0)))]
    rig.visible, rig.highlight = True, "left"
    trace.extend((t, skill.step(obs(t))) for t in (0.1, 0.2, 0.4))
    assert trace[-1][1].reason == "switch-refused: already-current; was: michael"
    assert_safe(trace)


def test_next_skips_disabled_and_explicit_disabled_refuses(rig):
    for args, reason in (({}, None), ({"to": "franklin"}, "switch-refused: unavailable")):
        skill = SwitchCharacter(args)
        trace = [(0, skill.step(obs(0)))]
        rig.visible, rig.highlight, rig.disabled = True, "left", frozenset({"top"})
        trace.append((0.1, skill.step(obs(0.1))))
        if reason is None:
            assert skill.chosen == "trevor"
        else:
            trace.append((0.4, skill.step(obs(0.4))))
            assert trace[-1][1].reason == f"{reason}; was: michael"
        assert_safe(trace)


@pytest.mark.parametrize("story_returns", [True, False])
def test_bottom_keeps_down_until_story_or_two_seconds(rig, story_returns):
    skill = SwitchCharacter({})
    trace = enter(skill, rig, "rescuing")
    assert trace[-1][1].pad == Pad(buttons=("down",), right=(0.0, -1.0))
    trace.append((0.3, skill.step(obs(0.3))))
    assert "down" in trace[-1][1].pad.buttons
    if story_returns:
        rig.highlight = "top"
    release_time = 0.4 if story_returns else 2.2
    trace.append((release_time, skill.step(obs(release_time))))
    trace.append((release_time + 0.3, skill.step(obs(release_time + 0.3))))
    assert trace[-1][1].reason == "online-slot-seen; was: michael"
    assert_safe(trace)


@pytest.mark.parametrize("phase", ["opening", "selecting", "returning"])
def test_deadlines_release_on_known_story_slot(rig, phase):
    skill = SwitchCharacter({"duration": 4})
    trace = enter(skill, rig, phase)
    trace.extend((t, skill.step(obs(t))) for t in (4, 4.1, 4.3))
    assert trace[-1][1].reason.startswith("time-limit")
    assert_safe(trace)


def test_unread_target_returns_to_previous_figure(rig):
    skill = SwitchCharacter({})
    trace = enter(skill, rig, "selecting")
    trace.extend((t, skill.step(obs(t))) for t in (2, 3.1, 3.2, 3.4))
    assert trace[-2][1].pad.right == DIRECTIONS["left"]
    assert trace[-1][1].reason == "wheel-unread; was: michael"
    assert_safe(trace)


def test_target_needs_two_consecutive_highlights(rig):
    skill = SwitchCharacter({})
    enter(skill, rig, "selecting")
    for time, highlight in ((0.2, "top"), (0.3, "left"), (0.4, "top")):
        rig.highlight = highlight
        assert "down" in skill.step(obs(time)).pad.buttons
    assert "down" not in skill.step(obs(0.5)).pad.buttons


def test_unknown_selection_gets_safe_top_rescue(rig):
    skill = SwitchCharacter({})
    trace = enter(skill, rig, "selecting")
    rig.highlight = None
    trace.extend((t, skill.step(obs(t))) for t in (0.2, 1, 2.2, 2.5))
    assert trace[2][1].pad == Pad(buttons=("down",), right=(0, -1))
    assert trace[-1][1].reason == "wheel-unread; was: michael"
    assert_safe(trace)


def test_duplicate_capture_is_not_a_second_confirmation(rig):
    skill = SwitchCharacter({})
    enter(skill, rig, "selecting")
    rig.highlight = "top"
    first = skill.step(obs(0.2))
    assert "down" in first.pad.buttons
    assert skill.step(obs(0.2)) == first
    assert "down" not in skill.step(obs(0.3)).pad.buttons


@pytest.mark.parametrize(
    "args",
    [
        {"x": 1},
        {"to": "online"},
        {"duration": True},
        {"duration": float("nan")},
        {"duration": float("inf")},
        [],
    ],
)
def test_bad_arguments(args):
    with pytest.raises(ValueError):
        SwitchCharacter(args)


def test_duration_clamps_and_prompt(rig):
    assert SwitchCharacter({"duration": 1}).limit == 4
    assert SwitchCharacter({"duration": 100}).limit == 40
    assert len(SwitchCharacter.prompt) <= 400


@pytest.mark.parametrize("bad_time", [float("nan"), float("inf"), -1.0])
def test_bad_clock_cannot_skip_release_hold(rig, bad_time):
    skill = SwitchCharacter({})
    trace = enter(skill, rig, "selecting")
    trace.append((0.1, skill.step(obs(bad_time))))
    trace.extend((t, skill.step(obs(t))) for t in (0.2, 0.3, 0.4))
    assert trace[-1][1].status == "failed"
    assert "clock-" in trace[-1][1].reason
    assert_safe(trace)
