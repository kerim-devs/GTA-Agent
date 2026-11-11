from dataclasses import replace

import pytest

from pilot.contract import Observation, Pad, Reading
from pilot.head import SkillCall, parse_response
from pilot.level import LevelCamera
from pilot.skills import REGISTRY, make_skill

FLAT = Reading("flat", "none", None, None, 0.0, False, 0.9)
TILTED = replace(FLAT, minimap="tilted")
NEUTRAL = Pad()


def run(skill, reading=FLAT, *, hz=30, seconds=12.0, readings=None):
    """Tick the skill and return (time, pad) per tick until it ends, and the last result."""
    rows, result = [], None
    for index in range(int(seconds * hz)):
        t = index / hz
        now = readings(t) if readings else reading
        result = skill.step(Observation(now, True, t))
        if result.status != "running":
            break
        rows.append((t, result.pad))
    return rows, result


def held(rows, wanted):
    """Seconds the right stick was at `wanted`, counted tick by tick."""
    return sum(b[0] - a[0] for a, b in zip(rows, rows[1:], strict=False) if a[1].right == wanted)


def test_the_move_runs_into_the_upper_stop_and_comes_back_by_four_pulses():
    rows, result = run(LevelCamera({}))
    assert result.status == "done" and result.reason == "levelled"
    assert held(rows, (0.0, -1.0)) == pytest.approx(2.0, abs=0.04)
    assert held(rows, (0.0, 0.5)) == pytest.approx(4 * 0.3, abs=0.14)
    # Up first, then four separate pulses down with the stick let go between them.
    sticks = [pad.right for _, pad in rows]
    changes = [stick for index, stick in enumerate(sticks) if index == 0 or stick != sticks[index - 1]]
    assert changes == [(0.0, -1.0), (0.0, 0.0)] + [(0.0, 0.5), (0.0, 0.0)] * 4
    assert rows[-1][0] == pytest.approx(5.7, abs=0.1)


def test_it_moves_nothing_but_the_tilt():
    rows, _ = run(LevelCamera({}))
    for _, pad in rows:
        assert pad.right[0] == 0.0
        assert replace(pad, right=(0.0, 0.0)) == NEUTRAL


def test_in_a_vehicle_it_sends_nothing_and_does_not_count_as_a_failure():
    rows, result = run(LevelCamera({}), TILTED)
    assert all(pad == NEUTRAL for _, pad in rows)
    assert result.status == "done" and result.reason == "not on foot"
    assert rows[-1][0] == pytest.approx(1.5, abs=0.05)


def test_a_wrong_map_class_for_most_of_a_second_does_not_call_it_a_vehicle():
    rows, result = run(LevelCamera({}), readings=lambda t: TILTED if t < 0.83 else FLAT)
    assert result.reason == "levelled"
    assert all(pad == NEUTRAL for t, pad in rows if t < 0.83)
    assert held(rows, (0.0, -1.0)) == pytest.approx(2.0, abs=0.04)


def test_a_damaged_tick_in_the_middle_does_not_change_the_move():
    damaged = replace(FLAT, corrupt=True)
    rows, result = run(LevelCamera({}), readings=lambda t: damaged if 1.0 <= t < 1.5 else FLAT)
    assert result.reason == "levelled"
    assert held(rows, (0.0, -1.0)) == pytest.approx(2.0, abs=0.04)


def test_a_late_tick_does_not_count_as_stick_time():
    skill = LevelCamera({})
    times = [index / 30 for index in range(30)] + [3.0 + index / 30 for index in range(120)]
    pads = [(t, skill.step(Observation(FLAT, True, t)).pad) for t in times]
    # One second of the stick was sent before the stall; another second has to follow it.
    after = [(t, pad) for t, pad in pads if t >= 3.0]
    assert held(after, (0.0, -1.0)) == pytest.approx(1.0 - 0.1, abs=0.07)


def test_time_limit_and_arguments():
    skill = LevelCamera({"duration": 6.0})
    assert skill.limit == 6.0
    assert LevelCamera({"duration": 99}).limit == 12.0
    with pytest.raises(ValueError):
        LevelCamera({"angle": 3})
    with pytest.raises(ValueError):
        LevelCamera({"duration": True})
    stalled = LevelCamera({})
    stalled.step(Observation(FLAT, True, 0.0))
    assert stalled.step(Observation(FLAT, True, 9.0)).reason == "time-limit"
    assert stalled.step(Observation(FLAT, True, 9.1)).status == "failed"


def test_the_head_can_plan_it():
    assert REGISTRY["level_camera"] is LevelCamera
    decision = parse_response({"plan": [{"name": "level_camera", "args": {}}], "sentence": "Kamera gerade."})
    assert isinstance(make_skill(decision.plan[0]), LevelCamera)
    assert isinstance(make_skill(SkillCall("level_camera", {"duration": 7})), LevelCamera)
