"""Behavioral checks use the detector's 1280x720 pixel contract throughout."""

from dataclasses import replace
from itertools import pairwise

import pytest

from pilot.contract import NEUTRAL_PAD, Detection, Hud, Reading
from pilot.punch import Punch
from pilot.skills import Observation


def person(box=(560, 200, 720, 660), confidence=0.9):
    return Detection("person", box, confidence)


def obs(time, objects=None, **changes):
    reading = Reading("flat", "none", None, None, None, False, 1.0)
    return replace(
        Observation(
            reading,
            False,
            time,
            objects=(person(),) if objects is None else tuple(objects),
            objects_time=time,
            hud=Hud(health=1.0),
        ),
        **changes,
    )


def safe(result):
    assert result.pad.r2 == 0
    assert set(result.pad.buttons) <= {"circle"}
    if result.pad.l2 or result.pad.buttons:
        assert result.pad.left == (0, 0)
        assert result.pad.right == (0, 0)
    return result


def terminal(skill, result, status):
    assert result.status == status
    assert result.reason
    assert result.pad == NEUTRAL_PAD
    assert skill.step(obs(30)) == result
    assert skill.stop("later stop") == result


def test_selects_near_central_and_keeps_person_as_larger_one_passes():
    skill = Punch({})
    target = person((570, 220, 710, 420))
    side = person((920, 160, 1080, 400))
    safe(skill.step(obs(0, [side, target])))
    expected = tuple(v / scale for v, scale in zip(target.box, (1280, 720, 1280, 720), strict=True))
    assert skill.target == expected
    for index in range(1, 7):
        cx = 1000 - index * 60
        passing = person((cx - 100, 120, cx + 100, 520))
        safe(skill.step(obs(index / 10, [passing, target])))
        assert skill.target == expected


@pytest.mark.parametrize("box", [(900, 150, 1080, 460), (580, 250, 700, 400), (100, 250, 190, 400)])
def test_no_attack_until_centered_and_tall(box):
    result = safe(Punch({}).step(obs(0, [person(box)])))
    assert result.status == "running"
    assert not result.pad.buttons and result.pad.l2 == 0
    assert result.pad != NEUTRAL_PAD


def test_pulses_release_and_end_after_exact_attempt_count():
    skill = Punch({"hits": 3})
    rises = []
    pressed = False
    for index in range(61):
        now = index / 30
        result = safe(skill.step(obs(now)))
        circle = "circle" in result.pad.buttons
        if circle and not pressed:
            rises.append(now)
        if pressed and not circle:
            assert now - rises[-1] <= 0.16
        pressed = circle
        if result.status != "running":
            break
    assert len(rises) == 3
    assert all(b - a >= 0.6 for a, b in pairwise(rises))
    terminal(skill, result, "done")


def test_follows_departing_person_then_attacks_again():
    skill = Punch({"hits": 2})
    assert safe(skill.step(obs(0))).pad.buttons == ("circle",)
    distant = person((580, 220, 700, 420))
    for time in (0.08, 0.3, 0.7):
        result = safe(skill.step(obs(time, [distant])))
        assert result.pad.left[1] < 0 and result.pad.l2 == 0
    assert safe(skill.step(obs(0.8))).pad.buttons == ("circle",)
    terminal(skill, safe(skill.step(obs(0.94))), "done")


def test_ground_box_must_persist_and_repeated_frame_is_not_confirmation():
    skill = Punch({"hits": 6})
    safe(skill.step(obs(0)))
    ground = person((490, 290, 790, 400))
    result = safe(skill.step(obs(0.1, [ground])))
    assert result.pad == NEUTRAL_PAD and result.status == "running"
    result = safe(skill.step(obs(0.56, [ground], objects_time=0.1)))
    assert result.status == "running"
    terminal(skill, safe(skill.step(obs(0.6, [ground]))), "done")


def test_a_figure_that_only_ever_lay_there_is_not_a_knockdown():
    skill = Punch({})
    ground = person((490, 290, 790, 400))
    for time in (0, 0.2, 0.4):
        assert safe(skill.step(obs(time, [ground]))).pad == NEUTRAL_PAD
    result = safe(skill.step(obs(0.5, [ground])))
    terminal(skill, result, "failed")
    assert result.reason == "person already on the ground; face a standing person"


def test_one_wide_box_does_not_end_attack():
    skill = Punch({"hits": 6})
    safe(skill.step(obs(0)))
    safe(skill.step(obs(0.1, [person((490, 290, 790, 400))])))
    assert safe(skill.step(obs(0.2))).status == "running"


def test_person_can_fall_before_first_punch_with_large_height_change():
    skill = Punch({})
    upright = person((720, 190, 820, 460))
    safe(skill.step(obs(0, [upright])))
    assert skill.delivered_hits == 0
    ground = person((620, 335, 920, 380))
    assert safe(skill.step(obs(0.1, [ground]))).pad == NEUTRAL_PAD
    terminal(skill, safe(skill.step(obs(0.6, [ground]))), "done")


def test_leaked_player_is_never_approached_or_punched():
    leak = person((400, 280, 760, 719))
    skill = Punch({})
    for time in (0, 0.3, 1, 2):
        assert safe(skill.step(obs(time, [leak]))).pad == NEUTRAL_PAD
    terminal(skill, safe(skill.step(obs(3, [leak]))), "failed")
    skill = Punch({})
    target = person((760, 220, 900, 430))
    result = safe(skill.step(obs(0, [leak, target])))
    assert result.pad.right[0] > 0
    assert skill.target[0] == target.box[0] / 1280


def test_tall_slim_npc_is_not_confused_with_broad_player_leak():
    skill = Punch({})
    close = person((580, 260, 700, 719))
    result = safe(skill.step(obs(0, [close])))
    assert result.pad.buttons == ("circle",)


def test_established_npc_can_grow_into_lower_foreground():
    skill = Punch({})
    safe(skill.step(obs(0, [person((520, 280, 760, 670))])))
    result = safe(skill.step(obs(0.04, [person((500, 260, 780, 719))])))
    assert result.pad.buttons == ("circle",)


def test_player_leak_cannot_replace_missing_side_target():
    skill = Punch({})
    safe(skill.step(obs(0, [person((760, 220, 900, 430))])))
    leak = person((400, 280, 760, 719))
    assert safe(skill.step(obs(0.1, [leak]))).pad == NEUTRAL_PAD
    terminal(skill, safe(skill.step(obs(1.1, [leak]))), "failed")


@pytest.mark.parametrize("stamp", [None, -1, 2, float("nan"), float("inf")])
def test_missing_stale_future_detection_releases_and_fails(stamp):
    skill = Punch({})
    safe(skill.step(obs(0)))
    result = safe(skill.step(obs(0.05, objects_time=stamp)))
    assert result.pad == NEUTRAL_PAD and result.status == "running"
    terminal(skill, safe(skill.step(obs(1.1, objects_time=stamp))), "failed")


def test_out_of_order_detection_releases_then_recovers():
    skill = Punch({})
    safe(skill.step(obs(1)))
    assert safe(skill.step(obs(1.1, objects_time=0.9))).pad == NEUTRAL_PAD
    result = safe(skill.step(obs(1.2)))
    assert result.status == "running"
    assert result.pad.l2 == 1


@pytest.mark.parametrize("hazard", ["corrupt", "tilted", "pause", "dead", "menu"])
def test_hazards_release_mid_pulse_and_latch(hazard):
    skill = Punch({})
    safe(skill.step(obs(0)))
    observation = obs(0.03)
    if hazard in {"corrupt", "tilted"}:
        observation = replace(
            observation,
            reading=replace(
                observation.reading,
                corrupt=hazard == "corrupt",
                minimap="tilted" if hazard == "tilted" else "flat",
            ),
        )
    else:
        observation = replace(observation, hud=Hud(screen=hazard))
    # Let go at once, and failed only when it lasts: the minimap reader calls a clean
    # picture damaged for a tick or two about once a second.
    result = safe(skill.step(observation))
    assert result.status == "running" and result.pad == NEUTRAL_PAD
    assert safe(skill.step(replace(observation, time=0.5, objects_time=0.5))).pad == NEUTRAL_PAD
    terminal(skill, safe(skill.step(replace(observation, time=1.04, objects_time=1.04))), "failed")


def test_a_damaged_tick_now_and_then_does_not_end_the_skill():
    skill = Punch({"hits": 2})
    pulses = 0
    held = False
    for tick in range(120):
        now = tick / 30
        observation = obs(now)
        if tick % 20 == 7:
            observation = replace(observation, reading=replace(observation.reading, corrupt=True))
        result = safe(skill.step(observation))
        if tick % 20 == 7:
            assert result.pad == NEUTRAL_PAD
        pressed = "circle" in result.pad.buttons
        pulses += pressed and not held
        held = pressed
        if result.status != "running":
            break
    assert result.status == "done" and pulses == 2


def test_stop_releases_mid_pulse():
    skill = Punch({})
    safe(skill.step(obs(0)))
    terminal(skill, safe(skill.stop("cancelled by head")), "failed")


def test_health_debounce_and_single_low_reading():
    skill = Punch({"hits": 6})
    low = Hud(health=0.29)
    safe(skill.step(obs(0, hud=low)))
    assert safe(skill.step(obs(0.1))).status == "running"
    assert safe(skill.step(obs(0.6, hud=low))).status == "running"
    assert safe(skill.step(obs(1.09, hud=low))).status == "running"
    terminal(skill, safe(skill.step(obs(1.11, hud=low))), "failed")
    assert "health" in skill.finished.reason


@pytest.mark.parametrize("health", [0.3, 0.8, None])
def test_healthy_or_unknown_health_does_not_fail(health):
    skill = Punch({"hits": 6})
    safe(skill.step(obs(0, hud=Hud(health=health))))
    assert safe(skill.step(obs(0.6, hud=Hud(health=health)))).status == "running"


def test_target_loss_does_not_switch_to_different_person():
    skill = Punch({})
    safe(skill.step(obs(0)))
    other = person((950, 200, 1100, 460))
    assert safe(skill.step(obs(0.1, [other]))).pad == NEUTRAL_PAD
    terminal(skill, safe(skill.step(obs(1.01, [other]))), "failed")
    assert "lost" in skill.finished.reason


def test_time_limit_no_person_and_invalid_time_are_neutral():
    skill = Punch({"duration": 0.1})
    safe(skill.step(obs(0)))
    terminal(skill, safe(skill.step(obs(0.1))), "failed")
    skill = Punch({})
    safe(skill.step(obs(0, [])))
    terminal(skill, safe(skill.step(obs(3.01, []))), "failed")
    skill = Punch({})
    safe(skill.step(obs(2)))
    terminal(skill, safe(skill.step(obs(1))), "failed")


@pytest.mark.parametrize(
    "item",
    [
        Detection("car", (560, 190, 720, 460), 0.9),
        person(confidence=0.1),
        person((-1, 190, 720, 460)),
        person((560, 190, 1300, 460)),
        person((560, 460, 720, 190)),
        person((560, 190, float("nan"), 460)),
        person((0.4, 0.2, 0.6, 0.8)),
    ],
)
def test_unusable_boxes_never_attack(item):
    result = safe(Punch({}).step(obs(0, [item])))
    assert not result.pad.buttons and result.pad.l2 == 0


@pytest.mark.parametrize(
    "args",
    [
        None,
        [],
        {"target": 1},
        {"duration": True},
        {"duration": "2"},
        {"duration": float("nan")},
        {"duration": float("inf")},
        {"hits": False},
        {"hits": "3"},
        {"hits": 1.5},
        {"hits": float("inf")},
    ],
)
def test_invalid_arguments(args):
    with pytest.raises(ValueError):
        Punch(args)


def test_defaults_clamping_and_exposed_limit():
    assert Punch({}).limit == 15
    assert Punch({}).hits == 3
    assert Punch({"duration": 100, "hits": 10}).limit == 20
    assert Punch({"duration": 100, "hits": 10}).hits == 6
    assert Punch({"duration": -2, "hits": -1}).limit == 0.1
    assert Punch({"duration": -2, "hits": -1}).hits == 1
    assert Punch({"duration": 10**1000, "hits": 10**1000}).limit == 20


def test_a_person_in_reach_but_off_to_the_side_is_turned_to_first():
    skill = Punch({})
    beside = person((880, 150, 1040, 660))
    for tick in range(6):
        result = safe(skill.step(obs(tick / 30, [beside])))
        assert result.pad.l2 == 0 and not result.pad.buttons
        assert result.pad.right[0] > 0 and result.pad.left == (0, 0)


def test_a_vehicle_is_not_a_person():
    skill = Punch({})
    car = Detection("car", (560, 200, 720, 660), 0.9)
    for tick in range(100):
        result = safe(skill.step(obs(tick / 30, [car])))
        assert result.pad == NEUTRAL_PAD
        if result.status != "running":
            break
    assert result.status == "failed" and "no person" in result.reason


def test_punch_takes_accepted_mode_over_opposite_map():
    def with_mode(minimap, mode):
        value = obs(0)
        return replace(value, reading=replace(value.reading, minimap=minimap), mode=mode)

    assert Punch({}).step(with_mode("tilted", "foot")).pad != NEUTRAL_PAD
    assert Punch({}).step(with_mode("flat", "vehicle")).pad == NEUTRAL_PAD
    result = Punch({}).step(with_mode("flat", "none"))
    assert result.status == "running" and result.pad == NEUTRAL_PAD


def test_reach_is_judged_against_the_figures_own_size():
    # The boxes of session 20261112-215851: the figure 0.28 of the frame high in the far view, the
    # man 0.25 at contact and 0.14 five steps away. Neither comes near the fixed 0.62.
    own = Detection("person", (563, 317, 640, 518), 0.9)
    near, far = person((640, 302, 704, 482)), person((704, 281, 768, 382))
    walking = Punch({}).step(obs(0, [far], figure=own))
    assert walking.pad.left[1] < 0 and not walking.pad.buttons and walking.pad.l2 == 0
    punching = safe(Punch({}).step(obs(0, [near], figure=own)))
    assert punching.pad.l2 == 1 and punching.pad.buttons == ("circle",)
    # Without the figure's own box the fixed share stays the rule.
    assert not Punch({}).step(obs(0, [near])).pad.buttons


def test_the_figures_size_is_kept_while_the_detector_misses_it():
    own = Detection("person", (563, 317, 640, 518), 0.9)
    skill = Punch({})
    near = person((640, 302, 704, 482))
    assert skill.step(obs(0, [near], figure=own)).pad.buttons == ("circle",)
    assert safe(skill.step(obs(0.05, [near]))).pad.l2 == 1
