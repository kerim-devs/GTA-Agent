"""The hit signal: a step down of the health bar, told from the HUD readings of every tick.

The synthetic sequences pin the rules; the real ones in lab/health/ are read from the recorded HUD
strips by the reader itself, frame by frame, at the conductor's thirty ticks a second.
"""

import json
from pathlib import Path
from statistics import median

import cv2
import pytest

from pilot.contract import Hud
from pilot.hits import DROP, QUIET_S, Hit, Hits
from pilot.hud import read

TICK = 1 / 30
LAB = Path(__file__).resolve().parents[2] / "lab"
HEALTH = json.loads((LAB / "health/cases.json").read_text())
CASES = {case["name"]: case for case in HEALTH["cases"]}
HITS = [name for name, case in CASES.items() if case["kind"] == "hit"]
FALSE_FALLS = [name for name, case in CASES.items() if case["kind"] != "hit"]


def bar(health):
    return Hud(health=health, armour=0.0, special=1.0)


def feed(hits, start, readings):
    """Feed one reading per tick from `start`; the hits and the time after the last tick."""
    found = []
    t = start
    for reading in readings:
        hit = hits.update(t, reading)
        if hit is not None:
            found.append(hit)
        t += TICK
    return found, t


def settled(health=0.8, seconds=2.0):
    """A signal past its quiet first second with a level of `health`."""
    hits = Hits()
    found, t = feed(hits, 0.0, [bar(health)] * round(seconds / TICK))
    assert found == []
    assert hits.level == pytest.approx(health)
    return hits, t


def test_a_step_down_is_a_hit_on_the_third_agreeing_reading():
    hits, t = settled(0.8)
    found, _ = feed(hits, t, [bar(0.6)] * 5)
    assert len(found) == 1
    hit = found[0]
    assert hit.since == pytest.approx(t)
    assert hit.time == pytest.approx(t + 2 * TICK)
    assert (hit.before, hit.after) == (pytest.approx(0.8), pytest.approx(0.6))
    assert hit.drop == pytest.approx(0.2)
    # The new level is the one the next hit is measured from.
    found, _ = feed(hits, t + 5 * TICK, [bar(0.6)] * 10 + [bar(0.4)] * 3)
    assert [(h.before, h.after) for h in found] == [(pytest.approx(0.6), pytest.approx(0.4))]


@pytest.mark.parametrize("odd", [[0.5], [0.5, 0.5], [0.5, 0.8, 0.5]])
def test_one_odd_tick_or_two_decide_nothing(odd):
    hits, t = settled(0.8)
    found, _ = feed(hits, t, [bar(v) for v in odd] + [bar(0.8)] * 30)
    assert found == []
    assert hits.level == pytest.approx(0.8)


def test_readings_that_disagree_on_the_new_level_are_no_hit():
    hits, t = settled(0.8)
    found, _ = feed(hits, t, [bar(v) for v in (0.6, 0.5, 0.65, 0.45, 0.6, 0.4)] + [bar(0.8)] * 10)
    assert found == []


def test_a_tick_without_a_value_is_stood_out():
    hits, t = settled(0.8)
    # Neither a reading without health nor a frame without the HUD's bars in between breaks the
    # three agreeing readings or confirms them.
    gap = [Hud(health=None, armour=0.0, special=1.0), Hud()]
    found, _ = feed(hits, t, [bar(0.6), gap[0], bar(0.6), gap[1], gap[0], bar(0.6)])
    assert len(found) == 1
    assert found[0].since == pytest.approx(t)
    assert found[0].time == pytest.approx(t + 5 * TICK)


def test_a_step_across_ticks_without_a_value_still_counts():
    # An icon over the bar's end hides it for a second; the first reading after it is lower.
    hits, t = settled(0.45)
    hidden = [Hud(health=None, armour=0.0, special=1.0)] * 30
    found, _ = feed(hits, t, hidden + [bar(0.27)] * 3)
    assert [(h.before, h.after) for h in found] == [(pytest.approx(0.45), pytest.approx(0.27))]


def test_nothing_counts_in_the_first_second_after_the_hud_returns():
    hits, t = settled(0.8)
    # A black screen: the reader gives no bars for half a second.
    _, t = feed(hits, t, [Hud(screen="loading")] * 15)
    # The bar fades back in, read lower at first and at its level later: nothing in the first
    # second counts, and what is read after it is the level.
    back = [bar(0.3)] * 10 + [bar(0.6)] * 50
    found, t = feed(hits, t, back)
    assert found == []
    assert hits.level == pytest.approx(0.6)
    # A hit after that second counts again, measured from the level after the screen.
    found, _ = feed(hits, t, [bar(0.4)] * 3)
    assert [(h.before, h.after) for h in found] == [(pytest.approx(0.6), pytest.approx(0.4))]


def test_a_fall_in_the_quiet_second_is_no_hit():
    hits, t = settled(0.8)
    _, t = feed(hits, t, [Hud(screen="loading")] * 15)
    found, _ = feed(hits, t, [bar(0.8)] * 10 + [bar(0.5)] * 10 + [bar(0.5)] * 40)
    assert found == []


def test_the_weapon_wheel_and_the_phone_keep_the_hud():
    hits, t = settled(0.8)
    wheel = [Hud(health=0.8, armour=0.0, special=1.0, screen="weapon_wheel")] * 20
    found, t = feed(hits, t, wheel)
    found, _ = feed(hits, t, [Hud(health=0.6, armour=0.0, special=1.0, screen="phone")] * 3)
    assert len(found) == 1


def test_a_slide_is_no_hit_and_the_lower_level_is_read_anew():
    hits, t = settled(0.8)
    slide = [bar(0.8 - 0.02 * k) for k in range(1, 11)]
    found, t = feed(hits, t, slide + [bar(0.6)] * 60)
    assert found == []
    assert hits.level == pytest.approx(0.6)
    found, _ = feed(hits, t, [bar(0.45)] * 3)
    assert [(h.before, h.after) for h in found] == [(pytest.approx(0.6), pytest.approx(0.45))]


def test_three_columns_are_no_hit_and_rising_is_none():
    hits, t = settled(0.8)
    found, t = feed(hits, t, [bar(0.8 - 3 / 90)] * 30 + [bar(0.95)] * 60)
    assert found == []


def test_the_same_frame_twice_counts_once():
    hits, t = settled(0.8)
    # The conductor ticks on fresh frames only; a repeated capture time is no second reading.
    assert hits.update(t, bar(0.6)) is None
    assert hits.update(t, bar(0.6)) is None
    assert hits.update(t, bar(0.6)) is None
    assert hits.update(t + TICK, bar(0.6)) is None
    assert isinstance(hits.update(t + 2 * TICK, bar(0.6)), Hit)


def test_a_level_not_read_for_two_seconds_is_forgotten():
    hits, t = settled(0.8)
    found, _ = feed(hits, t, [Hud(health=None, armour=0.0, special=1.0)] * 70 + [bar(0.5)] * 10)
    assert found == []


def recorded(name):
    """(capture time, native index, Hud) of every frame of a lab/health case, as the reader reads
    its HUD strip set into a game frame."""
    (top, bottom), (left, right) = HEALTH["strip"]["rows"], HEALTH["strip"]["columns"]
    stack = cv2.cvtColor(cv2.imread(str(LAB / "health" / f"{name}.png")), cv2.COLOR_BGR2RGB)
    base = cv2.cvtColor(cv2.imread(str(LAB / "hud/fixtures/clean2-07360.png")), cv2.COLOR_BGR2RGB)
    out = []
    for k, (index, time) in enumerate(CASES[name]["frames"]):
        pixels = base.copy()
        pixels[top:bottom, left:right] = stack[k * (bottom - top) : (k + 1) * (bottom - top)]
        out.append((time, index, read(pixels)))
    return out


def replay(frames, level):
    """A signal settled at `level` for two seconds, then fed the recorded frames: its hits with the
    position of the frame that confirmed each."""
    hits = Hits()
    feed(hits, frames[0][0] - 2.0, [bar(level)] * round(2.0 / TICK))
    assert hits.level == pytest.approx(level)
    found = []
    for k, (time, _, hud) in enumerate(frames):
        hit = hits.update(time, hud)
        if hit is not None:
            found.append((k, hit))
    return found


def level_before(name):
    """The level the reader reads before a hit's first shorter frame, as the signal would hold it."""
    case = CASES[name]
    values = [
        hud.health for _, index, hud in recorded(name) if index < case["first"][0] and hud.health is not None
    ]
    return median(values) if values else case["before"]


@pytest.mark.parametrize("name", [n for n in HITS if CASES[n]["before"] - CASES[n]["after"] >= DROP])
def test_a_real_hit_is_signalled_within_six_ticks_of_the_first_shorter_frame(name):
    case = CASES[name]
    frames = recorded(name)
    first = next(k for k, (_, index, _) in enumerate(frames) if index >= case["first"][0])
    found = replay(frames, level_before(name))
    assert found, case["shows"]
    k, hit = found[0]
    assert k - first <= 6
    assert hit.since >= frames[first][0]
    assert hit.after == pytest.approx(case["after"], abs=0.03)


@pytest.mark.parametrize("name", [n for n in HITS if CASES[n]["before"] - CASES[n]["after"] < DROP])
def test_a_hit_of_three_columns_is_not_signalled(name):
    # Readings of a still bar can be a column apart and an icon at the end shortens it by three.
    assert replay(recorded(name), level_before(name)) == []


@pytest.mark.parametrize("name", ["hit-065022-15123", "hit-185323-23660"])
def test_a_real_hit_through_ticks_without_a_value(name):
    case = CASES[name]
    frames = recorded(name)
    first = next(k for k, (_, index, _) in enumerate(frames) if index >= case["first"][0])
    (k, hit), *_ = replay(frames, level_before(name))
    # The reader reads nothing on some of the frames between the first shorter one and the one
    # that confirms the hit; they neither break the hit nor confirm it.
    assert any(hud.health is None for _, _, hud in frames[first:k])
    assert k - first <= 6
    assert hit.after == pytest.approx(case["after"], abs=0.03)


@pytest.mark.parametrize("name", FALSE_FALLS)
def test_the_false_falls_of_the_reaction_bench_are_no_hit(name):
    # The fades, the icons on the bar, the bright sand, enemy-17's stripes and P62's three hit
    # scenes, each from a signal settled at the bar's true level.
    assert replay(recorded(name), CASES[name]["level"]) == []


@pytest.mark.parametrize("name", ["fade-enemy-13", "fade-enemy-15", "fade-enemy-16"])
def test_nothing_counts_in_the_first_second_after_a_real_fade(name):
    hits = Hits()
    back = None
    for time, _, hud in recorded(name):
        assert hits.update(time, hud) is None
        if back is None and any(v is not None for v in (hud.health, hud.armour, hud.special)):
            back = time
        if back is not None and time - back < QUIET_S:
            assert hits.level is None
    assert back is not None
    assert hits.level == pytest.approx(0.99, abs=0.01)
