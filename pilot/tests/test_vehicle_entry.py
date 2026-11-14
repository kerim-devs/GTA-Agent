"""Vehicle-entry outcomes from recorded detections and a small delayed game model."""

import json
import math
from dataclasses import replace
from itertools import pairwise
from pathlib import Path

import pytest

from pilot.contract import NEUTRAL_PAD, Detection, Observation, Pad, Reading
from pilot.vehicle_entry import (
    DOOR_WAIT,
    MAX_ATTEMPTS,
    MAX_SECONDS,
    EnterVehicle,
    Vehicle,
    approach,
    choose_vehicle,
)


def px(x0, y0, x1, y1):
    return (x0 * 1280, y0 * 720, x1 * 1280, y1 * 720)


FAR = Detection("car", px(0.43, 0.42, 0.57, 0.52), 0.9)
BUMPER = Detection("car", px(0.41, 0.50, 0.55, 0.68), 0.9)
NEAR = Detection("car", px(0.30, 0.45, 0.70, 0.90), 0.9)


def obs(time, objects=(FAR,), *, age=0.0, minimap="flat", corrupt=False, delivered=True):
    return Observation(
        Reading(minimap, "none", None, None, None, corrupt, 1.0),
        None,
        time,
        objects=objects,
        objects_time=time - age if delivered else None,
        figure=Detection("person", px(0.42, 0.43, 0.52, 0.96), 0.9) if minimap == "flat" else None,
    )


@pytest.mark.parametrize(
    "args",
    [
        None,
        [],
        {"other": 1},
        {"duration": True},
        {"duration": "2"},
        {"duration": math.nan},
        {"duration": math.inf},
        {"kind": "bus"},
        {"kind": []},
        {"occupied": True},
        {"occupied": "yes"},
    ],
)
def test_arguments_reject_invalid_values(args):
    with pytest.raises(ValueError):
        EnterVehicle(args)


def test_metadata_clamping_and_hard_limit():
    assert EnterVehicle.name == "enter_vehicle"
    assert len(EnterVehicle.prompt) <= 400
    assert EnterVehicle({"duration": 100}).limit == MAX_SECONDS
    skill = EnterVehicle({"duration": -10})
    assert skill.limit == 0.1
    skill.step(obs(8, ()))
    result = skill.step(obs(8.11, ()))
    assert result.status == "failed" and result.reason.startswith("nothing found")
    assert result.pad == NEUTRAL_PAD


def test_release_then_human_length_press_then_neutral_animation_wait():
    skill = EnterVehicle({})
    assert skill.step(obs(0, (NEAR,))).pad == NEUTRAL_PAD
    for time in (0.04, 0.07, 0.10, 0.17):
        result = skill.step(
            obs(time, (), delivered=False, corrupt=True) if time > 0.04 else obs(time, (NEAR,))
        )
        assert result.pad == Pad(buttons=("triangle",))
    for time in (0.20, 0.7, 1.5, 2.9, DOOR_WAIT + 0.02):
        assert skill.step(obs(time, (), delivered=False, corrupt=True)).pad == NEUTRAL_PAD
    result = skill.step(obs(DOOR_WAIT + 0.05, (NEAR,)))
    assert result.status == "failed" and result.pad == NEUTRAL_PAD


def test_seated_proof_survives_corrupt_tick_but_rejects_short_false_map():
    skill = EnterVehicle({})
    skill.step(obs(0, (NEAR,)))
    skill.step(obs(0.04, (NEAR,)))
    for time, minimap, corrupt in (
        (0.2, "tilted", False),
        (1.03, "tilted", False),
        (1.1, "flat", False),
        (1.2, "tilted", False),
        (1.6, "flat", True),
        (2.19, "tilted", False),
    ):
        result = skill.step(obs(time, (), minimap=minimap, corrupt=corrupt, delivered=False))
        assert result.status == "running" and result.pad == NEUTRAL_PAD
    result = skill.step(obs(2.2, minimap="tilted"))
    assert result.status == "done" and result.reason.startswith("entered vehicle; vehicle=")
    assert result.pad == NEUTRAL_PAD and skill.step(obs(3)) == result


def test_already_seated_needs_two_seconds_and_uses_accepted_mode():
    skill = EnterVehicle({})
    for time in (0, 0.5, 0.83):
        assert skill.step(obs(time, minimap="tilted")).pad == NEUTRAL_PAD
    assert skill.step(obs(0.9)).pad == NEUTRAL_PAD
    for time in (1.0, 2.0, 2.99):
        assert skill.step(replace(obs(time), mode="vehicle")).status == "running"
    result = skill.step(replace(obs(3), mode="vehicle"))
    assert result.reason == "already in a vehicle" and result.pad == NEUTRAL_PAD
    assert EnterVehicle({}).step(replace(obs(0, minimap="tilted"), mode="foot")).pad == NEUTRAL_PAD


@pytest.mark.parametrize(
    "kwargs", [{"age": 0.501}, {"objects": ()}, {"delivered": False}, {"age": -0.1}, {"minimap": "none"}]
)
def test_unusable_detection_or_non_game_releases_motion(kwargs):
    skill = EnterVehicle({})
    skill.step(obs(-0.5))
    assert skill.step(obs(0)).pad.left[1] < 0
    assert skill.step(obs(0.51, **kwargs)).pad == NEUTRAL_PAD


def test_corrupt_map_releases_approach_and_blocks_a_new_entry_press():
    skill = EnterVehicle({})
    assert skill.step(obs(0, corrupt=True)).pad == NEUTRAL_PAD
    assert skill.step(obs(1.1, (NEAR,), corrupt=True)).pad == NEUTRAL_PAD
    assert skill.step(obs(1.14, (NEAR,), corrupt=True)).pad == NEUTRAL_PAD
    assert skill.step(obs(1.18, (NEAR,))).pad.buttons == ("triangle",)
    for time in (2, 3, 4):
        assert skill.step(obs(time, minimap="tilted", corrupt=True)).status == "running"


def test_none_releases_button_and_frozen_detection_expires():
    skill = EnterVehicle({})
    skill.step(obs(0, (NEAR,)))
    skill.step(obs(0.04, (NEAR,)))
    assert skill.step(replace(obs(0.05), mode="none")).pad == NEUTRAL_PAD
    frozen = EnterVehicle({})
    frozen.step(obs(0))
    assert frozen.step(obs(0.51, age=0.51)).pad == NEUTRAL_PAD


def test_target_leaving_range_between_release_and_press_is_approached_again():
    near = Detection("car", px(0.4, 0.43, 0.6, 0.66), 0.9)
    receding = Detection("car", px(0.44, 0.43, 0.56, 0.57), 0.9)
    skill = EnterVehicle({})
    assert skill.step(obs(0, (near,))).pad == NEUTRAL_PAD
    result = skill.step(obs(0.04, (receding,)))
    assert result.pad == NEUTRAL_PAD  # A receding car is observed before another approach.


def test_figure_steers_while_camera_follows_and_bumper_is_in_reach():
    side = Detection("car", px(0.72, 0.4, 0.92, 0.55), 0.9)
    skill = EnterVehicle({})
    skill.step(obs(0, (side,)))
    pad = skill.step(obs(0.5, (side,))).pad
    assert pad.left[0] > 0 and pad.left[1] <= -0.8 and pad.right[0] > 0
    normalized = replace(side, box=(0.72, 0.4, 0.92, 0.55))
    assert approach(normalized) == replace(pad, buttons=())
    assert pad.buttons == ("cross",)
    skill = EnterVehicle({})
    assert skill.step(obs(0, (BUMPER,))).pad == NEUTRAL_PAD
    assert skill.step(obs(0.04, (BUMPER,))).pad.buttons == ("triangle",)


def test_choice_prefers_standing_then_near_then_car():
    def vehicle(kind, box, motion="standing"):
        detection = Detection(kind, box, 0.9)
        return Vehicle(detection, 0, detection, 0, motion)

    car = vehicle("car", (0.3, 0.4, 0.5, 0.64))
    bus = vehicle("bus", (0.2, 0.2, 0.8, 0.6))
    passing = vehicle("car", (0.2, 0.3, 0.8, 0.9), "moving")
    far = vehicle("car", (0.4, 0.3, 0.5, 0.4))
    assert choose_vehicle([passing, car, far]) is car
    assert choose_vehicle([bus, car]) is car
    assert choose_vehicle([far, car]) is car


def test_stationary_probe_passes_over_traffic_before_starting_approach():
    skill = EnterVehicle({})
    parked = Detection("car", px(0.36, 0.36, 0.46, 0.49), 0.9)
    for tick in range(6):
        time = tick / 10
        passing = Detection("car", px(0.44 + time * 0.20, 0.37, 0.56 + time * 0.20, 0.54), 0.9)
        skill.step(obs(time, (passing, parked)))
    assert skill.target.obj.box == pytest.approx((0.36, 0.36, 0.46, 0.49))
    assert skill.target.motion == "standing"


def test_kind_filter_bad_boxes_and_confidence():
    motorcycle = Detection("motorcycle", px(0.45, 0.5, 0.55, 0.65), 0.9)
    for kind, expected in (("motorcycle", "motorcycle"), ("car", "car"), ("any", "car")):
        skill = EnterVehicle({"kind": kind})
        skill.step(obs(0, (motorcycle, NEAR, FAR)))
        assert skill.target.obj.kind == expected
    for bad in (
        replace(NEAR, confidence=0.3),
        replace(NEAR, confidence=math.nan),
        replace(NEAR, box=px(0.4, 0.5, math.nan, 0.9)),
    ):
        skill = EnterVehicle({})
        assert not skill.step(obs(0, (bad,))).pad.buttons
        assert skill.target is None


def test_no_vehicle_looks_locally_then_returns_search_early():
    skill = EnterVehicle({"duration": 12})
    assert skill.step(obs(0, ())).pad.right != (0, 0)
    for time in (1.5, 3.9):
        result = skill.step(obs(time, ()))
        assert result.pad.left == (0, 0) and result.status == "running"
    result = skill.step(obs(4, ()))
    assert "no car in reach" in result.reason and result.pad == NEUTRAL_PAD


def test_no_car_ends_early_without_needing_a_road_frame():
    skill = EnterVehicle({"duration": 6})
    for t in (0, 2):
        assert skill.step(obs(t, ())).status == "running"
    result = skill.step(obs(4, ()))
    assert result.status == "failed" and "no car in reach" in result.reason


def test_lost_detections_after_press_end_neutrally_without_waiting_full_limit():
    skill = EnterVehicle({})
    skill.step(obs(0, (NEAR,)))
    skill.step(obs(0.04, (NEAR,)))
    result = skill.step(obs(12.1, delivered=False))
    assert result.status == "failed" and result.reason == "detections lost after entry press"
    assert result.pad == NEUTRAL_PAD


def test_neighbouring_cars_keep_identity_when_detector_order_changes():
    skill = EnterVehicle({})
    left = Detection("car", px(0.31, 0.4, 0.43, 0.56), 0.9)
    right = Detection("car", px(0.44, 0.4, 0.56, 0.55), 0.9)
    skill.step(obs(0, (left, right)))
    chosen = skill.target
    chosen.tries = 2
    for t, objects in ((0.1, (right, left)), (0.2, (left, right))):
        skill.step(obs(t, objects))
        assert skill.target is chosen and chosen.obj.box == pytest.approx((0.31, 0.4, 0.43, 0.56))
        assert all(v.tries == 0 for v in skill.vehicles if v is not chosen)


def test_local_search_changes_to_approach_when_a_stopped_vehicle_appears():
    skill = EnterVehicle({})
    skill.step(obs(0, ()))
    assert skill.step(obs(2, ())).pad.left == (0, 0)
    skill.step(obs(3, (FAR,)))
    assert skill.step(obs(3.5, (FAR,))).pad.left[1] < 0


@pytest.mark.parametrize("phase", ["approach", "tap", "wait", "retry"])
def test_stop_releases_every_phase_and_skill_protects_head_replacement(phase):
    skill = EnterVehicle({})
    skill.step(obs(0, (NEAR,)))
    skill.phase = phase
    assert skill.uninterruptible
    result = skill.stop("replaced")
    assert result.status == "failed" and result.reason == "replaced"
    assert result.pad == NEUTRAL_PAD and skill.step(obs(0.1)) == result


def test_missing_delivery_and_invalid_clock_fail_neutrally():
    skill = EnterVehicle({})
    skill.step(obs(0, delivered=False))
    assert skill.step(obs(5, delivered=False)).reason == "no detections delivered at all"
    skill = EnterVehicle({})
    skill.step(obs(1))
    assert skill.step(obs(0)).reason == "invalid observation time"
    assert EnterVehicle({}).step(obs(math.nan)).pad == NEUTRAL_PAD
    assert EnterVehicle({}).step(None).reason == "invalid observation"


class EntryGame:
    """A press in range starts delayed door travel; movement cancels that travel."""

    def __init__(
        self,
        *,
        distance=5.0,
        lost=0,
        locked=False,
        away=False,
        blocked=False,
        latency=3.1,
        kind="car",
        alternate=False,
        road_x=None,
        driver=False,
        road_width=10,
    ):
        self.distance, self.lost, self.locked = distance, lost, locked
        self.away, self.blocked, self.latency, self.kind = away, blocked, latency, kind
        self.alternate = alternate
        self.road_x = road_x
        self.road_width = road_width  # 10: a band the edge reader can use, 3: a thin line it cannot
        self.driver = driver
        self.driver_out = False
        self.evict_at = None
        self.lane_idle = 0.0
        self.longest_lane_idle = 0.0
        self.pending = None
        self.seated = False
        self.held = False
        self.presses = 0
        self.out_of_range = 0
        self.cancelled = 0

    def observation(self, time):
        if self.pending is not None and time >= self.pending:
            self.seated = True
            if self.driver and self.evict_at is None:
                self.evict_at = time + 2
        if self.evict_at is not None and time >= self.evict_at:
            self.driver_out = True
            self.seated = False
        height = 0.65 / (self.distance + 1)
        vehicle = Detection(self.kind, px(0.5 - height, 0.43, 0.5 + height, 0.43 + height), 0.95)
        objects = () if self.away and time > 0.5 else (vehicle,)
        if self.alternate and time > 15:
            # The locked car departs and another car stops at the opposite side.
            objects = (Detection("car", px(0.62, 0.45, 0.85, 0.8), 0.95),)
        if self.driver and objects:
            a, b, c, d = vehicle.box
            person = Detection(
                "person",
                (a + 0.35 * (c - a), b + 0.1 * (d - b), a + 0.65 * (c - a), b + 0.55 * (d - b)),
                0.95,
            )
            objects += (person,)
        observation = obs(time, objects, minimap="tilted" if self.seated else "flat")
        if self.pending is not None and not self.seated:
            # A real door animation changes the standing pose before the map tilts.
            observation = replace(observation, figure=Detection("person", px(0.5, 0.5, 0.58, 0.9), 0.9))
        if self.road_x is not None:
            from test_foot import road_frame

            observation = replace(
                observation, frame=road_frame(-self.road_x, width=self.road_width, angle=15)
            )
        return observation

    def apply(self, time, pad):
        if self.road_x is not None:
            self.road_x += pad.left[0] * 1.2
            if abs(self.road_x) < 7 and pad.left == (0, 0) and not self.seated:
                self.lane_idle += 0.1
            else:
                self.lane_idle = 0
            self.longest_lane_idle = max(self.longest_lane_idle, self.lane_idle)
        if pad.left != (0, 0):
            if self.pending is not None and not self.seated:
                self.cancelled += 1
                self.pending = None
            if not self.blocked:
                self.distance = max(0.3, self.distance - max(0, -pad.left[1]) * 0.14)
        pressed = "triangle" in pad.buttons
        if pressed and not self.held:
            self.presses += 1
            if self.distance > 2:
                self.out_of_range += 1
            elif self.lost:
                self.lost -= 1
            elif (not self.locked or (self.alternate and time > 15)) and not self.away:
                self.pending = time + self.latency
        self.held = pressed


def play(game, duration=MAX_SECONDS):
    skill = EnterVehicle({"duration": duration})
    previous = False
    press_times = []
    for tick in range(int(duration * 10) + 2):
        time = tick / 10
        result = skill.step(game.observation(time))
        assert set(result.pad.buttons) <= {"triangle", "cross"}
        assert not {"triangle", "cross"} <= set(result.pad.buttons)
        assert result.pad.l2 == result.pad.r2 == 0
        if "triangle" in result.pad.buttons and not previous:
            press_times.append(time)
        previous = "triangle" in result.pad.buttons
        game.apply(time, result.pad)
        if result.status != "running":
            assert result.pad == NEUTRAL_PAD
            return result, game, press_times
    pytest.fail("skill exceeded hard deadline")


@pytest.mark.parametrize(
    "options",
    [
        {},
        {"lost": 1},
        {"latency": 5.3},
        {"latency": 11.6, "kind": "bus"},
        {"locked": True, "alternate": True},
    ],
)
def test_game_model_confirms_animation_but_leaves_an_ineffective_press(options):
    result, game, presses = play(EntryGame(**options))
    if options.get("lost") or options.get("locked"):
        assert result.status == "failed" and not game.seated
        assert len(presses) == 1 and result.pad == NEUTRAL_PAD
        assert result.reason.startswith("door locked or blocked")
        return
    assert result.status == "done" and result.reason.startswith("entered vehicle; vehicle=")
    assert game.seated and game.cancelled == 0
    assert 1 <= len(presses) <= MAX_ATTEMPTS
    assert all(b - a >= DOOR_WAIT for a, b in pairwise(presses))


@pytest.mark.parametrize(
    "options, reason",
    [
        ({"away": True, "distance": 1}, "vehicle drove away or was lost"),
        ({"blocked": True, "distance": 10}, "vehicle out of reach"),
        ({"locked": True, "distance": 1}, "door locked or blocked"),
    ],
)
def test_game_model_failures_are_bounded_actionable_and_neutral(options, reason):
    result, game, presses = play(EntryGame(**options))
    assert result.status == "failed" and result.reason.startswith(reason)
    assert not game.seated and len(presses) <= MAX_ATTEMPTS


def test_approach_reaches_the_door_before_its_only_press():
    result, game, _ = play(EntryGame(distance=2.5))
    assert game.out_of_range == 0
    assert result.status == "done" and game.presses == 1


RUNS = json.loads((Path(__file__).resolve().parents[2] / "lab/enter/runs.json").read_text())["runs"]
for run in RUNS:
    run["samples"] = [s for s in run["samples"] if s["skill"][0] == "enter_vehicle"]


def recorded_observation(sample):
    return replace(
        obs(
            sample["t"],
            tuple(Detection(kind, tuple(box), confidence) for kind, box, confidence in sample["objects"]),
            minimap=sample["map"],
            corrupt=sample["corrupt"],
        ),
        figure=None,
    )


@pytest.mark.parametrize("index", [1, 2, 3, 4, 5, 6, 8])
def test_recorded_vehicle_boxes_without_player_evidence_never_press(index):
    skill = EnterVehicle({})
    for sample in RUNS[index]["samples"]:
        assert "triangle" not in skill.step(recorded_observation(sample)).pad.buttons


def test_recorded_corrupt_map_releases_the_approach():
    skill = EnterVehicle({})
    acted = []
    for sample in RUNS[6]["samples"]:
        result = skill.step(recorded_observation(sample))
        if sample["corrupt"] and sample["objects"] and (result.pad.left != (0, 0) or result.pad.buttons):
            acted.append(sample["t"])
    assert not acted


def test_recorded_stopped_sedan_still_needs_player_evidence():
    skill = EnterVehicle({})
    for sample in RUNS[1]["samples"]:
        assert "triangle" not in skill.step(recorded_observation(sample)).pad.buttons


def test_recorded_far_vehicle_stretch_returns_search_without_claiming_an_entry():
    skill = EnterVehicle({})
    results = [skill.step(recorded_observation(s)) for s in RUNS[0]["samples"]]
    assert not any("triangle" in r.pad.buttons for r in results)
    assert results[-1].status == "failed" and "no car in reach" in results[-1].reason


def test_recorded_no_vehicle_stretch_never_follows_the_map():
    skill = EnterVehicle({})
    results = [skill.step(recorded_observation(s)) for s in RUNS[7]["samples"]]
    assert all(r.pad.left == (0, 0) and not r.pad.buttons for r in results)
    assert results[-1].status == "failed" and "no car in reach" in results[-1].reason


def test_between_two_deliveries_of_detections_the_walk_goes_on():
    skill = EnterVehicle({})
    skill.step(obs(-0.5))
    first = skill.step(obs(0.0))
    assert first.pad.left[1] < 0
    # Ticks come thirty times a second, detections twenty: this tick has the detections of the last.
    assert skill.step(obs(0.033, age=0.033)).pad == first.pad
    assert skill.step(obs(0.3, age=0.3)).pad == NEUTRAL_PAD


def test_within_reach_a_car_is_taken_before_a_nearer_bus():
    bus = Detection("bus", (0.20, 0.30, 0.60, 0.95), 0.9)
    car = Detection("car", (0.55, 0.45, 0.85, 0.80), 0.9)
    vehicles = [Vehicle(bus, 0.0, bus, 0.0), Vehicle(car, 0.0, car, 0.0)]
    assert choose_vehicle(vehicles).obj.kind == "car"
    far = Detection("car", (0.55, 0.40, 0.65, 0.48), 0.9)
    assert choose_vehicle([Vehicle(bus, 0.0, bus, 0.0), Vehicle(far, 0.0, far, 0.0)]).obj.kind == "bus"


def vehicle_at(box, motion="unknown", occupancy="unknown", kind="car"):
    obj = Detection(kind, box, 0.9)
    return Vehicle(obj, 0, obj, 0, motion, occupancy=occupancy)


NEAR_BOX = (0.30, 0.45, 0.70, 0.90)  # within reach
FAR_BOX = (0.45, 0.40, 0.55, 0.48)  # not


def test_ranking_puts_a_moving_vehicle_last_then_reach_then_evidence():
    near_unknown = vehicle_at(NEAR_BOX)
    far_parked = vehicle_at(FAR_BOX, "standing", "parked-candidate")
    near_moving = vehicle_at(NEAR_BOX, "moving")
    # within reach comes before standing evidence: the unknown vehicle beside the figure is taken first
    assert choose_vehicle([far_parked, near_unknown]) is near_unknown
    # a vehicle seen moving comes last, even within reach
    assert choose_vehicle([near_moving, far_parked]) is far_parked
    assert choose_vehicle([near_moving]) is near_moving  # last, not gone
    # among those within reach, the evidence decides, and the person-box hint only lowers
    parked = vehicle_at(NEAR_BOX, "standing", "parked-candidate")
    hinted = vehicle_at(NEAR_BOX, "standing", "occupied")
    assert choose_vehicle([hinted, near_unknown, parked]) is parked
    assert choose_vehicle([hinted, near_unknown]) is near_unknown
    assert choose_vehicle([hinted]) is hinted  # lowered, and still taken under allow
    assert choose_vehicle([hinted], "avoid") is None  # and passed over under avoid


def test_a_new_nearer_vehicle_does_not_steal_an_approach_already_in_progress():
    """A world seen in perspective: the figure stands, then walks to the far car seen standing. A quad
    (a motorcycle here, to tell them apart) comes into view beside the path. Only the initial choice
    ranks both: a target already being approached is kept until lost or unreachable."""

    def box(z, x, kind, width, height):
        h, w = height * 0.9 / z, width * 0.9 / z
        cx, y1 = 0.5 + 0.9 * x / z, 0.43 + 1.6 * 0.9 / z
        if not 0 <= cx - w / 2 < cx + w / 2 <= 1 or y1 > 1:
            return None
        return Detection(kind, px(cx - w / 2, y1 - h, cx + w / 2, y1), 0.95)

    for appears in (0.0, 0.5, 1.0, 2.0):
        skill = EnterVehicle({})
        far_z, far_x, quad_z, quad_x = 16.0, 1.0, 7.0, -0.8
        taken = None
        for tick in range(400):
            t = tick * 0.05
            seen = [box(far_z, far_x, "car", 2.0, 1.5)]
            if t >= appears:
                seen.append(box(quad_z, quad_x, "motorcycle", 1.2, 1.0))
            result = skill.step(obs(t, tuple(d for d in seen if d is not None)))
            if "triangle" in result.pad.buttons:
                taken = skill.entry_target.obj.kind
                break
            step = max(0.0, -result.pad.left[1]) * 1.6 * 0.05
            far_z, quad_z = far_z - step, quad_z - step
            far_x, quad_x = far_x - result.pad.left[0] * 1.6 * 0.05, quad_x - result.pad.left[0] * 1.6 * 0.05
        assert taken == ("motorcycle" if appears == 0 else "car"), appears


def test_occupant_confirmation_survives_one_pixel_box_jitter_but_not_a_pedestrian():
    # Actual first three pickup samples: the occupant's right edge exceeds
    # the next vehicle box by one pixel. That is detector jitter, not absence.
    runs = json.loads((Path(__file__).resolve().parents[2] / "lab/enter/runs-console.json").read_text())[
        "runs"
    ]
    run = next(r for r in runs if r["session"].endswith("122312"))
    samples = [s for s in run["samples"] if s["skill"][0] == "enter_vehicle"]
    skill = EnterVehicle({})
    for sample in samples[:8]:
        assert "triangle" not in skill.step(recorded_observation(sample)).pad.buttons
    assert any(v.occupancy == "occupied" for v in skill.vehicles)
    from pilot.vehicle_entry import occupant_visible

    car = replace(NEAR, box=(0.3, 0.45, 0.7, 0.9))
    pedestrian = Detection("person", px(0.4, 0.3, 0.6, 0.95), 0.99)
    assert not occupant_visible(car, (pedestrian,))


def test_recorded_quad_and_pickup_wait_for_player_evidence():
    runs = json.loads((Path(__file__).resolve().parents[2] / "lab/enter/runs-console.json").read_text())[
        "runs"
    ]
    for run in runs[:2]:
        skill = EnterVehicle({})
        samples = [sample for sample in run["samples"] if sample["skill"][0] == "enter_vehicle"]
        assert samples
        for sample in samples:
            assert "triangle" not in skill.step(recorded_observation(sample)).pad.buttons


def test_model_leaves_lane_before_waiting_for_an_occupied_vehicle():
    game = EntryGame(distance=1, road_x=0, driver=True)
    result, game, presses = play(game, duration=6)
    assert not presses and not game.driver_out
    assert abs(game.road_x) >= 7
    assert game.longest_lane_idle < 1.5
    assert result.status == "failed" and result.pad == NEUTRAL_PAD


def test_model_ineffective_press_in_lane_retreats_without_seven_second_wait():
    game = EntryGame(distance=1, road_x=0, locked=True)
    result, game, presses = play(game, duration=6)
    assert presses and abs(game.road_x) >= 7
    assert game.longest_lane_idle < 1.5
    assert "retreated" in result.reason


def test_allow_is_explicit_and_driver_can_get_out_after_success():
    game = EntryGame(distance=1, road_x=12, driver=True)
    skill = EnterVehicle({"occupied": "allow"})
    for tick in range(80):
        t = tick / 10
        result = skill.step(game.observation(t))
        game.apply(t, result.pad)
        if result.status == "done":
            break
    assert result.status == "done" and "occupancy=occupied" in result.reason
    game.observation(t + 3)
    assert game.driver_out and not game.seated


@pytest.mark.parametrize("speed, moving", [(0.25, True), (0.12, False)])
def test_traffic_alone_ends_the_try_without_chasing(speed, moving):
    """Passing traffic is waited for locally, then the bounded try returns to the trip."""
    from test_foot import road_frame

    skill = EnterVehicle({})
    for tick in range(60):
        t = tick / 10
        x = 0.02 + t * speed
        objects = (Detection("car", px(x, 0.35, x + 0.1, 0.45), 0.9),) if x + 0.1 <= 1 else ()
        result = skill.step(replace(obs(t, objects), frame=road_frame(-12)))
        assert "triangle" not in result.pad.buttons
        assert result.pad.left == (0, 0)
        if result.status != "running":
            break
    assert result.status == "failed" and t <= 4.1
    assert any(v.moved for v in skill.ever) is moving


def test_head_accepts_occupancy_argument_and_the_schema_offers_it():
    from pilot.head import parse_response, response_schema

    answer = parse_response(
        {
            "plan": [{"name": "enter_vehicle", "args": {"occupied": "avoid"}}],
            "sentence": "Leave a car with a driver.",
        }
    )
    assert answer.plan[0].args["occupied"] == "avoid"
    with pytest.raises(ValueError):
        parse_response({"plan": [{"name": "enter_vehicle", "args": {"occupied": "yes"}}], "sentence": "x"})
    variant = next(
        v
        for v in response_schema()["properties"]["plan"]["items"]["anyOf"]
        if v["properties"]["name"]["enum"] == ["enter_vehicle"]
    )
    assert variant["properties"]["args"]["properties"]["occupied"] == {
        "type": "string",
        "enum": ["allow", "avoid"],
    }


# ------------------------------------------- a map that cannot tell the side never stops the search
def run_game(game, duration=MAX_SECONDS, **args):
    """Like play(), keeping every tick: (result, game, presses, [(time, result), ...])."""
    skill = EnterVehicle({"duration": duration, **args})
    ticks, presses, held = [], [], False
    for tick in range(int(duration * 10) + 2):
        time = tick / 10
        result = skill.step(game.observation(time))
        ticks.append((time, result))
        if "triangle" in result.pad.buttons and not held:
            presses.append(time)
        held = "triangle" in result.pad.buttons
        game.apply(time, result.pad)
        if result.status != "running":
            break
    return result, game, presses, ticks


def longest_idle(ticks, after=0.0):
    """Seconds of the longest run of ticks on which the figure stands with the camera still."""
    longest = start = None
    for time, result in ticks:
        if time >= after and result.status == "running" and result.pad == NEUTRAL_PAD:
            start = time if start is None else start
            longest = max(longest or 0.0, time - start)
        else:
            start = None
    return longest or 0.0


def test_a_locked_car_does_not_hold_the_search_when_the_map_cannot_tell_the_side():
    # A thin road line: the map shows a road and not which side of it the figure is on.
    result, _game, presses, ticks = run_game(EntryGame(distance=1, road_x=20, locked=True, road_width=3))
    assert len(presses) == 1 and result.status == "failed"
    assert result.reason.startswith("door locked or blocked")
    assert "saw 1 vehicle (rejected 1, avoided 0, moving 0)" in result.reason
    assert ticks[-1][0] - presses[0] <= 4
    assert ticks[-1][1].pad == NEUTRAL_PAD


def test_a_driver_seen_is_passed_over_and_the_search_goes_on_when_the_map_cannot_tell():
    result, game, presses, ticks = run_game(
        EntryGame(distance=1, road_x=20, driver=True, road_width=3), duration=20
    )
    assert not presses and result.status == "failed" and not game.driver_out
    assert "saw 1 vehicle (rejected 0, avoided 1, moving 0)" in result.reason
    assert ticks[-1][0] <= 4.1
    assert all(r.pad.left == (0, 0) for _, r in ticks)


def test_the_same_driver_is_taken_when_the_rules_allow_it():
    result, _game, presses, _ticks = run_game(
        EntryGame(distance=1, road_x=20, driver=True, road_width=3), occupied="allow"
    )
    assert presses and result.status == "done" and "occupancy=occupied" in result.reason


def test_a_retreat_from_a_lane_ends_when_the_map_stops_saying_lane():
    game = EntryGame(distance=1, road_x=0, locked=True)  # a band the edges can be read on, the figure in it
    skill = EnterVehicle({})
    for tick in range(200):
        time = tick / 10
        result = skill.step(game.observation(time))
        game.apply(time, result.pad)
        if skill.retreating:
            break
    assert skill.retreating and result.reason == "leaving lane"
    game.road_width = 3  # from here the map cannot be read
    result = skill.step(game.observation(time + 0.1))
    assert not skill.retreating and result.reason != "leaving lane"


def test_parked_is_claimed_only_for_a_vehicle_seen_standing_with_no_person_box():
    inside = Detection("person", px(0.47, 0.43, 0.53, 0.47), 0.9)

    def run(hint_at):
        skill = EnterVehicle({})
        claims = {}
        for tick in range(30):
            time = tick * 0.05
            objects = (FAR, inside) if time in hint_at else (FAR,)
            skill.step(obs(time, objects))
            claims[round(time, 2)] = skill.ever[0].occupancy
        return claims

    clear = run(hint_at=())
    assert clear[0.35] == "unknown" and clear[0.45] == "parked-candidate"
    # One detection of a person box inside, 0.2 s in: no driver is confirmed (that takes 0.1 s of them), and
    # still the car is not called parked for a span that had a person box in it.
    hinted = run(hint_at=(0.2,))
    assert hinted[0.45] == "unknown" and hinted[0.75] == "unknown"
    assert hinted[0.85] == "parked-candidate"  # a clear span of 0.4 s after the hint, and only then
