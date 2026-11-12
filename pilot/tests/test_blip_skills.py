"""Closed-loop targets must remain bounded and release complete pad state."""

import importlib.util
from pathlib import Path

import pytest

from pilot.contract import NEUTRAL_PAD, Blip, Reading
from pilot.head import SkillCall, parse_response, response_schema
from pilot.skills import Observation, Skill, SkillRunner

DEFAULT_DOTS = (Blip("blue", 20, 30),)


def observation(t=0.0, dots=DEFAULT_DOTS, *, moving=True, minimap="flat", corrupt=False):
    return Observation(Reading(minimap, "none", None, None, 0, corrupt, 1, blips=dots), moving, t)


@pytest.mark.parametrize("name,limit", [("walk_to", 10), ("face", 5)])
def test_blip_limits_and_release(name, limit):
    skill = Skill(SkillCall(name, {"color": "blue", "duration": 999}))
    assert skill.step(observation()).status == "running"
    final = skill.step(observation(limit))
    assert final.status == "failed" and final.reason == "time-limit"
    assert final.pad == NEUTRAL_PAD
    assert skill.step(observation(limit + 1)) == final


@pytest.mark.parametrize("name", ["walk_to", "face"])
def test_missing_and_corrupt_targets_release_immediately(name):
    for args in ({"dots": ()}, {"corrupt": True}, {"minimap": "tilted"}):
        skill = Skill(SkillCall(name, {"color": "blue"}))
        assert skill.step(observation()).pad != NEUTRAL_PAD
        assert skill.step(observation(0.1, **args)).pad == NEUTRAL_PAD
        final = skill.step(observation(2.11, **args))
        assert final.status == "failed" and final.reason == "blip-gone"


@pytest.mark.parametrize("name", ["walk_to", "face"])
def test_replacement_releases_both_sticks(name):
    runner = SkillRunner()
    assert runner.replace((SkillCall(name, {"color": "blue"}),)) == NEUTRAL_PAD
    runner.tick(observation())
    assert runner.tick(observation(0.1)).pad != NEUTRAL_PAD
    assert runner.replace((SkillCall("wait", {}),)) == NEUTRAL_PAD
    assert runner.tick(observation(0.2)).pad == NEUTRAL_PAD
    assert runner.stop() == NEUTRAL_PAD


def test_nearest_requested_color_and_arrival():
    dots = (Blip("red", 0, 0), Blip("blue", 40, 0), Blip("blue", -8, 0))
    skill = Skill(SkillCall("walk_to", {"color": "blue"}))
    pad = skill.step(observation(dots=dots)).pad
    assert pad.left[0] < 0 and pad.left[1] == 0 and not pad.buttons
    arrived = skill.step(observation(0.1, (Blip("blue", 1, 2),)))
    assert arrived.status == "done" and arrived.reason == "arrived"
    assert arrived.pad == NEUTRAL_PAD


def test_face_requires_settling_and_releases_in_tolerance():
    skill = Skill(SkillCall("face", {"color": "blue"}))
    assert skill.step(observation()).pad.right[0] > 0
    first = skill.step(observation(0.1, (Blip("blue", 0, 40),)))
    assert first.status == "running" and first.pad == NEUTRAL_PAD
    assert skill.step(observation(0.31, (Blip("blue", 0, 40),))).reason == "aligned"


def test_a_blip_straight_behind_keeps_one_turn_direction():
    skill = Skill(SkillCall("face", {"color": "blue"}))
    first = skill.step(observation(dots=(Blip("blue", 2, -40),))).pad.right[0]
    second = skill.step(observation(0.03, (Blip("blue", -2, -40),))).pad.right[0]
    assert first > 0 and second > 0


def test_sprint_only_when_asked_and_far():
    def buttons(args, dot):
        skill = Skill(SkillCall("walk_to", {"color": "blue", **args}))
        return {b for tick in range(30) for b in skill.step(observation(tick / 30, (dot,))).pad.buttons}

    assert buttons({}, Blip("blue", 0, 50)) == set()
    assert buttons({"sprint": True}, Blip("blue", 0, 50)) == {"cross"}
    assert buttons({"sprint": True}, Blip("blue", 0, 10)) == set()


def test_blocked_walk_alternates_then_fails():
    skill = Skill(SkillCall("walk_to", {"color": "blue", "sprint": True}))
    side = []
    for tick in range(301):
        result = skill.step(observation(tick / 30, (Blip("blue", 0, 50),), moving=False))
        x = result.pad.left[0]
        if abs(x) > 0.5 and (not side or side[-1] != (x > 0)):
            side.append(x > 0)
            assert not result.pad.buttons
        if result.status != "running":
            break
    # The ways round go right, left, right, left (foot.FootGuard.ESCAPES), then walk_to gives up.
    assert side == [True, False, True, False]
    assert result.reason == "blocked" and result.pad == NEUTRAL_PAD


@pytest.mark.parametrize(
    "args",
    [
        {},
        {"color": "purple"},
        {"color": []},
        {"color": "blue", "duration": float("nan")},
        {"color": "blue", "sprint": 1},
    ],
)
def test_bad_target_arguments_are_rejected_atomically(args):
    with pytest.raises(ValueError):
        parse_response({"plan": [{"name": "walk_to", "args": args}], "sentence": "Wait."})


def test_head_schema_exposes_only_observed_colors():
    variants = response_schema()["properties"]["plan"]["items"]["anyOf"]
    for name in ("walk_to", "face"):
        variant = next(v for v in variants if v["properties"]["name"]["enum"] == [name])
        assert variant["properties"]["args"]["properties"]["color"]["enum"] == ["blue", "red", "yellow"]


def test_delayed_noisy_simulation_arrival_wall_and_turning():
    path = Path(__file__).resolve().parents[1] / "tools/sim_blip_skills.py"
    spec = importlib.util.spec_from_file_location("blip_sim", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for seed in range(5):
        for wall in ("none", "corner", "sealed"):
            result = module.simulate("walk_to", seed, wall=wall)
            assert result["seconds"] <= 10 and result["status"] != "running"
            if wall == "none":
                assert result["status"] == "done" and result["distance"] <= 6
            if wall == "sealed":
                assert result["status"] == "failed"
        for angle in (-179, -90, 20, 179):
            result = module.simulate("face", seed, angle=angle)
            assert result["status"] == "done" and result["angle_error"] <= 11
            assert result["turn_reversals"] == 0


@pytest.mark.parametrize("name", ["walk_to", "face"])
def test_blip_skills_take_accepted_mode_over_opposite_map(name):
    from dataclasses import replace

    call = SkillCall(name, {"color": "blue"})
    foot = replace(observation(minimap="tilted"), mode="foot")
    vehicle = replace(observation(minimap="flat"), mode="vehicle")
    absent = replace(observation(minimap="flat"), mode="none")
    assert Skill(call).step(foot).pad != NEUTRAL_PAD
    assert Skill(call).step(vehicle).pad == NEUTRAL_PAD
    result = Skill(call).step(absent)
    assert result.pad == NEUTRAL_PAD and result.status == "running"
