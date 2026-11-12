"""Approach visible vehicles, retry entry, and confirm the seat from the map."""

import math
from dataclasses import dataclass, replace
from typing import ClassVar

from pilot.contract import FRAME_SIZE, Detection, Observation, Pad, SkillResult, player_mode
from pilot.foot import WalkRoad
from pilot.profile import active

WIDTH, HEIGHT = FRAME_SIZE
MAX_SECONDS = 45.0
PRESS_SECONDS = 0.15
DETECTION_MAX_AGE = 0.5
# The on-foot reader produces false vehicle readings lasting up to 0.83 seconds.
CONFIRM_SECONDS = 1.0
ALREADY_SECONDS = 2.0
SCAN_SECONDS = 1.4
DELIVERY_WAIT = 5.0
TARGET_GRACE = 1.0
MIN_CONFIDENCE = 0.45
TARGET_GATE = 0.18
# Provisional image-space reach, checked against the recorded first presses, not live success.
REACH_HEIGHT = 0.19
REACH_BOTTOM = 0.61
# Kerim's entry latency p90 is 5.3 s; leave another second for seated proof.
DOOR_WAIT = 7.0
BUS_DOOR_WAIT = 13.0  # Recorded bus entry took 11.6 s before the seated event.
RETRY_APPROACH = 0.8
MAX_ATTEMPTS = 4


def center(obj):
    x0, y0, x1, y1 = obj.box
    return (x0 + x1) / 2, (y0 + y1) / 2


def within_reach(obj):
    x, _ = center(obj)
    _, y0, _, y1 = obj.box
    size = 1.5 if obj.kind in {"bus", "truck"} else 1.0
    return abs(x - 0.5) <= 0.45 and (y1 >= REACH_BOTTOM or (y1 - y0) / size >= REACH_HEIGHT)


def approach(obj, retry=False):
    """Steer the figure and camera together; off-centre cars never require a stationary turn."""
    error = center(obj)[0] - 0.5
    speed = 0.45 if within_reach(obj) else 0.85
    lateral = max(-0.65, min(0.65, error * 1.8))
    if retry and abs(lateral) < 0.15:
        lateral = 0.30  # A second angle avoids continually pushing into the same bumper.
    return Pad(left=(lateral, -speed), right=(max(-0.15, min(0.15, error * 0.25)), 0.0))


@dataclass
class Vehicle:
    obj: Detection
    seen: float
    anchor: Detection
    anchor_time: float
    motion: str = "unknown"
    tries: int = 0
    rejected: bool = False


def choose_vehicle(vehicles):
    """Prefer a vehicle seen to stand, then one within reach, then a car before a bus, then the nearer."""

    def rank(vehicle):
        obj = vehicle.obj
        _, y0, _, y1 = obj.box
        size = 1.5 if obj.kind in {"bus", "truck"} else 1.0
        proximity = y1 + (y1 - y0) / size * 0.5
        return (
            {"standing": 2, "unknown": 1, "moving": 0}[vehicle.motion],
            within_reach(obj),
            obj.kind in {"car", "motorcycle"},
            proximity - abs(center(obj)[0] - 0.5) * 0.1,
        )

    return max((v for v in vehicles if not v.rejected), key=rank, default=None)


class EnterVehicle:
    name = "enter_vehicle"
    # Protect approach as well: a plan arriving just before the release tick must not replace it.
    uninterruptible = True
    parameters: ClassVar[dict] = {
        "duration": (0.1, MAX_SECONDS, MAX_SECONDS),
        "kind": ("any", "car", "motorcycle"),
    }
    prompt = (
        "Find and enter a reachable vehicle (kind any/car/motorcycle; duration up to 45). "
        "Needs fresh detections; searches along a visible road if none are nearby. "
        "Approaches even with a damaged map, waits neutrally after pressing, and succeeds "
        "only on sustained seated proof. Fails for missing detections, no vehicle, lost "
        "target, unreachable vehicle, or a locked/blocked door."
    )

    def __init__(self, args: dict):
        self.profile = active()
        if not isinstance(args, dict) or set(args) - self.parameters.keys():
            raise ValueError("unknown enter_vehicle arguments")
        duration = args.get("duration", MAX_SECONDS)
        if (
            isinstance(duration, bool)
            or not isinstance(duration, (int, float))
            or not math.isfinite(duration)
        ):
            raise ValueError("duration must be a finite number")
        self.limit = min(MAX_SECONDS, max(0.1, duration))
        self.kind = args.get("kind", "any")
        if self.kind not in self.parameters["kind"]:
            raise ValueError("kind must be any, car, or motorcycle")
        self.started = self.last_time = self.capture = None
        self.finished = self.target = None
        self.entry_target = None
        self.vehicles = []
        self.saw_delivery = self.saw_target = False
        self.confirmed_since = None
        self.phase = "approach"
        self.phase_since = None
        self.attempts = 0
        self.retry_walk = 0.0
        self.was_walking = False
        self.previous_pad = Pad()
        self.last_problem = None
        self.road = None
        self.road_problem = None
        self.walk_pad = None
        self.walk_time = None

    def stop(self, reason="interrupted") -> SkillResult:
        if self.road is not None:
            self.road.stop(reason)
        self.finished = SkillResult(status="failed", reason=reason)
        return self.finished

    def _timeout_reason(self):
        if not self.saw_delivery:
            return "no detections delivered at all"
        if self.last_problem:
            return self.last_problem
        if self.saw_target:
            return "vehicle out of reach"
        if self.road_problem:
            return f"nothing found; road search unavailable: {self.road_problem}"
        return "nothing found"

    def _candidates(self, obs):
        kinds = {"car", "truck", "bus", "motorcycle"} if self.kind == "any" else {self.kind}
        result = []
        for obj in obs.objects:
            if obj.kind not in kinds or not math.isfinite(obj.confidence) or obj.confidence < MIN_CONFIDENCE:
                continue
            if len(obj.box) != 4 or not all(math.isfinite(v) for v in obj.box):
                continue
            x0, y0, x1, y1 = obj.box
            box = (x0 / WIDTH, y0 / HEIGHT, x1 / WIDTH, y1 / HEIGHT)
            if 0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1:
                result.append(replace(obj, box=box))
        return result

    def _observe(self, obs):
        if obs.objects_time == self.capture:
            return
        self.capture = obs.objects_time
        unmatched = list(self.vehicles)
        visible = []
        candidates = self._candidates(obs)
        pairs = []
        for index, obj in enumerate(candidates):
            for old, vehicle in enumerate(self.vehicles):
                ratio = (obj.box[3] - obj.box[1]) / (vehicle.obj.box[3] - vehicle.obj.box[1])
                distance = math.dist(center(vehicle.obj), center(obj))
                gate = min(TARGET_GATE, max(0.05, (vehicle.obj.box[2] - vehicle.obj.box[0]) * 0.6))
                if obj.kind == vehicle.obj.kind and distance <= gate and 0.55 <= ratio <= 1.8:
                    pairs.append((distance + 0.05 * abs(math.log(ratio)), index, old))
        assigned, used = {}, set()
        for _, index, old in sorted(pairs):
            if index not in assigned and old not in used:
                assigned[index] = self.vehicles[old]
                used.add(old)
        for index, obj in enumerate(candidates):
            vehicle = assigned.get(index)
            if vehicle is None:
                vehicle = Vehicle(obj, obs.time, obj, self.capture)
            else:
                unmatched.remove(vehicle)
                span = self.capture - vehicle.anchor_time
                if span >= 0.4:
                    # Large camera turns make box displacement ambiguous; do not call it traffic.
                    if abs(self.previous_pad.right[0]) < 0.08:
                        drift = math.dist(center(obj), center(vehicle.anchor)) / span
                        scale = (obj.box[3] - obj.box[1]) / (vehicle.anchor.box[3] - vehicle.anchor.box[1])
                        if drift > 0.16 or scale < 0.75:
                            vehicle.motion = "moving"
                        elif drift < 0.06 and 0.85 <= scale <= 1.20:
                            vehicle.motion = "standing"
                        else:
                            vehicle.motion = "unknown"
                    vehicle.anchor, vehicle.anchor_time = obj, self.capture
                vehicle.obj, vehicle.seen = obj, obs.time
            visible.append(vehicle)
        self.vehicles = visible + [v for v in unmatched if obs.time - v.seen <= TARGET_GRACE]
        best = choose_vehicle(visible)
        if self.phase == "wait":
            return
        if self.target is None or self.target.rejected or obs.time - self.target.seen > TARGET_GRACE:
            self.target = best
            if best is not None:
                self.last_problem = None
        elif best is not None and self.target.motion == "moving" and best.motion != "moving":
            self.target = best
        if self.target is not None and not self.target.rejected and self.road is not None:
            self.road.stop("vehicle found")
            self.road = None
            self.road_problem = None

    def _search(self, obs, elapsed):
        if elapsed < SCAN_SECONDS:
            return SkillResult(Pad(right=(0.4 if elapsed < SCAN_SECONDS / 2 else -0.4, 0.0)))
        if self.road is None:
            self.road = WalkRoad({"duration": min(30.0, self.limit - elapsed), "sprint": False})
        result = self.road.step(obs)
        if result.status != "running":
            self.road_problem = result.reason if result.status == "failed" else None
            self.road = None
            return SkillResult()
        return result

    def step(self, observation: Observation) -> SkillResult:
        if self.finished is not None:
            return self.finished
        try:
            result = self._step(observation)
            self.previous_pad = result.pad
            return result
        except Exception:
            return self.stop("invalid observation")

    def _step(self, obs):
        now = obs.time
        if not math.isfinite(now) or (self.last_time is not None and now < self.last_time):
            return self.stop("invalid observation time")
        if self.phase == "retry" and self.was_walking and self.last_time is not None:
            self.retry_walk += min(DETECTION_MAX_AGE, now - self.last_time)
        self.was_walking = False
        self.last_time = now
        if self.started is None:
            self.started = now
        elapsed = now - self.started
        if elapsed >= self.limit:
            return self.stop(self._timeout_reason())
        if not obs.reading.corrupt and player_mode(obs) == "none":
            return SkillResult()
        if self.phase == "wait" and now - self.phase_since < PRESS_SECONDS:
            return SkillResult(Pad(buttons=(self.profile.enter_vehicle,)))
        if not obs.reading.corrupt and player_mode(obs) == "vehicle":
            if self.confirmed_since is None:
                self.confirmed_since = now
            needed = CONFIRM_SECONDS if self.attempts else ALREADY_SECONDS
            if now - self.confirmed_since >= needed:
                self.finished = SkillResult(
                    status="done", reason="entered vehicle" if self.attempts else "already in a vehicle"
                )
                return self.finished
            return SkillResult()
        if obs.reading.corrupt and self.confirmed_since is not None:
            return SkillResult()
        self.confirmed_since = None
        fresh = (
            obs.objects_time is not None
            and math.isfinite(obs.objects_time)
            and 0 <= now - obs.objects_time <= DETECTION_MAX_AGE
        )
        if fresh:
            self.saw_delivery = True
            self._observe(obs)
        if self.phase == "wait":
            wait = BUS_DOOR_WAIT if self.entry_target.obj.kind == "bus" else DOOR_WAIT
            if now - self.phase_since < wait:
                return SkillResult()
            if not fresh:
                if now - self.phase_since >= wait + DELIVERY_WAIT:
                    return self.stop("detections lost after entry press")
                return SkillResult()
            attempted = self.entry_target
            if attempted is None or now - attempted.seen > TARGET_GRACE:
                self.last_problem = "vehicle drove away or was lost"
            elif not within_reach(attempted.obj):
                self.last_problem = "vehicle out of reach"
            elif attempted.tries >= 3:
                self.last_problem = "door locked or blocked"
                attempted.rejected = True
            else:
                self.last_problem = "entry press had no effect"
            if self.attempts >= MAX_ATTEMPTS:
                return self.stop(self.last_problem)
            self.phase = "retry"
            self.retry_walk = 0.0
        if not fresh:
            if not self.saw_delivery and elapsed >= DELIVERY_WAIT:
                return self.stop("no detections delivered at all")
            return SkillResult()
        if self.target is None or self.target.rejected or now - self.target.seen > TARGET_GRACE:
            if self.saw_target and self.last_problem is None:
                self.last_problem = "vehicle drove away or was lost"
            self.phase = "approach"
            return self._search(obs, elapsed)
        if self.target.seen != now:
            # Detections come twenty times a second and ticks thirty: on a tick between two of
            # them the walk goes on as it was, or every third tick would let the stick go.
            if self.walk_pad is not None and now - self.walk_time <= 0.15:
                self.was_walking = True
                return SkillResult(self.walk_pad)
            return SkillResult()
        self.saw_target = True
        self.walk_pad = None
        if self.phase == "tap":
            if not within_reach(self.target.obj):
                self.phase = "approach"
                self.was_walking = True
                return SkillResult(approach(self.target.obj))
            self.attempts += 1
            self.target.tries += 1
            self.entry_target = self.target
            self.phase, self.phase_since = "wait", now
            return SkillResult(Pad(buttons=(self.profile.enter_vehicle,)))
        ready = self.phase != "retry" or self.retry_walk >= RETRY_APPROACH
        if within_reach(self.target.obj) and ready:
            self.phase = "tap"
            return SkillResult()
        self.was_walking = True
        self.walk_pad, self.walk_time = approach(self.target.obj, retry=self.phase == "retry"), now
        return SkillResult(self.walk_pad)
