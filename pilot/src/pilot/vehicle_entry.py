"""Bounded vehicle approach, entry tap, and observed entry confirmation."""

import math
from dataclasses import replace
from typing import ClassVar

from pilot.contract import FRAME_SIZE, Detection, Observation, Pad, SkillResult, player_mode
from pilot.profile import active

# Camera geometry and GTA door timing are estimates, pending live measurement.
MAX_SECONDS = 25.0
WIDTH, HEIGHT = FRAME_SIZE  # detections come in pixels of the frame
# One tick is 33 ms, shorter than a person's press (about 0.14 s) and easy for the console to miss.
PRESS_SECONDS = 0.09
DETECTION_MAX_AGE = 0.5
# On foot the minimap reader called the map a vehicle's five times in the eight minutes of
# session 20261110-231512, for 0.83 s at the longest.
CONFIRM_SECONDS = 1.0
ALREADY_SECONDS = 2.0
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
# With the far camera level the figure's feet stand at 0.73 of the picture's height, and a car whose
# lower edge comes that near is a step or two away whatever the height of its box. Seen from behind
# a saloon is 0.18 high with the figure against its bumper: the walk pushed into it for twenty
# seconds and never came to 0.28 (session 20261111-121517, lower edge at 0.68).
REACH_BOTTOM = 0.66
WALK_FAST = 0.55
WALK_SLOW = 0.30
# Walking to the door, opening it and sitting down; pulling a driver out takes longer.
# A stick moved too early cancels the walk to the door.
DOOR_WAIT = 4.0
RETRY_APPROACH = 2.4
MAX_ATTEMPTS = 4
# These replacement timings are bounded estimates, not a measured escape time.
CLEAR_SECONDS = 1.5
STOP_SECONDS = 1.0
SETTLE_SECONDS = 0.3
STOP_DRIFT = 0.018


class EnterVehicle:
    name = "enter_vehicle"
    parameters: ClassVar[dict] = {
        "duration": (0.1, MAX_SECONDS, MAX_SECONDS),
        "kind": ("any", "car", "motorcycle"),
        "strategy": ("normal", "replace"),
    }
    prompt = (
        "Enter a nearby vehicle using fresh detections and a readable movement mode. "
        "strategy replace first exits, moves away and excludes the abandoned car, "
        "then waits for another vehicle to stop. Normal keeps the usual entry. "
        "Confirms entry from sustained vehicle mode; fails on missing evidence, "
        "an unopened door or the duration limit (up to 25 seconds)."
    )

    def __init__(self, args: dict):
        self.profile = active()
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
        self.strategy = args.get("strategy", "normal")
        if self.strategy not in self.parameters["strategy"]:
            raise ValueError("strategy must be normal or replace")
        self.uninterruptible = self.strategy == "replace"
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
        self.leaving = self.strategy == "replace"
        self.exit_pressed = False
        self.exit_since = None
        self.mode_since = None
        self.leave_mode = None
        self.excluded = None
        self.excluded_capture = None
        self.exclusion_visible = False
        self.clear_walk = 0.0
        self.clear_side = None
        self.jump_used = False
        self.jump_until = None
        self.path_capture = None
        self.blocked_since = None
        self.still_since = None
        self.stationary = []
        self.stationary_capture = None
        self.approach_until = None
        self.previous_pad = Pad()

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

    @classmethod
    def _match(cls, previous, candidates, *, gate=TARGET_GATE, scale=(0.4, 2.5)):
        matches = []
        for obj in candidates:
            ratio = (obj.box[3] - obj.box[1]) / (previous.box[3] - previous.box[1])
            distance = math.dist(cls._center(previous), cls._center(obj))
            # Car/truck labels can alternate on the same pickup.
            compatible = obj.kind == previous.kind or {obj.kind, previous.kind} <= {"car", "truck"}
            if compatible and distance <= gate and scale[0] <= ratio <= scale[1]:
                matches.append((distance + 0.05 * abs(math.log(ratio)), obj))
        return min(matches, key=lambda pair: pair[0])[1] if matches else None

    def _others(self, candidates, capture):
        if self.excluded is None:
            return []
        if capture != self.excluded_capture:
            matched = self._match(self.excluded, candidates, gate=0.07, scale=(0.75, 1.35))
            self.exclusion_visible = matched is not None
            if matched is not None:
                self.excluded = matched
            self.excluded_capture = capture
        if not self.exclusion_visible:
            return []
        # Keep the last exclusion through occlusion; losing the box is not permission to enter it.
        return [obj for obj in candidates if self._match(self.excluded, [obj]) is None]

    def _answer(self, obs, key):
        judgment = obs.judgment
        if judgment is None or not 0 <= obs.time - judgment.capture <= 1.0:
            return None
        answer = judgment.answers.get(key)
        return answer.value if answer is not None else None

    def _leave(self, obs, candidates, fresh, delta):
        now = obs.time
        mode = player_mode(obs)
        if mode != self.leave_mode:
            self.leave_mode = mode
            self.mode_since = now
        if mode == "vehicle":
            if not self.exit_pressed and now - self.mode_since >= CONFIRM_SECONDS:
                self.exit_pressed = True
                self.exit_since = now
            if self.exit_pressed and now - self.exit_since < PRESS_SECONDS:
                return SkillResult(Pad(buttons=(self.profile.enter_vehicle,)))
            return SkillResult()
        if mode != "foot" or not fresh:
            return SkillResult()
        if self.excluded is None:
            # A passing foreground car is not the abandoned car. Wait for a stable nearby box.
            nearby = [
                obj
                for obj in candidates
                if obj.box[3] >= 0.35 and (obj.box[2] - obj.box[0]) * (obj.box[3] - obj.box[1]) >= 0.015
            ]
            stopped = self._stopped(nearby, obs)
            if stopped:
                self.excluded = max(
                    stopped, key=lambda obj: (obj.box[2] - obj.box[0]) * (obj.box[3] - obj.box[1])
                )
                self.excluded_capture = obs.objects_time
                self.exclusion_visible = True
            else:
                return (
                    SkillResult(Pad(right=(SCAN_TURN, 0)))
                    if not nearby and (now - self.started) % SCAN_PERIOD < SCAN_PULSE
                    else SkillResult()
                )
        self._others(candidates, obs.objects_time)
        if now - self.mode_since < CONFIRM_SECONDS:
            return SkillResult()
        if self.clear_side is None:
            # The side opposite the abandoned car leaves room for the figure and the next door.
            self.clear_side = -1 if self._center(self.excluded)[0] >= 0.5 else 1
        if self.previous_pad.left != (0, 0):
            self.clear_walk += delta
        path = self._answer(obs, "path")
        if path != "blocked":
            self.blocked_since = None
        elif obs.judgment.capture != self.path_capture:
            self.path_capture = obs.judgment.capture
            if self.blocked_since is None:
                self.blocked_since = obs.judgment.capture
        if self.clear_walk < CLEAR_SECONDS:
            buttons = ()
            if (
                not self.jump_used
                and self.blocked_since is not None
                and obs.judgment.capture - self.blocked_since >= 0.5
                and self.profile.name == "gta5"
            ):
                # GTA V's jump can clear a low parapet; a blocked answer cannot tell its height.
                self.jump_used = True
                self.jump_until = now + PRESS_SECONDS
            if self.jump_until is not None and now < self.jump_until:
                buttons = ("square",)
            return SkillResult(Pad(left=(0.5 * self.clear_side, -0.4), buttons=buttons))
        self.leaving = False
        self.confirmed_since = None
        self.still_since = now
        return SkillResult()

    def _stopped(self, candidates, obs):
        now = obs.time
        if self.previous_pad.left != (0, 0) or self.previous_pad.right != (0, 0):
            self.still_since = now
            self.stationary = []
        if self.still_since is None:
            self.still_since = now
        if now - self.still_since < SETTLE_SECONDS:
            return []
        if self.stationary_capture != obs.objects_time:
            tracks = []
            available = list(self.stationary)
            for obj in candidates:
                prior = next((track for track in available if self._match(track[0], [obj]) is not None), None)
                if prior is not None:
                    available.remove(prior)
                if (
                    prior is not None
                    and obs.objects_time - prior[3] <= DETECTION_MAX_AGE
                    and max(abs(a - b) for a, b in zip(obj.box, prior[1], strict=True)) <= STOP_DRIFT
                ):
                    tracks.append((obj, prior[1], prior[2], obs.objects_time))
                else:
                    tracks.append((obj, obj.box, obs.objects_time, obs.objects_time))
            self.stationary = tracks
            self.stationary_capture = obs.objects_time
        return [obj for obj, _, since, capture in self.stationary if capture - since >= STOP_SECONDS]

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
            result = self._step(observation)
            self.previous_pad = result.pad
            return result
        except Exception:
            return self.stop("invalid observation")

    def _step(self, obs):
        now = obs.time
        if not math.isfinite(now) or (self.last_time is not None and now < self.last_time):
            return self.stop("invalid observation time")
        delta = 0 if self.last_time is None else min(DETECTION_MAX_AGE, now - self.last_time)
        if self.phase == "retry" and self.was_walking and self.last_time is not None:
            self.retry_walk += min(DETECTION_MAX_AGE, now - self.last_time)
        self.was_walking = False
        self.last_time = now
        if self.started is None:
            self.started = now
        elapsed = now - self.started
        if elapsed >= self.limit:
            return self.stop(
                "replacement timed out" if self.strategy == "replace" else self._timeout_reason()
            )

        if self.strategy == "replace":
            if (
                obs.reading.corrupt
                or player_mode(obs) in {None, "none"}
                or (obs.hud and obs.hud.screen != "game")
            ):
                self.mode_since = now
                self.confirmed_since = None
                self.stationary = []
                self.still_since = now
                return SkillResult()
            fresh = (
                obs.objects_time is not None
                and math.isfinite(obs.objects_time)
                and 0 <= now - obs.objects_time <= DETECTION_MAX_AGE
            )
            candidates = self._candidates(obs) if fresh else []
            if self.leaving:
                return self._leave(obs, candidates, fresh, delta)

        # Entry owns the pad even if object delivery disappears during the animation.
        if player_mode(obs) == "none":
            return SkillResult()
        if self.phase == "wait" and now - self.phase_since < PRESS_SECONDS:
            return SkillResult(Pad(buttons=(self.profile.enter_vehicle,)))
        if obs.reading.corrupt:
            # A damaged tick says nothing about the map: it neither counts nor starts over.
            if self.confirmed_since is not None:
                return SkillResult()
        elif player_mode(obs) == "vehicle":
            if self.strategy == "replace" and not self.attempts:
                # A map glitch or an unsolicited return to the old seat is not a replacement.
                return SkillResult()
            if self.confirmed_since is None:
                self.confirmed_since = now
            # Before any press the character sat in a vehicle already, or the reader is wrong.
            needed = CONFIRM_SECONDS if self.attempts else ALREADY_SECONDS
            if now - self.confirmed_since >= needed:
                reason = "entered vehicle" if self.attempts else "already in a vehicle"
                self.finished = SkillResult(status="done", reason=reason)
                return self.finished
            return SkillResult()
        else:
            self.confirmed_since = None

        if self.phase == "wait":
            if now - self.phase_since < DOOR_WAIT:
                return SkillResult()
            if self.attempts >= MAX_ATTEMPTS:
                return self.stop("door never opened")
            self.phase = "retry"
            self.phase_since = now
            self.retry_walk = 0.0

        if obs.reading.corrupt or player_mode(obs) != "foot":
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
        candidates = self._candidates(obs)
        if self.strategy == "replace":
            candidates = self._others(candidates, obs.objects_time)
            if self.approach_until is None or now >= self.approach_until:
                self.approach_until = None
                candidates = self._stopped(candidates, obs)
                if not candidates:
                    return SkillResult()
                self.approach_until = now + 0.35
            if self._answer(obs, "car") is False and self.phase == "tap":
                self.phase = "approach"
                return SkillResult()
        target = self._select(candidates, now)
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
            return SkillResult(Pad(buttons=(self.profile.enter_vehicle,)))
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
        if aligned and (height >= REACH_HEIGHT or target.box[3] >= REACH_BOTTOM) and retry_ready:
            # One release tick before the tap also clears queued movement commands.
            self.phase = "tap"
            return SkillResult()
        speed = max(WALK_SLOW, WALK_FAST - height * 0.25) if aligned else 0.0
        self.was_walking = speed > 0
        return SkillResult(Pad(left=(0.0, -speed), right=(turn, 0.0)))
