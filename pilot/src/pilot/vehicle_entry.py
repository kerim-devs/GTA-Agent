"""Bounded vehicle approach, entry tap, and observed entry confirmation."""

import math
from dataclasses import replace
from typing import ClassVar

from pilot.contract import FRAME_SIZE, Detection, Pad
from pilot.skills import Observation, SkillResult

# Camera geometry and GTA door timing are estimates, pending live measurement.
MAX_SECONDS = 25.0
WIDTH, HEIGHT = FRAME_SIZE  # detections come in pixels of the frame
# One tick is 33 ms, shorter than a person's press (about 0.14 s) and easy for the console to miss.
PRESS_SECONDS = 0.09
DETECTION_MAX_AGE = 0.5
CONFIRM_SECONDS = 0.5
SCAN_SECONDS = 5.0
SCAN_PERIOD = 0.7
SCAN_PULSE = 0.18
SCAN_TURN = 0.45
TARGET_GRACE = 1.0
MIN_CONFIDENCE = 0.45
TARGET_GATE = 0.22
CENTER_TOLERANCE = 0.09
TURN_GAIN = 1.0
MAX_TURN = 0.3
TURN_DEADBAND = 0.01
TURN_MIN_GAIN = 0.35
TURN_DAMPING = 0.65
TURN_REVERSAL_ERROR = 0.025
REACH_HEIGHT = 0.28
WALK_FAST = 0.55
WALK_SLOW = 0.30
# Walking to the door, opening it and sitting down; pulling a driver out takes longer.
# A stick moved too early cancels the walk to the door.
DOOR_WAIT = 4.0
RETRY_APPROACH = 2.4
MAX_ATTEMPTS = 4


class EnterVehicle:
    name = "enter_vehicle"
    parameters: ClassVar[dict] = {
        "duration": (0.1, MAX_SECONDS, MAX_SECONDS),
        "kind": ("any", "car", "motorcycle"),
    }
    prompt = (
        "Approach and enter a nearby detected vehicle (kind any/car/motorcycle; "
        "duration up to 25). Needs fresh vehicle detections and a readable minimap. "
        "Waits neutrally during entry; succeeds only after the vehicle map persists. "
        "Fails if detections or vehicles are absent, approach fails, the door never "
        "opens, or time runs out."
    )

    def __init__(self, args: dict):
        if not isinstance(args, dict) or set(args) - self.parameters.keys():
            raise ValueError("unknown enter_vehicle arguments")
        duration = args.get("duration", MAX_SECONDS)
        if isinstance(duration, bool) or not isinstance(duration, (int, float)):
            raise ValueError("duration must be a finite number")
        if not math.isfinite(duration):
            raise ValueError("duration must be a finite number")
        self.limit = min(MAX_SECONDS, max(0.1, duration))
        self.kind = args.get("kind", "any")
        if self.kind not in self.parameters["kind"]:
            raise ValueError("kind must be any, car, or motorcycle")
        self.started = None
        self.finished = None
        self.target = None
        self.last_seen = None
        self.last_time = None
        self.saw_delivery = False
        self.saw_target = False
        self.confirmed_since = None
        self.phase = "approach"
        self.phase_since = None
        self.attempts = 0
        self.turn_gain = TURN_GAIN
        self.previous_error = None
        self.previous_capture = None
        self.retry_walk = 0.0
        self.was_walking = False

    def stop(self, reason="interrupted") -> SkillResult:
        self.finished = SkillResult(status="failed", reason=reason)
        return self.finished

    def _timeout_reason(self):
        if not self.saw_delivery:
            return "no detections delivered at all"
        if self.attempts:
            return "door never opened"
        if self.saw_target:
            return "could not reach it"
        return "time up"

    def _candidates(self, obs):
        kinds = {"car", "truck", "bus", "motorcycle"} if self.kind == "any" else {self.kind}
        result = []
        for obj in obs.objects:
            if obj.kind not in kinds or not math.isfinite(obj.confidence):
                continue
            if obj.confidence < MIN_CONFIDENCE or len(obj.box) != 4:
                continue
            if not all(math.isfinite(v) for v in obj.box):
                continue
            x0, y0, x1, y1 = obj.box
            # Everything below works on the picture as 0 to 1 in both directions.
            box = (x0 / WIDTH, y0 / HEIGHT, x1 / WIDTH, y1 / HEIGHT)
            if not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1):
                continue
            result.append(replace(obj, box=box))
        return result

    @staticmethod
    def _center(obj):
        x0, y0, x1, y1 = obj.box
        return (x0 + x1) / 2, (y0 + y1) / 2

    def _select(self, candidates, now):
        if self.target is not None:
            cx, cy = self._center(self.target)
            old_height = self.target.box[3] - self.target.box[1]
            matches = []
            for obj in candidates:
                x, y = self._center(obj)
                ratio = (obj.box[3] - obj.box[1]) / old_height
                distance = math.hypot(x - cx, y - cy)
                if obj.kind == self.target.kind and distance <= TARGET_GATE and 0.4 <= ratio <= 2.5:
                    matches.append((distance + 0.05 * abs(math.log(ratio)), obj))
            if matches:
                self.target = min(matches, key=lambda pair: pair[0])[1]
                self.last_seen = now
                return self.target
            if now - self.last_seen <= TARGET_GRACE:
                return None
            self.target = None
        if not candidates:
            return None

        def score(obj: Detection):
            x0, y0, x1, y1 = obj.box
            # Area estimates proximity; central and low boxes favor the foreground.
            return (x1 - x0) * (y1 - y0) * (1 + y1) / (1 + 2 * abs((x0 + x1) / 2 - 0.5))

        self.target = max(candidates, key=score)
        self.last_seen = now
        return self.target

    def step(self, observation: Observation) -> SkillResult:
        if self.finished is not None:
            return self.finished
        try:
            return self._step(observation)
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

        if not obs.reading.corrupt and obs.reading.minimap == "tilted":
            if self.confirmed_since is None:
                self.confirmed_since = now
            if now - self.confirmed_since >= CONFIRM_SECONDS:
                self.finished = SkillResult(status="done", reason="entered vehicle")
                return self.finished
            return SkillResult()
        self.confirmed_since = None

        # Entry owns the pad even if object delivery disappears during the animation.
        if self.phase == "wait":
            if now - self.phase_since < PRESS_SECONDS:
                return SkillResult(Pad(buttons=("triangle",)))
            if now - self.phase_since < DOOR_WAIT:
                return SkillResult()
            if self.attempts >= MAX_ATTEMPTS:
                return self.stop("door never opened")
            self.phase = "retry"
            self.phase_since = now
            self.retry_walk = 0.0

        if obs.reading.corrupt or obs.reading.minimap != "flat":
            return SkillResult()
        fresh = (
            obs.objects_time is not None
            and math.isfinite(obs.objects_time)
            and 0 <= now - obs.objects_time <= DETECTION_MAX_AGE
        )
        if not fresh:
            if not self.saw_delivery and elapsed >= SCAN_SECONDS:
                return self.stop("no detections delivered at all")
            return SkillResult()
        self.saw_delivery = True
        target = self._select(self._candidates(obs), now)
        if target is None:
            if self.phase == "tap":
                self.phase = "approach"
            missing_for = elapsed if self.last_seen is None else now - self.last_seen
            if missing_for >= SCAN_SECONDS:
                return self.stop("could not reach it" if self.saw_target else "nothing found")
            # Short pulses cannot hold a stick through a run of missing detections.
            if self.target is None and missing_for % SCAN_PERIOD < SCAN_PULSE:
                return SkillResult(Pad(right=(SCAN_TURN, 0.0)))
            return SkillResult()
        self.saw_target = True
        if self.phase == "tap":
            self.attempts += 1
            self.phase = "wait"
            self.phase_since = now
            return SkillResult(Pad(buttons=("triangle",)))
        x, _ = self._center(target)
        error = x - 0.5
        height = target.box[3] - target.box[1]
        if obs.objects_time != self.previous_capture:
            if (
                self.previous_error is not None
                and error * self.previous_error < 0
                and min(abs(error), abs(self.previous_error)) > TURN_REVERSAL_ERROR
            ):
                # Delayed overshoot exposes excessive camera gain without knowing FOV.
                self.turn_gain = max(TURN_MIN_GAIN, self.turn_gain * TURN_DAMPING)
            self.previous_error = error
            self.previous_capture = obs.objects_time
        turn = 0.0 if abs(error) < TURN_DEADBAND else max(-MAX_TURN, min(MAX_TURN, error * self.turn_gain))
        aligned = abs(error) <= CENTER_TOLERANCE
        retry_ready = self.phase != "retry" or self.retry_walk >= RETRY_APPROACH
        if aligned and height >= REACH_HEIGHT and retry_ready:
            # One release tick before the tap also clears queued movement commands.
            self.phase = "tap"
            return SkillResult()
        speed = max(WALK_SLOW, WALK_FAST - height * 0.25) if aligned else 0.0
        self.was_walking = speed > 0
        return SkillResult(Pad(left=(0.0, -speed), right=(turn, 0.0)))
