"""The real conductor and runner carry one trip; only map outcomes are injected.

An injected outcome belongs to the currently executed waypoint call. Recorded downstream
results are never used for actions the new policy did not take. Entry and driving run for real.
"""

import json
from collections import deque
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from pilot.cli import drive_config
from pilot.conductor import Conductor, run_play
from pilot.contract import NEUTRAL_PAD, Blip, Detection, Hud, Observation, Reading, SkillResult
from pilot.drive import Driver
from pilot.flow import Flow
from pilot.head import SkillCall
from pilot.mission import MissionHead
from pilot.scene import SceneText
from pilot.skills import REGISTRY, SkillRunner
from pilot.waypoint import SetWaypoint

RGB = np.zeros((720, 1280, 3), dtype=np.uint8)
FIXTURES = Path(__file__).parent / "fixtures"
PLACE = "Ammu-Nation"
GOOD = Reading("tilted", "purple", 0, 0, 0, False, 1)
SUCCESS = f"waypoint set: {PLACE} (1000m); gameplay observed"


class NoEvents:
    def update(self, *args, **kwargs):
        return ()


class Session:
    def __init__(self, tmp_path, monkeypatch, *, outcomes=(), seconds=900, closes_map=True):
        self.now = 0.0
        self.reading = GOOD
        self.hud = Hud(wanted=0, health=1)
        self.objects = ()
        self.mode = "vehicle"
        self.distance = 1000
        self.moving = None
        self.closes_map = closes_map
        self.close_at = None
        self.waypoints = []
        self.outcomes = deque(outcomes)
        owner = self

        class MapOutcome(SetWaypoint):
            def step(self, observation):
                if self.started is None:
                    self.started = observation.time
                    owner.waypoints.append(dict(self.call_args))
                    return SkillResult()
                if self.finished is None and owner.outcomes:
                    status, reason, screen = owner.outcomes.popleft()
                    owner.screen(screen)
                    self.finished = SkillResult(status=status, reason=reason)
                return self.finished or SkillResult()

        monkeypatch.setitem(REGISTRY, "set_waypoint", MapOutcome)
        self.conductor = Conductor(
            tmp_path / "session",
            head=MissionHead(task="trip", place=PLACE, task_seconds=seconds),
            runner=SkillRunner(driver_factory=lambda: Driver(drive_config([]))),
            detector=NoEvents(),
            flow=Flow(),
            notebook=tmp_path / "notes",
            clock=lambda: self.now,
        )
        self.trip = self.conductor.trip

    def screen(self, name):
        self.hud = replace(self.hud, screen=name)
        self.reading = replace(
            self.reading, corrupt=name != "game", minimap="tilted" if name == "game" else "none"
        )

    def tick(self, dt=0.1, *, events=(), text=None):
        self.now += dt
        if self.close_at is not None and self.now >= self.close_at:
            self.screen("game")
            self.close_at = None
        reading = replace(self.reading, gps_distance=self.distance, gps_time=self.now)
        result = self.conductor.tick(
            Observation(
                reading,
                self.moving,
                self.now,
                hud=self.hud,
                mode=self.mode,
                objects=self.objects,
                objects_time=self.now,
            ),
            RGB,
            frame_time=self.now,
            events=events,
            text=text,
        )
        if "circle" in result.pad.buttons and self.closes_map:
            self.close_at = self.now + 0.15
        return result

    def until(self, predicate, *, seconds=40):
        end = self.now + seconds
        while self.now < end:
            result = self.tick()
            if predicate():
                return result
        pytest.fail(f"condition not reached: {self.trip.__dict__}; runner={self.conductor.runner.describe()}")

    def active(self, name):
        active = self.conductor.runner.active
        return active is not None and active.name == name

    def drive(self):
        self.outcomes.append(("done", SUCCESS, "game"))
        self.until(lambda: self.active("drive_route"))
        return self.conductor.runner.active

    def rows(self, kind):
        return [
            row
            for row in map(json.loads, (self.conductor.directory / "head.jsonl").read_text().splitlines())
            if row["type"] == kind
        ]

    def close(self):
        self.conductor.close()


@pytest.fixture
def session(tmp_path, monkeypatch):
    value = Session(tmp_path, monkeypatch)
    yield value
    value.close()


def test_recorded_car_beside_foot_marker_owns_the_first_plan(session):
    rows = json.loads((FIXTURES / "own-car-1957.json").read_text())
    raw = next(row["request"] for row in rows if row["request"]["objects"])
    reading = {**raw["minimap"], "blips": tuple(Blip(**blip) for blip in raw["minimap"]["blips"])}
    session.reading = Reading(**reading)
    session.objects = tuple(Detection(**obj) for obj in raw["objects"])
    session.mode = "foot"
    session.until(lambda: session.active("enter_vehicle"))
    for _ in range(15):
        session.tick()
    plans = [row["plan"] for row in session.rows("response") if row["plan"]]
    assert [plan[0]["name"] for plan in plans] == ["enter_vehicle"]
    assert not session.waypoints
    assert session.trip.step == "car"


def test_recorded_unknown_tilted_map_does_not_skip_entry(session):
    data = json.loads((FIXTURES / "trip-recorded-requests.json").read_text())
    raw = data["sequences"]["foot_after_map"][1]["request"]
    session.reading = Reading(
        **{**raw["minimap"], "blips": tuple(Blip(**b) for b in raw["minimap"]["blips"])}
    )
    session.mode = "unknown"
    session.until(lambda: session.active("enter_vehicle"))
    for _ in range(10):
        session.tick()
    assert session.trip.step == "car"
    assert not session.waypoints


def test_quiet_sixty_second_request_preserves_drive_and_queue(session):
    active = session.drive()
    session.conductor.runner.append((SkillCall("wait", {"duration": 1}), SkillCall("wait", {"duration": 1})))
    queue = tuple(session.conductor.runner.queue)
    start = session.now
    for _ in range(620):
        session.distance -= 0.8
        session.tick()
    assert session.now - start > 60
    assert session.conductor.runner.active is active
    assert tuple(session.conductor.runner.queue) == queue
    assert session.trip.place == PLACE
    assert session.rows("response")[-1]["disposition"] == "kept"
    assert len(session.waypoints) == 1


def test_two_equal_waits_are_distinct_attempts_and_waypoint_third_try_drives(session):
    session.outcomes.extend(
        [
            ("failed", "map-shift-unverified; gameplay observed", "game"),
            ("failed", "map-shift-unverified; gameplay observed", "game"),
            ("done", SUCCESS, "game"),
        ]
    )
    session.until(lambda: session.active("drive_route"))
    waits = [row for row in session.rows("trip_attempt") if row["name"] == "wait"]
    assert len(waits) == 2
    assert waits[0]["attempt_id"] != waits[1]["attempt_id"]
    assert [(row["status"], row["reason"], row["args"]) for row in waits] == [
        ("done", "time-limit", {"duration": 1}),
        ("done", "time-limit", {"duration": 1}),
    ]
    assert len(session.waypoints) == 3
    assert session.trip.step == "drive" and session.trip.verdict is None


def test_three_failed_waypoints_close_the_map_before_terminal_verdict(session):
    session.outcomes.extend([("failed", "map-shift-unverified", "map")] * 3)
    session.until(lambda: session.trip.verdict is not None)
    assert session.trip.verdict["status"] == "failed"
    assert "three attempts" in session.trip.verdict["reason"]
    assert session.hud.screen == "game"
    assert len(session.waypoints) == 3
    assert any(
        "circle" in action["buttons"] for row in session.rows("flow_exit") for action in row["actions"]
    )
    assert not session.conductor.runner.has_plan
    assert session.tick().pad == NEUTRAL_PAD


def test_unclosed_recorded_map_is_terminal_and_never_restarts(tmp_path, monkeypatch):
    data = json.loads((FIXTURES / "trip-recorded-requests.json").read_text())
    raw = data["sequences"]["unclosed_map"][1]["request"]
    reason = raw["last_skill"]["reason"]
    value = Session(tmp_path, monkeypatch, outcomes=[("failed", reason, "map")], closes_map=False)
    try:
        value.until(lambda: value.trip.verdict is not None)
        assert value.trip.verdict["status"] == "failed"
        assert "screen recovery" in value.trip.verdict["reason"]
        assert len(value.waypoints) == 1
        count = len(value.rows("response"))
        assert value.tick(1000).pad == NEUTRAL_PAD
        assert len(value.rows("response")) == count
        assert len(value.rows("trip_end")) == 1
    finally:
        value.close()


def test_map_back_passes_both_locks_but_damaged_game_and_stale_map_do_not(tmp_path):
    def run(directory, screen, frame_age):
        conductor = Conductor(directory, flow=Flow(), detector=NoEvents())
        try:
            reading = Reading("none", "none", None, None, None, True, 0)
            pads = [
                conductor.tick(
                    Observation(reading, None, t, hud=Hud(screen=screen)), RGB, frame_time=t - frame_age
                ).pad
                for t in (0, 0.1, 0.2)
            ]
            return pads
        finally:
            conductor.close()

    assert any("circle" in pad.buttons for pad in run(tmp_path / "map", "map", 0.14))
    assert all(not pad.buttons for pad in run(tmp_path / "game", "game", 0))
    assert all(not pad.buttons for pad in run(tmp_path / "stale", "map", 2))


def test_time_limit_with_progress_continues_same_step_without_recovery(session):
    first = session.drive()
    for _ in range(1210):
        session.distance -= 0.5
        session.tick()
    assert session.active("drive_route")
    assert session.conductor.runner.active is not first
    assert session.trip.recovery == 0
    assert session.trip.waypoint_id is not None and len(session.waypoints) == 1
    ended = [row for row in session.rows("trip_attempt") if row["name"] == "drive_route"]
    assert ended[0]["reason"] == "time-limit" and ended[0]["end_distance"] < ended[0]["start_distance"]


def test_no_progress_recovery_order_then_failure(session):
    # A car that drives is driven off twice before it is left, the next car gets the same two tries,
    # and only then is the trip given up. The destination is set once.
    session.drive()
    for _ in range(2):
        session.until(lambda: session.active("get_away"), seconds=30)
        session.until(lambda: session.active("drive_route"))
    session.until(lambda: session.active("press"), seconds=30)
    # The new press really ran. The following changed observation is an explicit exit simulation.
    session.tick()
    session.reading = replace(session.reading, minimap="flat")
    session.mode = "foot"
    session.until(lambda: session.active("walk_road"))
    session.until(lambda: session.active("enter_vehicle"))
    session.reading = replace(session.reading, minimap="tilted")
    session.mode = "vehicle"
    session.until(lambda: session.active("drive_route"))
    for _ in range(2):
        session.until(lambda: session.active("get_away"), seconds=30)
        session.until(lambda: session.active("drive_route"))
    session.until(lambda: session.trip.verdict is not None, seconds=30)
    assert session.trip.verdict["status"] == "failed"
    rows = session.rows("trip_recovery")
    assert [row["stage"] for row in rows] == [1, 2, 3, 4, 5, 6]
    assert [row["method"] for row in rows] == ["loose", "loose", "exit", "loose", "loose", None]
    assert len(session.waypoints) == 1
    assert session.trip.place == PLACE


def test_a_drive_that_gives_up_beside_its_route_keeps_the_car(session):
    # 20261113-224327: the route began behind the car, the driver gave up twice within ten seconds,
    # driving on ended at once because a route was on the map, and the pilot left a car that drove.
    session.drive()
    session.conductor.runner.stop("failed-recovery")
    session.until(lambda: session.active("get_away"), seconds=5)
    session.until(lambda: session.active("drive_route"), seconds=15)
    ended = [row for row in session.rows("trip_attempt") if row["name"] == "get_away"]
    assert len(ended) == 1 and ended[0]["status"] == "done"
    session.conductor.runner.stop("failed-recovery")
    session.until(lambda: session.active("get_away"), seconds=5)
    assert not [row for row in session.rows("trip_attempt") if row["name"] == "press"]
    assert session.trip.verdict is None and len(session.waypoints) == 1


def test_driving_off_under_stars_to_its_limit_costs_no_second_recovery(session):
    session.drive()
    session.conductor.runner.stop("failed-recovery")
    session.until(lambda: session.active("get_away"), seconds=5)
    session.hud = replace(session.hud, wanted=2)
    session.until(lambda: session.active("drive_route"), seconds=15)
    ended = [row for row in session.rows("trip_attempt") if row["name"] == "get_away"]
    assert ended[0]["status"] == "failed" and ended[0]["reason"].startswith("time-limit")
    assert [row["stage"] for row in session.rows("trip_recovery")] == [1]


def test_a_car_that_is_held_is_left_at_once(session):
    session.drive()
    session.conductor.runner.stop("dead-or-held")
    session.until(lambda: session.active("press"), seconds=5)
    assert [row["method"] for row in session.rows("trip_recovery")] == ["exit"]


def test_an_exit_seen_late_is_not_pressed_a_second_time(session):
    # 20261113-224327: the door took 2.3 s and the eye another moment, the check came 0.8 s after
    # the figure stood outside, and a second triangle put it back into the car.
    session.drive()
    session.conductor.runner.stop("dead-or-held")
    session.until(lambda: session.active("press"), seconds=5)
    session.until(lambda: session.active("wait"), seconds=5)
    for _ in range(24):
        session.tick()
    # Out of the car, as the map shows it, while the eye still says seated.
    session.reading = replace(session.reading, minimap="flat", route="none")
    for _ in range(8):
        session.tick()
    session.mode = "foot"
    session.until(lambda: session.active("walk_road"), seconds=10)
    presses = [row for row in session.rows("trip_attempt") if row["name"] == "press"]
    assert len(presses) == 1


def test_an_exit_that_stays_unclear_is_not_pressed_a_second_time(session):
    session.drive()
    session.conductor.runner.stop("dead-or-held")
    session.until(lambda: session.active("press"), seconds=5)
    session.until(lambda: session.active("wait"), seconds=5)
    # The map shows no seat and the eye never says foot: the way into a car decides, not a press.
    session.reading = replace(session.reading, minimap="flat", route="none")
    session.until(lambda: session.active("enter_vehicle"), seconds=15)
    presses = [row for row in session.rows("trip_attempt") if row["name"] == "press"]
    assert len(presses) == 1 and session.trip.step == "car" and session.trip.verdict is None


def test_stretches_that_end_unread_are_not_stretches_without_progress(session):
    session.drive()
    for _ in range(100):
        session.distance -= 2
        session.tick()
    session.distance = None
    for _ in range(2600):
        session.tick()
    ended = [row for row in session.rows("trip_attempt") if row["name"] == "drive_route"]
    assert len(ended) >= 2 and all(row["reason"] == "time-limit" for row in ended)
    assert session.active("drive_route") and not session.rows("trip_recovery")


def test_a_distance_that_cannot_be_read_is_no_standstill(session):
    # 20261113-225006: on a bright road the printed distance was not read for 39 s while the car
    # drove, and the trip took that for a drive that came no nearer.
    session.drive()
    for _ in range(100):
        session.distance -= 2
        session.tick()
    left, session.distance = session.distance, None
    for _ in range(400):
        session.tick()
    assert session.active("drive_route") and not session.rows("trip_recovery")
    session.distance = left - 10
    for _ in range(100):
        session.tick()
    assert session.active("drive_route") and not session.rows("trip_recovery")
    # Read again and no nearer: now it counts.
    session.until(lambda: session.active("get_away"), seconds=30)
    assert [row["stage"] for row in session.rows("trip_recovery")] == [1]


@pytest.mark.parametrize("news", ["stars", "objective", "health", "standing", "ending"])
def test_news_does_not_take_the_running_drive(session, news):
    active = session.drive()
    events = []
    text = None
    if news == "stars":
        session.hud = replace(session.hud, wanted=3)
        events = [{"kind": "wanted_changed", "wanted": 3}]
    elif news == "health":
        session.hud = replace(session.hud, health=0.1)
        events = [{"kind": "low_health"}]
    elif news == "objective":
        text = SceneText(objective="Folge dem Wagen.")
        events = [{"kind": "objective_changed"}]
    else:
        events = [{"kind": "standing" if news == "standing" else "plan_ending"}]
    for _ in range(10):
        session.tick(events=events, text=text)
    assert session.conductor.runner.active is active
    assert session.trip.step == "drive"
    assert session.trip.verdict is None


def test_death_restarts_same_destination_at_car_only_twice(session):
    session.drive()
    for death in range(3):
        session.screen("wasted")
        for _ in range(5):
            assert session.tick().pad == NEUTRAL_PAD
        if death == 2:
            break
        session.screen("game")
        session.reading = replace(session.reading, minimap="flat", route="none")
        session.mode = "foot"
        session.until(lambda: session.active("enter_vehicle"))
        assert session.trip.step == "car" and session.trip.place == PLACE
        assert session.trip.waypoint_id is None
    assert session.trip.verdict["status"] == "failed"
    assert "death/arrest" in session.trip.verdict["reason"]


def test_human_hand_suspends_and_rechecks_seat_before_same_step(session):
    session.drive()
    destination = session.trip.place
    session.conductor.refuse(session.now, True)
    for _ in range(20):
        assert session.tick().pad == NEUTRAL_PAD
    assert not session.conductor.runner.has_plan
    assert session.trip.suspended == "human"
    session.conductor.refuse(session.now, False)
    session.until(lambda: session.active("enter_vehicle"))
    assert session.trip.step == "drive" and session.trip.place == destination
    session.until(lambda: session.active("drive_route"))
    # The route is still on the map: the hand moved no waypoint, and the map is not opened again.
    assert session.trip.step == "drive" and len(session.waypoints) == 1
    assert len(session.rows("trip_suspended")) == len(session.rows("trip_resumed")) == 1


def test_a_waypoint_gone_after_the_hand_is_set_again_for_the_same_place(session):
    session.drive()
    session.conductor.refuse(session.now, True)
    for _ in range(20):
        session.tick()
    session.reading = replace(session.reading, route="none")
    session.conductor.refuse(session.now, False)
    session.outcomes.append(("done", SUCCESS, "game"))
    session.until(lambda: len(session.waypoints) == 2)
    assert session.waypoints[1]["place"] == PLACE and session.trip.step == "drive"
    session.reading = replace(session.reading, route="purple")
    session.until(lambda: session.active("drive_route"))
    assert session.trip.recovery == 0


def test_a_picture_that_was_away_does_not_open_the_map_again(session):
    session.drive()
    for _ in range(10):
        session.now += 0.1
        session.conductor.missing(session.now)
    assert session.trip.suspended == "picture" and not session.conductor.runner.has_plan
    session.until(lambda: session.active("drive_route"))
    assert len(session.waypoints) == 1 and session.trip.step == "drive"
    assert [row["reason"] for row in session.rows("trip_resumed")] == ["picture"]


def test_progress_after_a_recovery_pays_it_back(session):
    session.drive()
    session.until(lambda: session.active("get_away"), seconds=30)
    assert session.trip.recovery == 1
    session.until(lambda: session.active("drive_route"))
    for _ in range(60):
        session.distance -= 1
        session.tick()
    assert session.trip.recovery == 0
    # The next snag begins at the first stage again instead of leaving the car.
    session.until(lambda: session.active("get_away"), seconds=40)
    assert [row["stage"] for row in session.rows("trip_recovery")] == [1, 1]
    assert session.trip.verdict is None


def test_route_gone_near_the_place_while_on_along_the_road_is_an_arrival(session):
    session.drive()
    session.until(lambda: session.active("get_away"), seconds=30)
    session.distance = 30
    for _ in range(5):
        session.tick()
    session.reading = replace(session.reading, route="none")
    session.until(lambda: session.trip.verdict is not None, seconds=5)
    assert session.trip.verdict["status"] == "reached"
    assert session.tick().pad == NEUTRAL_PAD and not session.conductor.runner.has_plan
    assert len(session.rows("trip_end")) == 1


def test_route_gone_far_from_the_place_is_no_arrival(session):
    session.drive()
    session.until(lambda: session.active("get_away"), seconds=30)
    session.distance = 400
    for _ in range(5):
        session.tick()
    session.reading = replace(session.reading, route="none")
    for _ in range(60):
        session.tick()
    assert session.trip.verdict is None or session.trip.verdict["status"] == "failed"


def test_a_route_drawn_a_moment_after_the_waypoint_costs_no_recovery(session):
    session.reading = replace(session.reading, route="none")
    session.outcomes.append(("done", SUCCESS, "game"))
    session.until(lambda: session.trip.step == "drive")
    for _ in range(10):
        session.tick()
    assert not session.active("drive_on") and session.trip.recovery == 0
    session.reading = replace(session.reading, route="purple")
    session.until(lambda: session.active("drive_route"))
    assert session.trip.recovery == 0 and not session.rows("trip_recovery")


def test_a_route_that_stays_away_goes_to_recovery_after_one_wait(session):
    session.reading = replace(session.reading, route="none")
    session.outcomes.append(("done", SUCCESS, "game"))
    session.until(lambda: session.active("drive_on"), seconds=20)
    assert [row["reason"] for row in session.rows("trip_recovery")] == ["route absent"]
    waits = [row for row in session.rows("trip_attempt") if row["name"] == "wait"]
    assert len(waits) == 1


def test_one_odd_screen_reading_does_not_cut_a_held_button_in_two(session):
    from pilot.contract import Pad

    active = session.drive()
    active.step = lambda observation: SkillResult(Pad(buttons=("triangle",)))
    assert session.tick().pad.buttons == ("triangle",)
    session.screen("pause")
    assert session.tick().pad.buttons == ("triangle",)
    session.screen("game")
    assert session.tick().pad.buttons == ("triangle",)
    assert session.conductor.runner.active is active and session.trip.suspended is None


def test_an_idle_trip_is_not_asked_on_every_tick(session):
    session.drive()
    session.conductor.runner.stop("interrupted")
    session.trip.issued = {"name": "nothing", "args": {}}  # an order whose receipt never comes
    before = session.conductor.request_count
    for _ in range(30):
        session.tick()
    assert session.conductor.request_count - before <= 8


def test_real_arrival_exports_evidence_and_reaches_neutral_terminal(session):
    session.drive()
    session.distance = 25
    for _ in range(8):
        session.tick()
    session.reading = replace(session.reading, route="none")
    session.until(lambda: session.trip.verdict is not None)
    assert session.trip.verdict["status"] == "reached"
    last = session.rows("trip_attempt")[-1]
    assert last["name"] == "drive_route" and last["route_seen"]
    assert last["end_distance"] == 25 and last["distance_age"] <= 5
    assert last["attempt_id"] > last["waypoint_attempt_id"]
    assert session.tick().pad == NEUTRAL_PAD
    assert not session.conductor.runner.has_plan
    assert len(session.rows("trip_end")) == 1


def test_trip_budget_is_failed_even_while_human_holds_the_controller(session):
    session.drive()
    session.conductor.refuse(session.now, True)
    assert session.tick(901).pad == NEUTRAL_PAD
    assert session.trip.verdict["status"] == "failed"
    assert "budget" in session.trip.verdict["reason"]


def test_runner_ids_and_result_evidence_survive_stop():
    runner = SkillRunner()
    runner.replace((SkillCall("drive_route", {"duration": 120}),))
    runner.tick(Observation(GOOD, True, 0))
    runner.tick(Observation(replace(GOOD, gps_distance=42, gps_time=0.1), True, 0.1))
    running = runner.describe()
    runner.stop("pad_refused")
    ended = runner.describe()
    assert running["attempt_id"] == ended["attempt_id"]
    assert ended["args"] == {"duration": 120}
    assert ended["end_distance"] == 42 and ended["route_seen"]
    runner.replace((SkillCall("wait", {"duration": 1}),))
    runner.tick(Observation(GOOD, None, 1))
    runner.tick(Observation(GOOD, None, 1.1))
    assert runner.describe()["attempt_id"] > ended["attempt_id"]


def test_recorded_p93_arrival_through_conductor_and_runner(session):
    session.drive()
    data = json.loads((FIXTURES / "p93_arrival.json").read_text())
    first = data["drive_readings"][0][0]
    offset = session.now + 0.1 - first
    for values in data["drive_readings"]:
        row = dict(zip(data["reading_fields"], values, strict=True))
        source_t = row.pop("source_t")
        if row.get("gps_time") is not None:
            row["gps_time"] += offset - data["clock_offset"]
        session.now = source_t + offset
        if row["minimap"] is None:
            session.conductor.missing(session.now, lost=False)
            continue
        reading = replace(GOOD, **row)
        session.conductor.tick(
            Observation(reading, True, session.now, hud=session.hud, mode="vehicle"),
            RGB,
            frame_time=session.now,
        )
        if session.trip.verdict is not None:
            break
    assert session.trip.verdict["status"] == "reached"
    receipt = session.rows("trip_attempt")[-1]
    assert receipt["reason"] == "arrived" and receipt["end_distance"] == 46
    assert receipt["distance_age"] <= 5
    assert session.conductor.last_pad == NEUTRAL_PAD


def test_quiet_request_uses_recorded_news_without_injecting_old_plan_results(session):
    active = session.drive()
    data = json.loads((FIXTURES / "trip-recorded-requests.json").read_text())
    quiet = data["sequences"]["quiet_and_waypoint_failures"][1]["request"]
    assert quiet["events"] == []
    queued = (SkillCall("wait", {"duration": 1}), SkillCall("wait", {"duration": 2}))
    session.conductor.runner.append(queued)
    old_queue = tuple(session.conductor.runner.queue)
    session.conductor.last_request_time = session.now - 60
    session.tick(events=quiet["events"], text=SceneText(objective=quiet["objective"]))
    assert session.conductor.runner.active is active
    assert tuple(session.conductor.runner.queue) == old_queue
    assert session.rows("response")[-1]["action"] == "go_on"


def test_failed_car_tries_change_method_and_keep_a_recently_seen_car(session):
    session.reading = replace(GOOD, minimap="flat", route="none")
    session.mode = "foot"
    session.objects = (Detection("car", (600, 280, 900, 600), 0.95),)
    session.until(lambda: session.active("enter_vehicle"))
    session.conductor.runner.stop("no entry observed")
    session.until(lambda: session.active("walk"))
    result = session.tick()
    assert result.pad.left[1] < 0  # Toward the last car, never away down the road.
    session.objects = ()
    session.until(lambda: session.active("enter_vehicle"))
    session.tick(2.1)  # The last detection has expired; road search is now justified.
    session.conductor.runner.stop("no entry observed")
    session.until(lambda: session.active("walk_road"))
    session.until(lambda: session.active("enter_vehicle"))
    session.conductor.runner.stop("no entry observed")
    # 20261113-225835: a third try without a car is not the end, the search goes on along the road
    # until its five minutes are spent.
    session.until(lambda: session.active("walk_road"))
    session.until(lambda: session.active("enter_vehicle"))
    assert session.trip.verdict is None
    session.until(lambda: session.trip.verdict is not None, seconds=400)
    assert session.trip.verdict["status"] == "failed"
    assert "no car within five minutes" in session.trip.verdict["reason"]
    assert session.now >= 300


def test_car_retry_without_recent_detection_looks_before_trying_again(session):
    session.reading = replace(GOOD, minimap="flat", route="none")
    session.mode = "foot"
    session.until(lambda: session.active("enter_vehicle"))
    session.conductor.runner.stop("no vehicle found")
    session.until(lambda: session.active("look"))
    session.until(lambda: session.active("enter_vehicle"))
    assert session.trip.car_attempts == 1


def test_progress_window_outlasts_short_drive_stretches(session):
    session.drive()
    for _ in range(260):
        if session.active("drive_route"):
            # Fault injection: end stretches early, without restarting the trip's progress clock.
            session.conductor.runner.active.limit = 2
        session.tick()
        if session.active("get_away"):
            break
    assert session.active("get_away")
    assert session.trip.recovery == 1
    ended = [row for row in session.rows("trip_attempt") if row["name"] == "drive_route"]
    assert len(ended) == 2
    assert all(row["reason"] in {"time-limit", "goal_trip_recovery"} for row in ended)


@pytest.mark.parametrize("wrong", ["other-place", "stale-arrival", "yellow-arrival"])
def test_missing_or_wrong_destination_evidence_cannot_reach(session, wrong):
    if wrong == "other-place":
        session.outcomes.extend([("done", "waypoint set: Suburban (50m); gameplay observed", "game")] * 3)
        session.until(lambda: session.trip.verdict is not None)
        assert session.trip.verdict["status"] == "failed" and session.trip.waypoint_id is None
        return
    session.drive()
    if wrong == "yellow-arrival":
        # A different route is not this trip's waypoint, even if the skill reports a nearby endpoint.
        session.reading = replace(session.reading, route="yellow")
    session.distance = 25
    for _ in range(10):
        session.tick()
    if wrong == "stale-arrival":
        session.distance = None
        for _ in range(60):
            session.tick()
    session.reading = replace(session.reading, route="none")
    for _ in range(20):
        session.tick()
    assert session.trip.verdict is None or session.trip.verdict["status"] == "failed"


def test_no_third_identical_plan_without_progress_in_waypoint_retries(session):
    session.outcomes.extend([("failed", "map-shift-unverified", "game")] * 3)
    session.until(lambda: session.trip.verdict is not None)
    plans = [row["plan"] for row in session.rows("response") if row["plan"]]
    assert all(not (a == b == c) for a, b, c in zip(plans, plans[1:], plans[2:], strict=False))
    attempts = session.rows("trip_attempt")
    assert len({row["attempt_id"] for row in attempts}) == len(attempts)
    assert len(session.rows("trip_started")) == len(session.rows("trip_end")) == 1


def test_real_runtime_stops_on_arrival_and_releases_the_pad(session):
    from pilot.bridge import Frame

    session.outcomes.append(("done", SUCCESS, "game"))
    session.distance = 40
    pads = []

    class Bridge:
        def frame(self, rect, after=None):
            return Frame(RGB, 0 if after is None else after + 1, 0)

        def pad(self, pad=None):
            pads.append(pad)
            return 200

        def record_start(self, directory, *, shadow):
            return session.conductor.directory

        def record_stop(self):
            pass

    class Pipeline:
        def step(self, *args, **kwargs):
            if session.active("drive_route"):
                session.distance = max(25, session.distance - 0.25)
            return (
                replace(
                    GOOD,
                    route="none" if session.distance <= 25 else "purple",
                    gps_distance=session.distance,
                    gps_time=session.now,
                ),
                True,
                None,
            )

        def close(self):
            pass

    class HudReader:
        @staticmethod
        def read(*args, **kwargs):
            return session.hud

    def sleep(seconds):
        session.now += max(seconds, 0.001)

    result = run_play(
        Bridge(),
        seconds=100,
        pipeline=Pipeline(),
        head=session.conductor.head,
        conductor_factory=lambda *args, **kwargs: session.conductor,
        clock=lambda: session.now,
        sleep=sleep,
        hud=HudReader(),
        ocr=False,
    )
    assert result["trip"]["status"] == "reached"
    assert result["elapsed"] < 15
    assert pads[-1] is None and pads[-2] == NEUTRAL_PAD
    assert session.conductor.closed


@pytest.mark.parametrize("status,exit_code", [("reached", 0), ("failed", 1)])
def test_trip_cli_prints_verdict_and_exit_code(monkeypatch, capsys, status, exit_code):
    from pilot import cli

    calls = []

    class Bridge:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def run(bridge, **kwargs):
        calls.append(kwargs)
        return {"trip": {"status": status, "place": PLACE, "reason": "observed in fixture"}}

    monkeypatch.setattr(cli, "Bridge", Bridge)
    monkeypatch.setattr(cli, "run_play", run)
    monkeypatch.setattr(cli, "ObjectReader", lambda: None)
    if exit_code:
        with pytest.raises(SystemExit) as error:
            cli.main(["play", "--task", "trip", "--place", PLACE])
        assert error.value.code == exit_code
    else:
        assert cli.main(["play", "--task", "trip", "--place", PLACE]) is None
    assert f"trip {status}: {PLACE}" in capsys.readouterr().out
    assert calls[0]["seconds"] == 900 and calls[0]["opening"] == () and calls[0]["guard"] is None
    assert calls[0]["head"].trip.place == PLACE


@pytest.mark.parametrize("args", [[], ["--guard"], ["--no-hud-flow"], ["--plan", "[]"]])
def test_invalid_trip_cli_never_opens_bridge(monkeypatch, args):
    from pilot import cli

    def forbidden():
        pytest.fail("invalid CLI opened the bridge")

    monkeypatch.setattr(cli, "Bridge", forbidden)
    arguments = ["play", "--task", "trip", *args]
    if args:
        arguments += ["--place", PLACE]
    with pytest.raises(SystemExit) as error:
        cli.main(arguments)
    assert error.value.code == 2


def test_intentional_waypoint_keeps_ticking_and_can_press_on_its_fresh_map(session):
    from pilot.contract import Pad

    session.until(lambda: session.active("set_waypoint"))
    skill = session.conductor.runner.active
    seen = []

    def step(observation):
        seen.append(observation.hud.screen)
        return SkillResult(Pad(buttons=("cross",)))

    skill.step = step
    session.screen("map")
    assert session.tick().pad.buttons == ("cross",)
    assert seen == ["map"]
    assert session.conductor.runner.active is skill
    assert session.trip.suspended is None


def test_human_suspension_also_suppresses_the_awake_nudge(session):
    session.drive()
    session.conductor.awake = 15
    session.conductor.last_input = None
    session.conductor.refuse(session.now, True)
    for _ in range(20):
        assert session.tick().pad == NEUTRAL_PAD


def test_an_ongoing_phone_call_does_not_pause_the_trip(session, monkeypatch):
    active = session.drive()
    session.conductor.flow.calls = True
    monkeypatch.setattr(session.conductor.flow, "on_call", lambda *args: True)
    session.hud = replace(session.hud, screen="phone")
    for _ in range(10):
        result = session.tick()
    assert result.pad.r2 > 0
    assert session.conductor.runner.active is active
    assert session.trip.suspended is None
