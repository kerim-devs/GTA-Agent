"""Game bindings, retained skill profiles and outbound controller safety."""

from dataclasses import asdict, replace
from itertools import pairwise

import numpy as np
import pytest

from pilot import profile
from pilot.combat import Fight, Melee
from pilot.contract import NEUTRAL_PAD, Blip, Detection, Hud, Observation, Pad, Reading
from pilot.flow import Flow
from pilot.head import SkillCall
from pilot.loop import ControllerRuntime, log_row
from pilot.punch import Punch
from pilot.skills import Press, SkillRunner, Walk, WalkTo
from pilot.vehicle_entry import EnterVehicle
from pilot.waypoint import MapPicture, SetWaypoint


@pytest.fixture(autouse=True)
def restore_profile():
    previous = profile.active().name
    profile.use("gta5")
    yield
    profile.use(previous)


@pytest.mark.parametrize("name,sprint,held", [("gta5", "cross", False), ("gta6", "l3", True)])
def test_action_bindings(name, sprint, held):
    game = profile.use(name)
    assert (game.sprint, game.sprint_held) == (sprint, held)
    assert (game.enter_vehicle, game.melee, game.cover) == ("triangle", "circle", "r1")
    assert (game.pause, game.confirm, game.back, game.retry) == ("options", "cross", "circle", "cross")
    assert (game.left_dead_zone, game.right_dead_zone) == (0, 0.3)


def test_unknown_profile_keeps_selection():
    before = profile.active()
    with pytest.raises(ValueError, match="Unknown game profile"):
        profile.use("unknown")
    assert profile.active() is before


@pytest.mark.parametrize("factory", [Walk, WalkTo, Fight, Melee, Punch, EnterVehicle, SetWaypoint, Flow])
def test_existing_skill_retains_its_profile(factory):
    args = {"color": "yellow"} if factory is WalkTo else {}
    first = factory() if factory is Flow else factory(args)
    profile.use("gta6")
    second = factory() if factory is Flow else factory(args)
    assert first.profile is profile.GTA5
    assert second.profile is profile.GTA6


def observation(t):
    reading = Reading("flat", "none", None, None, None, False, 1, blips=(Blip("yellow", 0, 30),))
    return Observation(reading, True, t)


@pytest.mark.parametrize("factory,args", [(Walk, {"y": -1}), (WalkTo, {"color": "yellow"})])
@pytest.mark.parametrize("name", ["gta5", "gta6"])
def test_sprint_taps_or_holds_and_releases(factory, args, name):
    profile.use(name)
    skill = factory({**args, "sprint": True, "duration": 1})
    profile.use("gta6" if name == "gta5" else "gta5")
    pads = [skill.step(observation(t)).pad for t in (0, 0.13, 0.26, 0.39)]
    expected = [("cross",), (), ("cross",), ()] if name == "gta5" else [("l3",)] * 4
    assert [pad.buttons for pad in pads] == expected
    bridge = Bridge()
    runtime = ControllerRuntime(bridge, clock=lambda: 0)
    runtime.tick(skill.step(observation(1)).pad, fresh=True, received=0)
    assert bridge.calls[-1] == NEUTRAL_PAD
    runtime.tick(skill.stop().pad, fresh=True, received=0)
    assert bridge.calls[-1] == NEUTRAL_PAD


def test_raw_press_and_plan_stop_remain_neutral():
    profile.use("gta6")
    assert Press({"button": "cross"}).step(observation(0)).pad.buttons == ("cross",)
    runner = SkillRunner()
    assert runner.replace((SkillCall("walk", {"sprint": True, "y": -1}),)) == NEUTRAL_PAD
    assert runner.tick(observation(0)).pad == NEUTRAL_PAD
    assert runner.tick(observation(0.03)).pad.buttons == ("l3",)
    bridge = Bridge()
    runtime = ControllerRuntime(bridge, clock=lambda: 0)
    runtime.tick(runner.stop(), fresh=True, received=0)
    assert bridge.calls[-1] == NEUTRAL_PAD
    runtime.tick(runner.tick(observation(0.06)).pad, fresh=True, received=0)
    assert bridge.calls[-1] == NEUTRAL_PAD


@pytest.mark.parametrize("name", ["gta5", "gta6"])
def test_actions_emit_profile_buttons(name):
    game = profile.use(name)
    reading = Reading("flat", "none", None, None, None, False, 1, blips=(Blip("red", 0, 8),))
    obs = Observation(reading, False, 0, hud=Hud(health=0.2, wanted=0, screen="game"))
    low_health = Fight({"cover": "yes"}).step(obs)
    assert low_health.reason == "health-still-low" and low_health.pad == NEUTRAL_PAD
    fight = Fight({"cover": "yes"})
    for tick in range(63):
        hud = Hud(health=0.9 if tick < 60 else 0.7, armour=0.0, special=1.0, wanted=0, screen="game")
        covered = fight.step(replace(obs, time=tick / 30, hud=hud))
    assert covered.pad.buttons == (game.cover,)
    assert covered.pad.l2 == covered.pad.r2 == 0
    melee = Melee({})
    healthy = replace(obs, hud=Hud(health=1))
    for tick in range(10):
        result = melee.step(replace(healthy, time=tick / 30))
    assert result.pad.buttons == (game.melee,)
    person = Detection("person", (560, 200, 720, 660), 0.9)
    assert Punch({}).step(replace(healthy, objects=(person,), objects_time=0)).pad.buttons == (game.melee,)
    car = Detection("car", (384, 324, 896, 648), 0.9)
    vehicle = EnterVehicle({})
    nearby = replace(healthy, objects=(car,), objects_time=0, figure=person)
    vehicle.step(nearby)
    assert vehicle.step(replace(nearby, time=0.04, objects_time=0.04)).pad.buttons == (game.enter_vehicle,)
    frame = np.full((720, 1280, 3), 20, np.uint8)
    assert SetWaypoint({}).step(replace(healthy, frame=frame)).pad.buttons == (game.pause,)
    waypoint = SetWaypoint({})
    waypoint.phase = "enter"
    waypoint._picture = lambda _: MapPicture("overview")
    paused = replace(healthy, frame=frame, hud=Hud(screen="pause"))
    assert waypoint.step(paused).pad.buttons == (game.confirm,)
    for screen, text, button in (("pause", None, game.back), ("failed", "Erneut versuchen", game.retry)):
        flow = Flow()
        menu = replace(healthy, hud=Hud(screen=screen))
        flow.tick(menu, text)
        assert flow.tick(replace(menu, time=0.1), text).pad.buttons == (button,)


class Bridge:
    def __init__(self, status=200):
        self.calls = []
        self.status = status

    def pad(self, command):
        self.calls.append(command)
        return self.status


def test_outbound_shaping_and_log_keep_request():
    bridge = Bridge()
    runtime = ControllerRuntime(bridge, clock=lambda: 0)
    request = Pad(buttons=("circle",), left=(0.01, -0.65), right=(0.1, -0.65), l2=0.2, r2=1)
    sent, status = runtime.tick(request, fresh=True, received=0)
    actual = bridge.calls[-1]
    assert sent and status == 200
    assert actual.right == pytest.approx((0.37, -0.755))
    assert actual.left == request.left
    # The pedals are lifted over their dead zone of 0.35 as the right stick is over its 0.3.
    assert (actual.buttons, actual.l2, actual.r2) == (request.buttons, pytest.approx(0.48), 1)
    assert request.right == (0.1, -0.65)
    row = log_row(
        0,
        1,
        0,
        0,
        None,
        None,
        request,
        sent,
        status,
        requested_pad=runtime.requested_pad,
        sent_pad=runtime.sent_pad,
    )
    assert row["requested_pad"] == asdict(request)
    assert row["sent_pad"] == asdict(actual)


def test_dead_zone_is_monotonic_symmetric_and_bounded():
    values = [i / 1000 for i in range(1001)]
    shaped = [profile.GTA5.shape(Pad(right=(v, -v))).right for v in values]
    assert all(x == -y for x, y in shaped)
    assert all(a[0] <= b[0] for a, b in pairwise(shaped))
    assert all(x == 0 or 0.3 <= x <= 1 for x, _ in shaped)
    assert shaped[100][0] >= 0.3
    assert shaped[300][0] < shaped[650][0]
    assert shaped[-1] == (1, -1)
    assert profile.GTA5.shape(Pad(right=(0.0199, -0.0199))) == NEUTRAL_PAD
    assert profile.GTA5.shape(NEUTRAL_PAD) == NEUTRAL_PAD
    assert profile.GTA5.shape(Pad(right=(1.4, -1.4))).right == (1, -1)


def test_a_value_measured_at_the_console_leaves_as_it_was_measured():
    # Just above the zone's edge there is a gap as wide as the noise floor's share: 0.3 to 0.314.
    for measured in (0.5, -0.5, 0.35, 1.0, -1.0):
        request = profile.GTA5.right_for(measured)
        assert profile.GTA5.shape(Pad(right=(request, 0.0))).right == pytest.approx((measured, 0.0))


def test_the_calibration_measures_the_console_and_sends_what_it_asks():
    bridge = Bridge()
    runtime = ControllerRuntime(bridge, clock=lambda: 0, raw=True)
    runtime.tick(Pad(right=(0.1, -0.2)), fresh=True, received=0)
    assert bridge.calls[-1].right == (0.1, -0.2)
    assert runtime.sent_pad == runtime.requested_pad


@pytest.mark.parametrize("shadow", [False, True])
def test_neutral_stale_and_release(shadow):
    bridge = Bridge()
    runtime = ControllerRuntime(bridge, shadow=shadow, clock=lambda: 0)
    runtime.tick(NEUTRAL_PAD, fresh=True, received=0)
    assert runtime.sent_pad is None if shadow else runtime.sent_pad == NEUTRAL_PAD
    runtime.tick(Pad(right=(0.1, 0)), fresh=False, received=0.31)
    assert runtime.sent_pad is None
    runtime.release()
    assert runtime.sent_pad is None
    assert bridge.calls == ([] if shadow else [NEUTRAL_PAD, None, None])


def test_conflict_does_not_retain_shaped_input():
    bridge = Bridge(status=409)
    runtime = ControllerRuntime(bridge, clock=lambda: 0)
    request = Pad(right=(0.1, 0))
    assert runtime.tick(request, fresh=True, received=0) == (False, 409)
    assert runtime.sent_pad == bridge.calls[-1]
    runtime.tick(request, fresh=True, received=0.5)
    assert runtime.sent_pad is None
    bridge.status = 200
    runtime.tick(request, fresh=True, received=1)
    assert bridge.calls[-1] is None
