"""Approach visible vehicles, retry entry, and confirm the seat from the map."""

import math
from dataclasses import dataclass, replace
from typing import ClassVar

from pilot.contract import FRAME_SIZE, Detection, Observation, Pad, SkillResult, player_mode
from pilot.foot import WalkRoad, road_position, stick_for
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
LANE_WAIT = 1.0  # No seven-second door wait with sustained on-foot proof in a lane.
HOLD_SECONDS = 3.0  # Longest the search stands still for one vehicle it may still take and cannot yet judge.


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
    occupancy: str = "unknown"  # unknown | parked-candidate | occupied
    driver_since: float | None = None
    last_hint: float | None = None  # capture time of the last person box inside this vehicle's
    stood_clear: bool = False  # seen standing for a whole span of 0.4 s with no person box in it
    moved: bool = False
    held: float = 0.0  # seconds the search has stood still for this vehicle


def occupant_visible(obj, objects):
    """A contained upper-body box is positive evidence; absent boxes prove nothing.

    Full containment rejects Trevor and most pedestrians beside a car. Lights
    are deliberately not used: parked vehicles can have lights on too.
    """
    x0, y0, x1, y1 = obj.box
    for person in objects:
        if person.kind != "person" or person.confidence < MIN_CONFIDENCE:
            continue
        a, b, c, d = person.box
        a, b, c, d = a / WIDTH, b / HEIGHT, c / WIDTH, d / HEIGHT
        if (
            x0 - 0.003 <= a < c <= x1 + 0.003
            and y0 - 0.003 <= b < d <= y1 + 0.003
            and b < y0 + (y1 - y0) * 0.55
        ):
            return True
    return False


def choose_vehicle(vehicles, occupied="allow"):
    """A vehicle seen moving comes last. Of the others one within reach comes before one that is not,
    and only then standing or parked evidence, a car before a bus, and the nearer. The person-box hint
    lowers a vehicle (evidence) and under occupied=avoid takes it out; it decides nothing else."""

    def rank(vehicle):
        obj = vehicle.obj
        _, y0, _, y1 = obj.box
        size = 1.5 if obj.kind in {"bus", "truck"} else 1.0
        proximity = y1 + (y1 - y0) / size * 0.5
        return (
            vehicle.motion != "moving" and not vehicle.moved,
            within_reach(obj),
            {"parked-candidate": 2, "unknown": 1, "occupied": 0}[vehicle.occupancy],
            {"standing": 2, "unknown": 1, "moving": 0}[vehicle.motion],
            obj.kind in {"car", "motorcycle"},
            proximity - abs(center(obj)[0] - 0.5) * 0.1,
        )

    return max(
        (v for v in vehicles if not v.rejected and (occupied == "allow" or v.occupancy != "occupied")),
        key=rank,
        default=None,
    )


class EnterVehicle:
    name = "enter_vehicle"
    # Protect approach as well: a plan arriving just before the release tick must not replace it.
    uninterruptible = True
    parameters: ClassVar[dict] = {
        "duration": (0.1, MAX_SECONDS, MAX_SECONDS),
        "kind": ("any", "car", "motorcycle"),
        "occupied": ("avoid", "allow"),
        "traffic": (False, True),
    }
    prompt = (
        "Enter a reachable vehicle, parked candidates first. occupied=avoid skips seen drivers; "
        "allow permits them. traffic=true waits at the road for a stopped reachable car or "
        "motorcycle and allows drivers by default, excluding buses/trucks. After a traffic "
        "timeout walk along the road before waiting again. Only sustained seated proof succeeds."
    )

    def __init__(self, args: dict):
        self.profile = active()
        if not isinstance(args, dict) or set(args) - self.parameters.keys():
            raise ValueError("unknown enter_vehicle arguments")
        self.traffic = args.get("traffic", False)
        if not isinstance(self.traffic, bool):
            raise ValueError("traffic must be true or false")
        self.door_target = None
        self.door_since = None
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
        self.occupied = args.get("occupied", "allow" if self.traffic else "avoid")
        if self.occupied not in self.parameters["occupied"]:
            raise ValueError("occupied must be avoid or allow")
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
        self.location = None
        self.lane_since = None
        self.retreating = False
        self.taken_kind = None
        self.taken_vehicle = None
        self.ever = []  # every vehicle tracked, for the account when time runs out
        self.gap = 0.0

    def stop(self, reason="interrupted") -> SkillResult:
        if self.road is not None:
            self.road.stop(reason)
        self.finished = SkillResult(status="failed", reason=reason)
        return self.finished

    def _timeout_reason(self):
        if self.traffic:
            detail = self.last_problem or "nothing found; no stopped reachable car or motorcycle"
            return detail + "; traffic wait ended" + self._saw()
        if not self.saw_delivery:
            return "no detections delivered at all"
        if self.last_problem:
            reason = self.last_problem
        elif self.saw_target:
            reason = "vehicle out of reach"
        elif self.road_problem:
            reason = f"nothing found; road search unavailable: {self.road_problem}"
        else:
            reason = "nothing found"
        return reason + self._saw()

    def _saw(self):
        """What the run saw, so that whoever plans next knows why nothing was taken."""
        if not self.ever:
            return ""
        rejected = sum(v.rejected for v in self.ever)
        moving = sum(not v.rejected and (v.moved or v.motion == "moving") for v in self.ever)
        avoided = sum(
            not v.rejected
            and not (v.moved or v.motion == "moving")
            and v.occupancy == "occupied"
            and self.occupied == "avoid"
            for v in self.ever
        )
        noun = "vehicle" if len(self.ever) == 1 else "vehicles"
        return f"; saw {len(self.ever)} {noun} (rejected {rejected}, avoided {avoided}, moving {moving})"

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
        previous_capture = self.capture
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
            # A person box inside the vehicle's is a hint, not proof: it lowers the vehicle in the ranking
            # and, seen for 0.1 s, makes occupied=avoid pass it over. It is never the only reason to stand
            # and wait; the detector misses many drivers, so no hint is not "empty" either.
            hint = occupant_visible(obj, obs.objects)
            if vehicle is None:
                vehicle = Vehicle(obj, obs.time, obj, self.capture)
                self.ever.append(vehicle)
                if hint:
                    vehicle.last_hint = self.capture
            else:
                unmatched.remove(vehicle)
                if hint:
                    vehicle.last_hint = self.capture
                # A stopped target can pull away between the slower motion windows.
                # Any new displacement cancels the traffic approach immediately; movement
                # caused by our own approach is ambiguous and must settle again as well.
                if self.traffic and previous_capture is not None:
                    sample_span = self.capture - previous_capture
                    if sample_span > 0:
                        drift = math.dist(center(obj), center(vehicle.obj)) / sample_span
                        scale = (obj.box[3] - obj.box[1]) / (vehicle.obj.box[3] - vehicle.obj.box[1])
                        if drift > 0.16 or not 0.85 <= scale <= 1.20:
                            vehicle.motion = "moving" if self.previous_pad.left == (0, 0) else "unknown"
                            vehicle.moved |= vehicle.motion == "moving"
                            vehicle.anchor, vehicle.anchor_time = obj, self.capture
                span = self.capture - vehicle.anchor_time
                if span >= 0.4:
                    # Large camera turns make box displacement ambiguous; do not call it traffic.
                    if abs(self.previous_pad.right[0]) < 0.08:
                        drift = math.dist(center(obj), center(vehicle.anchor)) / span
                        scale = (obj.box[3] - obj.box[1]) / (vehicle.anchor.box[3] - vehicle.anchor.box[1])
                        if drift > 0.16 or scale < 0.75:
                            vehicle.motion = "moving" if self.previous_pad.left == (0, 0) else "unknown"
                            vehicle.moved |= vehicle.motion == "moving"
                        elif drift < 0.06 and 0.85 <= scale <= 1.20:
                            vehicle.motion = "standing"
                            if vehicle.last_hint is None or vehicle.last_hint < vehicle.anchor_time:
                                vehicle.stood_clear = True
                        else:
                            vehicle.motion = "unknown"
                    vehicle.anchor, vehicle.anchor_time = obj, self.capture
                vehicle.obj, vehicle.seen = obj, obs.time
            if hint:
                if vehicle.driver_since is None:
                    vehicle.driver_since = obs.time
                if obs.time - vehicle.driver_since >= 0.1:
                    vehicle.occupancy = "occupied"
            else:
                vehicle.driver_since = None
            if vehicle.moved:
                vehicle.occupancy = "occupied"  # stopped traffic, not evidence of parking
            elif vehicle.occupancy != "occupied" and vehicle.stood_clear:
                vehicle.occupancy = "parked-candidate"
            visible.append(vehicle)
        self.vehicles = visible + [v for v in unmatched if obs.time - v.seen <= TARGET_GRACE]
        if self.phase == "wait":
            return
        best = choose_vehicle([v for v in visible if self._eligible(v)], self.occupied)
        current = self.target
        if (
            current is None
            or current.rejected
            or obs.time - current.seen > TARGET_GRACE
            or not self._eligible(current)
        ):
            self.target = best
            if best is not None:
                self.last_problem = None
        elif best is not None and choose_vehicle([current, best], self.occupied) is best:
            self.target = best
        if self.target is not None and not self.target.rejected and self.road is not None:
            self.road.stop("vehicle found")
            self.road = None
            self.road_problem = None

    def _search(self, obs, elapsed):
        if self.traffic:
            self.door_target = None
            return SkillResult()
        if self._in_lane():
            return self._retreat()
        # Stand still only for a vehicle that may still be taken and is not yet seen clearly, and for
        # HOLD_SECONDS at most per vehicle. A moving, locked or avoided one holds nothing: look on.
        holding = [v for v in self.vehicles if self._may_take(v) and v.held < HOLD_SECONDS]
        if holding:
            for vehicle in holding:
                vehicle.held += self.gap
            return SkillResult(reason=f"waiting to see a {holding[0].obj.kind} clearly")
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

    def _in_lane(self):
        return self.location is not None and self.location.position == "lane"

    def _at_side(self):
        return self.location is not None and self.location.position == "side"

    def _may_take(self, vehicle):
        """Not rejected, not moving now, and not one that occupied=avoid passes over."""
        return not (
            vehicle.rejected
            or vehicle.motion == "moving"
            or (vehicle.occupancy == "occupied" and self.occupied == "avoid")
        )

    def _eligible(self, vehicle):
        if self.traffic and vehicle is not None and vehicle.obj.kind not in {"car", "motorcycle"}:
            return False
        if vehicle is None or not self._may_take(vehicle):
            return False
        if vehicle.driver_since is not None and vehicle.occupancy != "occupied":
            return False  # a person box was just seen inside: the next detection says if it stays
        if self.traffic:
            return (
                vehicle.obj.kind in {"car", "motorcycle"}
                and vehicle.motion == "standing"
                and within_reach(vehicle.obj)
                and (self._at_side() or self._in_lane())
            )
        if self._in_lane():
            return vehicle.motion == "standing" and vehicle.occupancy != "occupied"
        if self._at_side() and not within_reach(vehicle.obj) and vehicle.motion != "standing":
            return False
        return True

    def _retreat(self):
        """Out of the carriageway toward its nearer edge; only on a lane reading, which has the edge."""
        if not self._in_lane() or self.location.outward is None:
            return SkillResult()
        return SkillResult(Pad(left=stick_for(self.location.outward, 0.85)), reason="leaving lane")

    def step(self, observation: Observation) -> SkillResult:
        if self.finished is not None:
            return self.finished
        try:
            result = self._step(observation)
            if self.traffic and result.status == "failed" and "; traffic wait ended" not in result.reason:
                result = replace(result, reason=result.reason + "; traffic wait ended")
                self.finished = result
            self.previous_pad = result.pad
            return result
        except Exception:
            return self.stop("invalid observation")

    def _step(self, obs):
        now = obs.time
        if not math.isfinite(now) or (self.last_time is not None and now < self.last_time):
            return self.stop("invalid observation time")
        self.gap = 0.0 if self.last_time is None else min(DETECTION_MAX_AGE, now - self.last_time)
        if self.phase == "retry" and self.was_walking and self.last_time is not None:
            self.retry_walk += min(DETECTION_MAX_AGE, now - self.last_time)
        self.was_walking = False
        self.last_time = now
        if self.started is None:
            self.started = now
        elapsed = now - self.started
        if elapsed >= self.limit:
            reason = self._timeout_reason()
            location = road_position(obs)
            if location is not None and location.position == "lane":
                reason += "; still-in-lane"
            return self.stop(reason)
        if self.traffic and obs.reading.corrupt:
            self.confirmed_since = None
            return SkillResult()
        fresh = (
            obs.objects_time is not None
            and math.isfinite(obs.objects_time)
            and 0 <= now - obs.objects_time <= DETECTION_MAX_AGE
        )
        standing = fresh and obs.figure is not None and obs.figure.kind == "person"
        # A sound tilted map with a route says seated, whatever the judge says: in the eight sessions of
        # 13 November that were on foot throughout, 44,000 ticks, the map was read so not once.
        seated = (
            not obs.reading.corrupt
            and obs.reading.confidence >= 0.45
            and obs.reading.minimap == "tilted"
            and obs.reading.route in {"yellow", "purple"}
            and not standing
        )
        if not obs.reading.corrupt and player_mode(obs) in {"none", "unknown"} and not seated:
            return SkillResult()
        if seated or (not obs.reading.corrupt and player_mode(obs) == "vehicle"):
            if self.confirmed_since is None:
                self.confirmed_since = now
            needed = CONFIRM_SECONDS if self.attempts else ALREADY_SECONDS
            if now - self.confirmed_since >= needed:
                self.finished = SkillResult(
                    status="done",
                    reason=(
                        f"entered vehicle; vehicle={self.taken_vehicle}; occupancy={self.taken_kind}; "
                        f"road={self.location.position if self.location else 'unknown'}"
                    )
                    if self.attempts
                    else "already in a vehicle",
                )
                return self.finished
            return SkillResult()
        if self.traffic and not fresh:
            return SkillResult()
        if self.phase == "wait" and now - self.phase_since < PRESS_SECONDS:
            return SkillResult(Pad(buttons=(self.profile.enter_vehicle,)))
        if obs.reading.corrupt and self.confirmed_since is not None:
            return SkillResult()
        self.confirmed_since = None
        self.location = road_position(obs)
        in_lane = self.location is not None and self.location.position == "lane"
        if in_lane:
            if self.lane_since is None:
                self.lane_since = now
        else:
            self.lane_since = None
        fresh = (
            obs.objects_time is not None
            and math.isfinite(obs.objects_time)
            and 0 <= now - obs.objects_time <= DETECTION_MAX_AGE
        )
        if fresh:
            self.saw_delivery = True
            self._observe(obs)
        if self.retreating:
            if in_lane:
                return self._retreat()
            # At the side, or the map says nothing: a retreat needs a lane reading, without one it is over.
            self.retreating = False
            self.phase = "approach"
        if self.phase == "wait" and in_lane and self.lane_since is not None and not self.traffic:
            if now - max(self.phase_since, self.lane_since) >= LANE_WAIT:
                self.last_problem = "entry unconfirmed in lane; retreated"
                self.entry_target.rejected = True
                self.target = None
                self.retreating = True
                self.phase = "approach"
                return self._retreat()
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
            return self._retreat() if in_lane else SkillResult()
        if self.target is None or self.target.rejected or now - self.target.seen > TARGET_GRACE:
            if self.saw_target and self.last_problem is None:
                self.last_problem = "vehicle drove away or was lost"
            self.phase = "approach"
            return self._search(obs, elapsed)
        if not self._eligible(self.target):
            self.phase = "approach"
            self.walk_pad = None
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
        if self.traffic and self.door_target is not self.target:
            self.phase = "approach"
        if self.traffic and self.phase != "tap":
            if self.door_target is not self.target:
                self.door_target, self.door_since = self.target, now
            if now - self.door_since < 0.3:
                # The detector has no door keypoint. A short side approach uses the
                # same bounded correction as an entry retry, only beside stopped traffic.
                return SkillResult(approach(self.target.obj, retry=True))
        if self.phase == "tap":
            # A vehicle box also surrounds the player's own car. A press needs the figure on foot:
            # the judge's word, which no longer says so against a tilted map before three seconds
            # of it, or with no judge the player's person detection and a sound flat map. The
            # detector does not see the figure in every picture by night, and a flat map over a
            # street grid was read as tilted on 13 November; neither stops a figure the judge sees
            # standing beside a car.
            if player_mode(obs) != "foot":
                return SkillResult()
            if obs.mode is None and (
                not standing
                or obs.reading.corrupt
                or obs.reading.confidence < 0.45
                or obs.reading.minimap != "flat"
            ):
                return SkillResult()
            if not within_reach(self.target.obj):
                self.phase = "approach"
                self.was_walking = True
                return SkillResult(approach(self.target.obj))
            self.attempts += 1
            self.target.tries += 1
            self.entry_target = self.target
            self.taken_kind = self.target.occupancy
            self.taken_vehicle = self.target.obj.kind
            self.phase, self.phase_since = "wait", now
            return SkillResult(Pad(buttons=(self.profile.enter_vehicle,)))
        ready = self.phase != "retry" or self.retry_walk >= RETRY_APPROACH
        if within_reach(self.target.obj) and ready:
            self.phase = "tap"
            return SkillResult()
        self.was_walking = True
        self.walk_pad, self.walk_time = approach(self.target.obj, retry=self.phase == "retry"), now
        return SkillResult(self.walk_pad)
