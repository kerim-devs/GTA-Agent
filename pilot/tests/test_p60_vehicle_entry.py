"""Recorded death/seat contradiction, without a console or judge server."""

from dataclasses import replace

import pytest

from pilot.contract import Answer, Judgment, Observation, Pad, Reading
from pilot.vehicle_entry import EnterVehicle


def observation(t, minimap="tilted", mode="vehicle", *, raw="vehicle", banner=False):
    judgment = Judgment(
        t,
        {"mode": Answer(raw, 1.0), "banner": Answer(banner, 1.0)},
        {},
        0.25,
        "stored",
    )
    return Observation(
        Reading(minimap, "none", None, None, None, False, 1.0),
        None,
        t,
        mode=mode,
        judgment=judgment,
    )


def test_death_with_accepted_vehicle_mode_never_proves_a_seat():
    # 143128: accepted vehicle mode at ~22.524; clean absent map since 21.925.
    skill = EnterVehicle({})
    skill.attempts = 1
    for t in (22.524, 22.8, 23.0, 23.536, 24.0):
        result = skill.step(observation(t, minimap="none"))
        assert result.status == "running"
        assert result.pad == Pad()
        assert skill.confirmed_since is None
    assert "no gameplay minimap" in result.reason


@pytest.mark.parametrize("interruption", ["none", "banner", "raw_foot", "raw_none"])
def test_non_play_or_contradiction_breaks_continuous_seat_proof(interruption):
    skill = EnterVehicle({})
    skill.attempts = 1
    skill.step(observation(0))
    if interruption == "none":
        interrupted = observation(0.8, minimap="none", mode="none", raw="none")
    elif interruption == "banner":
        interrupted = observation(0.8, banner=True)
    else:
        interrupted = observation(0.8, raw=interruption.removeprefix("raw_"))
    assert skill.step(interrupted).pad == Pad()
    assert skill.confirmed_since is None
    assert skill.step(observation(1.1)).status == "running"
    assert skill.step(observation(1.9)).status == "running"
    result = skill.step(observation(2.2))
    assert result.status == "done"
    assert result.pad == Pad()


def test_old_banner_is_not_a_new_death_and_missing_judge_keeps_map_proof():
    skill = EnterVehicle({})
    skill.attempts = 1
    old = observation(0, banner=True).judgment
    assert skill.step(replace(observation(2), judgment=old)).status == "running"
    assert skill.step(replace(observation(3.1), judgment=None)).status == "done"


def test_absent_map_after_press_releases_button_even_with_wrong_vehicle_judge():
    skill = EnterVehicle({})
    skill.phase = "wait"
    skill.phase_since = 0
    skill.attempts = 1
    result = skill.step(observation(0.04, minimap="none"))
    assert result.pad == Pad()
    assert result.status == "running"
