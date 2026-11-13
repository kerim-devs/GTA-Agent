import importlib.util
import math
from pathlib import Path

import pytest

from pilot.combat import (
    BURST_SECONDS,
    BURSTS_PER_LOCK,
    MELEE_PULSE,
    MELEE_PULSES_PER_LOCK,
    Fight,
    Melee,
)
from pilot.contract import NEUTRAL_PAD, Blip, Hud, Reading
from pilot.skills import Observation

FRONT_RED = (Blip("red", 0, 8),)


def observation(time, blips=FRONT_RED, *, mode="flat", corrupt=False, health=None, missing=False):
    reading = None if missing else Reading(mode, "none", None, None, None, corrupt, 0.9, blips=blips)
    return Observation(reading, False, time, hud=Hud(health=health) if health is not None else None)


def advance(skill, begin, end, **kwargs):
    return [
        skill.step(observation(tick / 30, **kwargs)) for tick in range(round(begin * 30), round(end * 30) + 1)
    ]


@pytest.mark.parametrize("kind,limit", [(Fight, 30), (Melee, 10)])
def test_metadata_validation_and_clamping(kind, limit):
    assert len(kind.prompt) <= 400
    assert kind({"duration": 100}).args["duration"] == limit
    assert kind({"duration": -10}).args["duration"] > 0
    assert kind({}).args["duration"] == limit
    for args in (
        {"unknown": 1},
        {"duration": True},
        {"duration": "3"},
        {"duration": None},
        {"duration": math.nan},
        {"duration": math.inf},
        {"cover": True},
        {"cover": "maybe"},
        [],
        None,
    ):
        with pytest.raises(ValueError):
            kind(args)


@pytest.mark.parametrize("kind", [Fight, Melee])
@pytest.mark.parametrize("x,y", [(8, 0), (-8, 0), (1, -8), (-1, -8)])
def test_faces_nearest_red_without_attack(kind, x, y):
    skill = kind({})
    result = skill.step(observation(0, (Blip("red", x, y), Blip("red", -x * 5, 30), Blip("blue", 0, 1))))
    if kind is Fight:
        assert result.pad.l2 == 1 and result.pad.r2 == 0
        assert result.pad.right == (0, 0)
    else:
        assert result.pad.right[0] * x > 0
        assert result.pad.l2 == result.pad.r2 == 0
    assert not result.pad.buttons


@pytest.mark.parametrize("kind", [Fight, Melee])
def test_aim_bursts_gaps_and_retarget(kind):
    skill = kind({})
    results = advance(skill, 0, 3)
    pads = [result.pad for result in results]
    assert pads[0].l2 and not pads[0].r2 and not pads[0].buttons
    attacks = [bool(p.r2 or "circle" in p.buttons) for p in pads]
    assert sum(attacks) > 3
    assert any(attacks[i] and not attacks[i + 1] for i in range(len(attacks) - 1))
    assert any(p.l2 and not p.r2 and not p.buttons for p in pads[10:])
    assert any(p == NEUTRAL_PAD for p in pads[10:])
    first_release = next(i for i, pad in enumerate(pads) if pad == NEUTRAL_PAD)
    assert any(pad.l2 for pad in pads[first_release + 1 :])
    assert all(not set(p.buttons) & {"ps", "create"} and p.left == (0, 0) for p in pads)
    assert all(p.r2 == 0 for p in pads) if kind is Melee else all(not p.buttons for p in pads)


@pytest.mark.parametrize("kind", [Fight, Melee])
def test_target_moves_behind_camera_releases_every_attack(kind):
    skill = kind({})
    assert any(r.pad.r2 or "circle" in r.pad.buttons for r in advance(skill, 0, 0.5))
    result = skill.step(observation(0.53, (Blip("red", 1, -8),)))
    if kind is Fight:
        assert not result.pad.r2
        assert not result.pad.l2 or result.pad.right == (0, 0)
    else:
        assert result.pad.right[0] > 0
        assert result.pad.r2 == result.pad.l2 == 0 and not result.pad.buttons


@pytest.mark.parametrize("kind", [Fight, Melee])
def test_target_disappears_during_attack_releases_every_control(kind):
    skill = kind({})
    assert any(r.pad.r2 or "circle" in r.pad.buttons for r in advance(skill, 0, 0.5))
    assert skill.step(observation(0.53, ())).pad == NEUTRAL_PAD


@pytest.mark.parametrize("kind", [Fight, Melee])
@pytest.mark.parametrize("bad", [{"missing": True}, {"corrupt": True}, {"mode": "none"}, {"mode": "tilted"}])
def test_bad_map_neutralizes_immediately_and_fails_bounded(kind, bad):
    skill = kind({})
    advance(skill, 0, 0.5)
    results = advance(skill, 0.6, 2.8, **bad)
    assert all(result.pad == NEUTRAL_PAD for result in results)
    assert results[-1].status == "failed"
    assert results[-1].reason == "minimap-unreadable"
    assert skill.step(observation(3)).pad == NEUTRAL_PAD


@pytest.mark.parametrize("kind", [Fight, Melee])
def test_readable_empty_map_is_observed_success(kind):
    results = advance(kind({}), 0, 2.1, blips=(Blip("blue", 1, 1),))
    assert all(result.status == "running" for result in results[:60])
    assert results[-1].status == "done"
    assert results[-1].reason == "no-red-blips"
    assert all(result.pad == NEUTRAL_PAD for result in results)


def test_clear_confirmation_never_counts_unreadable_or_unsampled_time():
    skill = Fight({})
    advance(skill, 0, 1.5, blips=())
    advance(skill, 1.6, 2.1, missing=True)
    assert skill.step(observation(2.2, blips=())).status == "running"
    assert advance(skill, 2.23, 4, blips=())[-1].status == "running"
    assert advance(skill, 4.03, 4.3, blips=())[-1].status == "done"
    skill = Fight({})
    skill.step(observation(0, blips=()))
    assert skill.step(observation(3, blips=())).status == "running"


def test_short_gap_pauses_confirmation_and_red_resets_it():
    skill = Fight({})
    advance(skill, 0, 1.5, blips=())
    skill.step(observation(1.53, missing=True))
    assert advance(skill, 1.57, 2, blips=())[-1].status == "running"
    assert advance(skill, 2.03, 2.2, blips=())[-1].status == "done"
    skill = Fight({})
    advance(skill, 0, 1.9, blips=())
    skill.step(observation(1.93))
    assert advance(skill, 1.97, 3, blips=())[-1].status == "running"


@pytest.mark.parametrize("kind", [Fight, Melee])
@pytest.mark.parametrize("cover", ["no", "yes"])
def test_low_health_pauses_and_cover_is_one_press(kind, cover):
    skill = kind({"cover": cover})
    advance(skill, 0, 0.5)
    results = advance(skill, 0.6, 3, health=0.2)
    if kind is Fight:
        assert all(r.reason == "health-still-low" and r.pad == NEUTRAL_PAD for r in results)
        return
    assert results[0].pad.buttons == (("r1",) if cover == "yes" else ())
    assert all(r.pad == NEUTRAL_PAD for r in results[5:])
    presses = ["r1" in r.pad.buttons for r in results]
    assert sum(pressed and (i == 0 or not presses[i - 1]) for i, pressed in enumerate(presses)) == (
        cover == "yes"
    )
    assert all(r.pad.r2 == r.pad.l2 == 0 for r in results)
    assert any(r.pad.buttons for r in advance(skill, 3.03, 3.7, health=0.5))


@pytest.mark.parametrize("kind", [Fight, Melee])
def test_unrecovered_health_fails_and_missing_hud_resumes_after_wait(kind):
    results = advance(kind({}), 0, 4.1, health=0.2)
    assert results[-1].status == "failed"
    assert results[-1].reason == "health-still-low"
    assert results[-1].pad == NEUTRAL_PAD
    skill = kind({})
    skill.step(observation(0, health=0.2))
    results = advance(skill, 0.03, 4.8)
    if kind is Fight:
        assert all(r.pad == NEUTRAL_PAD and r.status == "failed" for r in results)
    else:
        assert any(r.pad.buttons for r in results)


@pytest.mark.parametrize("kind", [Fight, Melee])
def test_depleted_health_is_terminal_even_without_map(kind):
    result = kind({}).step(observation(0, health=0, missing=True))
    assert result.reason == "health-depleted"
    assert result.pad == NEUTRAL_PAD


@pytest.mark.parametrize("kind", [Fight, Melee])
def test_stop_timeout_and_replacement_never_leave_input_held(kind):
    old = kind({})
    advance(old, 0, 0.5)
    stopped = old.stop("replaced")
    assert stopped.status == "failed" and stopped.pad == NEUTRAL_PAD
    assert old.step(observation(0.6)) == stopped
    skill = kind({"duration": 1})
    result = advance(skill, 0, 1)[-1]
    assert result.reason == "combat-timeout" and result.pad == NEUTRAL_PAD
    assert skill.step(observation(1.1)) == result


@pytest.mark.parametrize("bad_time", [math.nan, math.inf, -1])
def test_bad_clock_fails_neutral(bad_time):
    skill = Fight({})
    skill.step(observation(0))
    assert skill.step(observation(bad_time)).pad == NEUTRAL_PAD
    assert skill.finished.reason == "invalid-observation-time"


@pytest.mark.parametrize("blip", [Blip("red", 0, 40), Blip("red", 0, 5, border=True)])
def test_melee_requires_close_target(blip):
    result = Melee({}).step(observation(0, (blip,)))
    assert result.reason == "melee-target-too-far"
    assert result.pad == NEUTRAL_PAD


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parents[1] / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_seeded_delayed_combat_clears_majority_and_fails_safely():
    simulate = load_tool("sim_combat").simulate
    runs = [simulate(seed) for seed in range(20)]
    assert sum(run["cleared"] for run in runs) > len(runs) / 2
    assert all(run["seconds"] <= 30 and run["neutral_end"] and not run["invalid_attacks"] for run in runs)
    killed = [simulate(seed, pressure=30) for seed in range(5)]
    assert any(run["reason"] in ("health-depleted", "health-still-low") for run in killed)
    assert all(run["neutral_end"] and not run["invalid_attacks"] for run in killed)
    assert simulate(0, map_lost=True)["reason"] == "minimap-unreadable"
    assert all(simulate(seed, melee=True)["neutral_end"] for seed in range(5))


def test_recording_pad_intervals_clip_window_and_include_held_controls():
    intervals = load_tool("evaluate_combat").intervals
    rows = [{"t": t, "buttons": (), "l2": value} for t, value in [(-1, 1), (0.5, 0), (1, 1), (2, 0), (3, 1)]]
    assert intervals(rows, "l2", 0, 4) == [[0, 0.5], [1, 2], [3, 4]]


@pytest.mark.parametrize(
    ("kind", "count", "pulse"),
    [(Fight, BURSTS_PER_LOCK, BURST_SECONDS), (Melee, MELEE_PULSES_PER_LOCK, MELEE_PULSE)],
)
def test_attacks_are_pulses_and_not_a_held_button(kind, count, pulse):
    skill = kind({})
    lock = []
    for result in advance(skill, 0, 3):
        if result.pad == NEUTRAL_PAD:
            break
        lock.append(bool(result.pad.r2 or "circle" in result.pad.buttons))
    starts = sum(now and not before for before, now in zip([False, *lock], lock, strict=False))
    longest = max(len(run) for run in "".join("x" if attack else " " for attack in lock).split())
    assert starts == count
    assert longest <= math.ceil(pulse * 30) + 1


@pytest.mark.parametrize("kind", [Fight, Melee])
def test_combat_takes_accepted_mode_over_opposite_map(kind):
    from dataclasses import replace

    def observed(minimap, accepted):
        base = observation(0)
        return replace(base, reading=replace(base.reading, minimap=minimap), mode=accepted)

    assert kind({}).step(observed("tilted", "foot")).pad.l2 == 1
    assert kind({}).step(observed("flat", "vehicle")).pad == NEUTRAL_PAD
    result = kind({}).step(observed("flat", "none"))
    assert result.status == "running" and result.pad == NEUTRAL_PAD


def test_fight_clock_matches_recorded_first_shot_and_release():
    from pilot.combat import AIM_HOLD, AIM_SETTLE, RETARGET_SECONDS

    skill = Fight({})
    samples = [(i / 1000, skill.step(observation(i / 1000))) for i in range(2000)]
    first = next(t for t, result in samples if result.pad.r2)
    assert AIM_SETTLE <= first <= AIM_SETTLE + 0.001
    release = next(t for t, result in samples if t > first and not result.pad.l2)
    assert AIM_HOLD <= release <= AIM_HOLD + 0.001
    relock = next(t for t, result in samples if t > release and result.pad.l2)
    assert RETARGET_SECONDS <= relock - release <= RETARGET_SECONDS + 0.001


def test_fight_turns_only_after_releasing_its_first_lock():
    skill = Fight({})
    results = advance(skill, 0, 2, blips=(Blip("red", 8, 0),))
    assert results[0].pad.l2 and results[0].pad.right == (0, 0)
    assert any(result.pad.r2 for result in results)
    assert any(result.pad.right[0] > 0 for result in results)
    assert all(not result.pad.right[0] or (not result.pad.l2 and not result.pad.r2) for result in results)
    aligned = skill.step(observation(2.03))
    assert aligned.pad.l2 and aligned.pad.right == (0, 0)


@pytest.mark.parametrize("cover", ["no", "yes"])
def test_confirmed_hit_moves_or_taps_cover_and_releases(cover):
    from dataclasses import replace

    skill = Fight({"cover": cover})
    results = []
    for tick in range(150):
        health = 0.9 if tick < 60 else 0.7
        obs = replace(observation(tick / 30), hud=Hud(wanted=0, health=health, armour=0.0, special=1.0))
        results.append(skill.step(obs))
    if cover == "yes":
        assert any("r1" in result.pad.buttons for result in results)
        assert all(
            not result.pad.r2 and not result.pad.l2 for result in results if "r1" in result.pad.buttons
        )
    else:
        assert any(result.pad.left[0] < 0 and result.pad.l2 for result in results)
    assert results[-1].pad.left == (0, 0)
    assert skill.stop().pad == NEUTRAL_PAD


@pytest.mark.parametrize("stars", [1, 3, 5])
def test_stars_end_neutral_even_on_the_shot_tick(stars):
    from dataclasses import replace

    skill = Fight({})
    advance(skill, 0, 0.4)
    result = skill.step(replace(observation(0.43), hud=Hud(wanted=stars, health=1.0)))
    assert result.status == "failed" and result.reason == "stars" and result.pad == NEUTRAL_PAD
    assert skill.step(observation(0.46)) == result


def test_health_below_one_third_is_terminal_before_locking():
    result = Fight({"cover": "yes"}).step(observation(0, health=0.32))
    assert result.status == "failed" and result.reason == "health-still-low"
    assert result.pad == NEUTRAL_PAD


def test_melee_uses_punch_authority_and_never_fires():
    from pilot.combat import MELEE_GAP
    from pilot.punch import Punch

    assert MELEE_PULSE == Punch.PULSE_DURATION
    assert MELEE_PULSE + MELEE_GAP == Punch.PULSE_PERIOD
    assert all(not r.pad.r2 for r in advance(Melee({}), 0, 4))


def test_recorded_intervals_count_button_edges_not_samples():
    intervals = load_tool("evaluate_combat").intervals
    rows = [
        {"t": t, "buttons": buttons}
        for t, buttons in [(0, ()), (1, ("square",)), (1.2, ("square",)), (1.4, ())]
    ]
    assert intervals(rows, "square", 0, 2) == [[1, 1.4]]


def test_measured_policy_reaches_target_sooner_across_lock_cone_assumptions():
    comparison = load_tool("sim_combat").compare_first_shot()
    assert len(comparison["rows"]) == 9
    assert all(row["target_met"] for row in comparison["rows"])


def test_accepted_foot_mode_cannot_override_an_absent_map_on_a_shot_tick():
    from dataclasses import replace

    skill = Fight({})
    advance(skill, 0, 0.2)
    result = skill.step(replace(observation(0.23, mode="none"), mode="foot"))
    assert result.pad == NEUTRAL_PAD
