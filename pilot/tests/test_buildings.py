"""Doors in a scripted room, using the same steering guard as a real walk."""

import math
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
import pytest

from pilot import ahead, indoors
from pilot.contract import NEUTRAL_PAD, Blip, Observation, Reading
from pilot.leave import LeaveBuilding
from pilot.walkto import WalkTo
from pilot.waymark import find_waypoint
from pilot.wayround import WayRound


class Room:
    def __init__(self, *, inside=False, door=True):
        self.x, self.y = (4.0, 1.0) if inside else (2.0, -0.3)
        self.camera = self.facing = 0.0
        self.moved = False
        self.door = door

    @property
    def inside(self):
        return 0 < self.y < 6 and 0 < self.x < 6

    def observation(self, now):
        arrow = (self.facing - self.camera + 180) % 360 - 180
        reading = Reading("flat", "none", None, None, arrow, False, 1.0, blips=(Blip("purple", 0, 2, False),))
        return Observation(reading, self.moved, now, mode="foot")

    def apply(self, pad, dt=0.1):
        self.camera += pad.right[0] * 120 * dt
        x, y = pad.left[0], -pad.left[1]
        angle = math.radians(self.camera)
        dx, dy = (
            (x * math.cos(angle) + y * math.sin(angle)) * dt * 2,
            (-x * math.sin(angle) + y * math.cos(angle)) * dt * 2,
        )
        old = self.x, self.y
        nx, ny = self.x + dx, self.y + dy
        # Slide along a solid front; its only opening is x=3..5.
        if self.y * ny <= 0 and 0 <= nx <= 6 and not (self.door and 3 <= nx <= 5):
            ny = self.y
        if self.inside:
            if not 0 < nx < 6:
                nx = self.x
            if ny >= 6:
                ny = self.y
        self.x, self.y = nx, ny
        self.moved = math.hypot(self.x - old[0], self.y - old[1]) > 0.01
        if self.moved:
            self.facing = math.degrees(math.atan2(dx, dy))


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    indoors.forget()
    monkeypatch.setattr(ahead, "active", lambda: None)
    monkeypatch.setattr(ahead, "place", lambda: None)
    yield
    indoors.forget()


def sensor(monkeypatch, room):
    # The world supplies an exact sensor. Qualification of the real image reader is tested separately.
    monkeypatch.setattr(indoors, "INDEPENDENT", True)
    monkeypatch.setattr(indoors, "read", lambda frame: room.inside)


def play(skill, room, until=60, *, start=0):
    results = []
    guard = None
    for index in range(round(start * 10), round(until * 10) + 1):
        if skill.guard is not guard:
            guard = skill.guard
            guard._evidence = lambda observation: "going" if room.moved else "still"
        result = skill.step(room.observation(index / 10))
        results.append((index / 10, result))
        room.apply(result.pad)
        if result.status != "running":
            break
    return results


def test_wall_finds_door_then_remembered_exit_clears_it(monkeypatch):
    room = Room()
    sensor(monkeypatch, room)
    enter = WalkTo({"enter": True, "roads": False, "sprint": False})
    results = play(enter, room, 45)
    assert results[-1][1].status == "done"
    assert "entered" in results[-1][1].reason
    assert room.inside and indoors.entrance() is not None
    assert results[-1][1].pad == NEUTRAL_PAD
    leave = LeaveBuilding({})
    start = results[-1][0] + 0.1
    outputs = play(leave, room, start + 20, start=start)
    assert "remembered" in leave.guard.views
    assert outputs[-1][1].reason == "outdoors"
    assert outputs[-1][1].pad == NEUTRAL_PAD
    assert room.y < -1.0
    assert outputs[-1][0] - leave.clear >= 1.5


def test_no_door_is_an_arrival_after_forty_seconds_and_a_step_off_wall(monkeypatch):
    room = Room(door=False)
    sensor(monkeypatch, room)
    skill = WalkTo({"enter": True, "roads": False, "sprint": False})
    results = play(skill, room, 45)
    assert results[-1][1].status == "done"
    assert "arrived; no door found" in results[-1][1].reason
    assert results[-1][0] - skill.enter_since == pytest.approx(40, abs=0.1)
    assert any(result.reason == "standing off the wall" for _, result in results)
    assert results[-1][1].pad == NEUTRAL_PAD


def test_exit_without_memory_or_model_uses_wall_round(monkeypatch):
    room = Room(inside=True)
    sensor(monkeypatch, room)
    skill = LeaveBuilding({})
    results = play(skill, room, 1.5)
    assert "wall" in skill.guard.views
    assert any(result.pad.right != (0, 0) for _, result in results)
    assert skill.guard.entered is False


def test_closed_room_fails_with_reason_and_released_pad(monkeypatch):
    room = Room(inside=True, door=False)
    sensor(monkeypatch, room)
    skill = LeaveBuilding({"duration": 120})
    skill.guard._evidence = lambda observation: "still"
    results = []
    for i in range(1201):
        result = skill.step(room.observation(i / 10))
        results.append(result)
        if result.status != "running":
            break
    assert results[-1].reason == "no-way-out"
    assert results[-1].status == "failed" and results[-1].pad == NEUTRAL_PAD


def test_outdoors_requires_two_separate_readings_and_unknown_breaks_them(monkeypatch):
    room = Room()
    sensor(monkeypatch, room)
    skill = LeaveBuilding({})
    assert skill.step(room.observation(0)).status == "running"
    bad = room.observation(0.2)
    bad = replace(bad, reading=replace(bad.reading, minimap="none"))
    assert skill.step(bad).pad == NEUTRAL_PAD
    assert skill.step(room.observation(0.4)).status == "running"
    assert skill.step(room.observation(0.6)).status == "running"
    assert skill.step(room.observation(0.8)).reason == "outdoors"


@pytest.mark.parametrize("kind", ["none", "corrupt", "low", "duplicate", "gap"])
def test_missing_or_bad_tick_releases_all_controls_without_deciding(monkeypatch, kind):
    room = Room(inside=True)
    sensor(monkeypatch, room)
    indoors.remember(0, (0, -3))
    skill = LeaveBuilding({})
    play(skill, room, 0.8)
    obs = room.observation(0.9)
    if kind == "none":
        obs = replace(obs, reading=replace(obs.reading, minimap="none"))
    elif kind == "corrupt":
        obs = replace(obs, mode=None, reading=replace(obs.reading, corrupt=True))
    elif kind == "low":
        obs = replace(obs, mode=None, reading=replace(obs.reading, confidence=0.1))
    elif kind == "duplicate":
        obs = replace(obs, time=0.8)
    else:
        obs = replace(obs, time=3)
    result = skill.step(obs)
    assert result.status == "running" and result.pad == NEUTRAL_PAD


@pytest.mark.parametrize("kind", ["tilted", "corrupt", "low"])
def test_a_misread_map_does_not_stop_the_way_out_while_the_judge_sees_the_figure_on_foot(monkeypatch, kind):
    # 13 November, 15:49: the floor plan on the radar was read as tilted for fourteen seconds, and
    # the figure stood in the bedroom for all of them.
    room = Room(inside=True)
    sensor(monkeypatch, room)
    indoors.remember(0, (0, -3))
    skill = LeaveBuilding({})
    play(skill, room, 0.8)
    pads = []
    for tick in range(9, 40):
        obs = room.observation(tick / 10)
        change = {"tilted": {"minimap": "tilted"}, "corrupt": {"corrupt": True}, "low": {"confidence": 0.1}}
        result = skill.step(replace(obs, reading=replace(obs.reading, **change[kind])))
        pads.append(result.pad)
        room.apply(result.pad)
    assert any(pad != NEUTRAL_PAD for pad in pads)


def test_the_standing_sense_ends_the_way_out(monkeypatch):
    # 13 November, 16:02: out on the landing the skill's own question had not said so yet, and the
    # figure went on along the wall and back into the apartment.
    room = Room(inside=True)
    sensor(monkeypatch, room)
    indoors.remember(0, (0, -3))
    skill = LeaveBuilding({})
    play(skill, room, 0.8)
    reasons = []
    for tick in range(9, 40):
        result = skill.step(replace(room.observation(tick / 10), place="landing"))
        reasons.append(result.reason)
        room.apply(result.pad)
        if result.status != "running":
            break
    assert (result.status, result.reason) == ("done", "outdoors")
    assert "clearing doorway" in reasons


def test_enter_never_coasts_into_a_missing_map(monkeypatch):
    room = Room()
    sensor(monkeypatch, room)
    skill = WalkTo({"enter": True, "roads": False})
    play(skill, room, 1)
    obs = room.observation(1.1)
    obs = replace(obs, reading=replace(obs.reading, minimap="none"))
    assert skill.step(obs).pad == NEUTRAL_PAD
    assert skill.finished is None


def test_time_limit_interruption_and_arguments_are_safe(monkeypatch):
    room = Room(inside=True)
    monkeypatch.setattr(indoors, "read", lambda frame: None)
    skill = LeaveBuilding({"duration": 5})
    results = play(skill, room, 6)
    assert results[-1][1].reason == "place-unread" and results[-1][1].pad == NEUTRAL_PAD
    assert LeaveBuilding({}).stop("replaced").pad == NEUTRAL_PAD
    for args in ({"duration": float("nan")}, {"duration": float("inf")}, {"duration": True}, {"x": 1}):
        with pytest.raises(ValueError):
            LeaveBuilding(args)
    with pytest.raises(ValueError):
        WalkTo({"enter": "yes"})


def test_unqualified_image_reader_cannot_trigger_room_or_outdoors():
    assert not indoors.INDEPENDENT
    assert indoors.resolve(True, None) is None
    assert indoors.resolve(False, None) is None
    assert indoors.resolve(True, False) is False
    assert indoors.resolve(False, True) is True
    assert indoors.read(None) is None
    assert indoors.read(np.zeros((720, 1280, 3), dtype=np.uint8)) is None


def test_remembered_world_heading_is_relative_to_current_camera_not_current_facing(monkeypatch):
    room = Room(inside=True)
    room.camera, room.facing = 110, 70
    sensor(monkeypatch, room)
    monkeypatch.setattr("pilot.leave.north_bearing", lambda crop: -room.camera)
    indoors.remember(30, (2, -4), "shop", at=0, absolute=True)
    skill = LeaveBuilding({})
    for i in range(5):
        frame = np.full((720, 1280, 3), 100 + i, dtype=np.uint8)
        skill.step(replace(room.observation(i / 10), frame=frame))
    assert skill.guard.views == ["remembered"]
    assert skill.guard.turn_from == -40
    # Entry world bearing30 -> outward210 -> picture100 with camera110.
    assert skill.guard.turn_by == 100 and skill.guard.turn_side == 1


def test_late_model_answer_is_not_two_fresh_outdoor_readings():
    class Slow:
        def ask(self, frame, capture, **kwargs):
            return True

        def answer(self, since):
            return ahead.View(indoors=0.0)

    place = indoors.Place(Slow())
    room = Room()
    assert place.sample(room.observation(0)) is None
    assert place.sample(room.observation(2.1)) is None
    assert place.sample(room.observation(2.5)) is None
    assert place.sample(room.observation(2.6)) is None


def test_exit_guard_discards_a_late_place_answer_before_counting_outdoors():
    class Model:
        def ask(self, frame, capture, **kwargs):
            return True

        def answer(self, since):
            return ahead.View(indoors=0.0)

    room = Room(inside=True)
    guard = WayRound(ahead=Model(), confirm_place=True)
    for time in (0.6, 1.8, 2.5, 2.6):
        guard._watch(room.observation(time))
    assert guard.outside is None
    for time in (3.3, 3.4):
        guard._watch(room.observation(time))
    assert guard.outside == 3.4


def test_enter_false_or_nonexact_preserves_arrival(monkeypatch):
    room = Room()
    sensor(monkeypatch, room)
    for args in ({"enter": False}, {"enter": True, "exact": False}):
        skill = WalkTo(args)
        result = play(skill, room, 2)[-1][1]
        assert result.status == "done" and "entered" not in result.reason


@pytest.mark.parametrize("session", ["20261113-022849", "20261113-005541", "20261113-010434"])
def test_recorded_barber_starts_back_away_then_go_along_front(session):
    crop = cv2.cvtColor(
        cv2.imread(str(Path(__file__).parents[2] / "lab/indoors" / f"{session}.png")), cv2.COLOR_BGR2RGB
    )
    marker = find_waypoint(crop)
    skill = WalkTo({})
    commands = []
    for i in range(20):
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame[530:700, 30:290] = crop
        frame[0, 0] = i
        reading = Reading("flat", "none", None, None, 0, False, 1.0, blips=(marker,))
        result = skill.step(Observation(reading, True, i / 10, frame=frame, mode="foot"))
        commands.append(result)
    moving = [r for r in commands if r.pad.left != (0, 0)]
    assert moving[0].pad.left[1] > 0.5
    assert moving[0].reason == "away from the building"
    assert any(r.reason == "along the front" for r in commands)
    assert all(not r.pad.buttons and not r.pad.l2 and not r.pad.r2 for r in commands)


def test_model_wall_at_start_is_confirmed_before_backing_away(monkeypatch):
    class Model:
        def ask(self, frame, capture, **kwargs):
            return True

        def answer(self, since):
            return ahead.View(open=0.01)

    monkeypatch.setattr(ahead, "active", lambda: Model())
    skill = WalkTo({"roads": False})
    room = Room()
    commands = []
    for i in range(10):
        frame = np.full((720, 1280, 3), 100, dtype=np.uint8)
        frame[0, 0] = i
        obs = room.observation(i / 10)
        obs = replace(obs, frame=frame, reading=replace(obs.reading, blips=(Blip("purple", 0, 60),)))
        result = skill.step(obs)
        commands.append(result)
    assert all(r.pad == NEUTRAL_PAD for r in commands[:4])
    assert next(r for r in commands if r.pad.left != (0, 0)).pad.left == (0, 1)


def test_a_missing_map_releases_departure_even_when_mode_still_says_foot(monkeypatch):
    monkeypatch.setattr("pilot.walkto.near_place", lambda crop: (0, 5))
    skill = WalkTo({})
    room = Room()
    skill.step(room.observation(0))
    assert skill.step(room.observation(0.2)).pad.left == (0, 1)
    obs = room.observation(0.3)
    obs = replace(obs, reading=replace(obs.reading, minimap="none"))
    assert skill.step(obs).pad == NEUTRAL_PAD


@pytest.mark.parametrize("status,reason", [("done", "outdoors"), ("failed", "place-unread")])
def test_p81_stop_preserves_the_final_verdict(status, reason):
    from pilot.contract import SkillResult

    skill = LeaveBuilding({})
    skill.finished = SkillResult(status=status, reason=reason)
    original = skill.finished
    assert skill.stop("replaced") is original
    assert skill.step(Room().observation(2)) is original


def test_p81_no_place_model_fails_on_first_valid_step(monkeypatch):
    monkeypatch.setattr(indoors, "INDEPENDENT", False)
    skill = LeaveBuilding({})
    invalid = replace(Room().observation(0), reading=None)
    assert skill.step(invalid).status == "running"
    result = skill.step(Room().observation(0.1))
    assert result.status == "failed" and result.reason == "place-unread"
    assert result.pad == NEUTRAL_PAD


@pytest.mark.parametrize("answers", ["absent", "ambiguous", "alternating"])
def test_p81_unconfirmed_place_model_fails_after_eight_valid_seconds(monkeypatch, answers):
    from types import SimpleNamespace

    class Model:
        count = 0

        def ask(self, *args, **kwargs):
            return True

        def answer(self, at):
            self.count += 1
            if answers == "absent":
                return None
            share = 0.7 if answers == "ambiguous" else (1.0 if self.count % 2 else 0.0)
            return SimpleNamespace(indoors=share, error=None)

    monkeypatch.setattr(indoors, "INDEPENDENT", False)
    monkeypatch.setattr(indoors, "read", lambda frame: None)
    monkeypatch.setattr(ahead, "place", Model)
    skill = LeaveBuilding({})
    trace = [skill.step(Room().observation(i / 10)) for i in range(81)]
    assert all(result.status == "running" and result.pad == NEUTRAL_PAD for result in trace[:-1])
    assert trace[-1].status == "failed" and trace[-1].reason == "place-unread"


def test_p81_invalid_frames_pause_but_do_not_erase_place_wait(monkeypatch):
    monkeypatch.setattr(indoors, "INDEPENDENT", False)
    skill = LeaveBuilding({})
    skill.place.model = object()
    monkeypatch.setattr(skill.place, "sample", lambda observation: None)
    room = Room()
    for i in range(41):
        assert skill.step(room.observation(i / 10)).status == "running"
    for i in range(41, 61):
        assert skill.step(replace(room.observation(i / 10), reading=None)).status == "running"
    for i in range(61, 101):
        assert skill.step(room.observation(i / 10)).status == "running"
    result = skill.step(room.observation(10.1))
    assert result.status == "failed" and result.reason == "place-unread"


@pytest.mark.parametrize(
    "absolute,age,used",
    [
        (False, 30, True),
        (False, 30.01, False),
        (True, 180, True),
        (True, 180.01, False),
        (False, -1, False),
        (True, -1, False),
        (False, None, False),
    ],
)
def test_p81_only_fresh_entrances_guide_the_exit(monkeypatch, absolute, age, used):
    from types import SimpleNamespace

    monkeypatch.setattr(indoors, "INDEPENDENT", True)
    monkeypatch.setattr("pilot.leave.north_bearing", lambda crop: 10)
    now = 200.0
    entry = SimpleNamespace(heading=30, at=None if age is None else now - age, absolute=absolute)
    monkeypatch.setattr(indoors, "entrance", lambda: entry)
    skill = LeaveBuilding({})
    monkeypatch.setattr(skill.place, "sample", lambda observation: True)
    headings, searches = [], []
    monkeypatch.setattr(skill.guard, "leave_heading", lambda observation, heading: headings.append(heading))
    monkeypatch.setattr(skill.guard, "leave", lambda observation: searches.append(observation.time))
    monkeypatch.setattr(
        skill.guard,
        "step",
        lambda *args: SimpleNamespace(failed=False, state="look", left=(0, 0), right=(0, 0), buttons=()),
    )
    frame = np.full((720, 1280, 3), 100, dtype=np.uint8)
    skill.step(replace(Room(inside=True).observation(now), frame=frame))
    assert bool(headings) == used
    if used:
        assert headings == [220 if absolute else 210]
    else:
        assert searches


def test_p81_walk_records_the_confirmed_entrance_time(monkeypatch):
    skill = WalkTo({"enter": True, "roads": False, "sprint": False})
    monkeypatch.setattr(skill.enter_place, "sample", lambda observation: True)
    result = skill._entering(Room(inside=True).observation(12.5))
    assert result.reason.startswith("entered")
    assert indoors.entrance().at == 12.5


def test_p81_unsure_model_does_not_cancel_confirmed_outdoors(monkeypatch):
    from types import SimpleNamespace

    class Model:
        def ask(self, *args, **kwargs):
            return True

        def answer(self, at):
            return SimpleNamespace(indoors=1.0 if at < 0.8 else 0.0 if at < 1.6 else 0.7, error=None)

    monkeypatch.setattr(indoors, "INDEPENDENT", False)
    monkeypatch.setattr(indoors, "read", lambda frame: None)
    monkeypatch.setattr(ahead, "place", Model)
    skill = LeaveBuilding({})
    monkeypatch.setattr(
        skill.guard,
        "step",
        lambda *args: SimpleNamespace(failed=False, state="look", left=(0, 0), right=(0, 0), buttons=()),
    )
    room = Room(inside=True)
    first_clear = None
    for i in range(80):
        result = skill.step(room.observation(i / 10))
        if skill.clear is not None:
            first_clear = skill.clear if first_clear is None else first_clear
            assert skill.clear == first_clear
        if result.status != "running":
            break
    assert first_clear is not None and first_clear < 1.7
    assert result.status == "done" and result.reason == "outdoors"
