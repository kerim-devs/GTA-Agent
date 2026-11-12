"""Bounded, pixel-box-only pursuit and unarmed punches.

Geometry and timing are estimates pending console calibration. No registry wiring.
"""

from math import hypot, isfinite, log
from typing import ClassVar

from pilot.contract import FRAME_SIZE, Detection, Observation, Pad, SkillResult, player_mode
from pilot.profile import active


class Punch:
    name = "punch"
    parameters: ClassVar = {"duration": (0.1, 20.0, 15.0), "hits": (1, 6, 3), "aim": ("lock", "free")}
    prompt = (
        "Walk up to the nearest person in view and punch: L2 to lock on, Circle in a quick rhythm, never a "
        "gun. hits is the number of punches asked for. On foot only. Done when the person is down or the "
        "presses are used up. Fails when nobody is seen, the person is lost, health is low or time is up. "
        "aim=free punches without the lock, the stick held at the person; untried."
    )

    FRESHNESS = 0.5
    DETECTOR_TIMEOUT = 1.0
    SEARCH_TIMEOUT = 3.0
    LOST_TIMEOUT = 1.0
    CENTER_TOLERANCE = 0.09
    # Nominal-camera simulation estimate, not a calibrated console reach signal. Only used while the
    # figure's own box is unknown.
    REACH_HEIGHT = 0.62
    # A fixed share of the frame holds for one camera view only: with the far view the figure's own
    # box is 0.27 to 0.30 of the frame and no person ever reaches 0.62, so the skill walked into a man
    # for nine seconds without a punch (session 20261112-215851). There the man's box was 0.79 to
    # 0.93 of the figure's own at contact and 0.52 of it five steps away.
    REACH_RATIO = 0.75
    # Held near a person, L2 makes the figure face and target that person by itself (Kerim, who
    # plays it, on 12 November), so within reach the box need not sit in the middle of the frame.
    LOCK_TOLERANCE = 0.2
    # The game runs one punch per animation however often Circle is pressed, and takes the next press
    # only in its own time: of four presses 0.65 s apart it ran one (session 20261112-220332). Kerim
    # presses in a quick rhythm and lets the game pick: over the 590 punches of his recordings a
    # press lasts 0.12 s and the next follows 0.21 s after it began (0.17 to 0.27 s), up to five in
    # a row. Four presses are asked of the game for every punch wanted.
    PULSE_DURATION = 0.12
    PULSE_PERIOD = 0.21
    PRESSES_PER_PUNCH = 4
    # Kerim punches without the lock on 479 of those 590 presses: he sees where the man stands and
    # holds the stick that way. aim=free is the place for that, in its plainest form and untried at
    # the console: the stick points at the person's box, fully sideways from this offset on. How he
    # really holds it is to be measured on his recordings before this is anything but a switch.
    FREE_SIDE = 0.2
    GROUND_DURATION = 0.45
    # The minimap reader calls a clean cable picture damaged for a tick or two about once a
    # second (2 to 3 in 100 frames of the sessions of 10 November, 16 ticks at the longest).
    HAZARD_TIMEOUT = 1.0

    def __init__(self, args: dict):
        self.profile = active()
        if not isinstance(args, dict) or set(args) - self.parameters.keys():
            raise ValueError("punch accepts only duration, hits and aim")
        values = {}
        for key, spec in self.parameters.items():
            if isinstance(spec[0], str):
                values[key] = args.get(key, spec[0])
                if not isinstance(values[key], str) or values[key] not in spec:
                    raise ValueError(f"{key} must be one of: {', '.join(spec)}")
                continue
            low, high, default = spec
            value = args.get(key, default)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or (isinstance(value, float) and not isfinite(value))
            ):
                raise ValueError(f"{key} must be a finite number")
            if key == "hits" and value != int(value):
                raise ValueError("hits must be an integer")
            values[key] = max(low, min(high, value))
        self.limit = float(values["duration"])
        self.hits = int(values["hits"])
        self.free = values["aim"] == "free"
        self.finished = None
        self.started = None
        self.last_time = None
        self.last_detection_time = None
        self.bad_detector_since = None
        self.low_health_since = None
        self.hazard_since = None
        self.target = None
        self.last_seen = None
        self.ground_since = None
        self.stood = False
        self.pulse_started = None
        self.next_pulse = 0.0
        self.delivered_hits = 0
        self.own_height = None

    def stop(self, reason: str = "interrupted") -> SkillResult:
        if self.finished is None:
            self.finished = SkillResult(status="failed", reason=reason)
        return self.finished

    def _done(self, reason: str) -> SkillResult:
        self.finished = SkillResult(status="done", reason=reason)
        return self.finished

    def step(self, obs: Observation) -> SkillResult:
        if self.finished is not None:
            return self.finished
        try:
            return self._step(obs)
        except (AttributeError, TypeError, ValueError, OverflowError):
            return self.stop("invalid observation; check detector and HUD readings")

    def _box(self, item: Detection):
        if item.kind != "person" or not isfinite(item.confidence):
            return None
        if item.confidence < 0.45 or len(item.box) != 4:
            return None
        x0, y0, x1, y1 = item.box
        width, height = FRAME_SIZE
        if not all(isfinite(v) for v in item.box):
            return None
        if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
            return None
        # A leaked third-person player occupies the lower central foreground.
        # Do not reuse the detector's broad filter: it also covers reachable NPCs.
        if (
            0.30 * width <= (x0 + x1) / 2 <= 0.65 * width
            and y1 >= 0.94 * height
            and y1 - y0 >= 0.48 * height
            and (x1 - x0) / (y1 - y0) >= 0.55
            and not self._continues_target((x0 / width, y0 / height, x1 / width, y1 / height))
        ):
            return None
        return x0 / width, y0 / height, x1 / width, y1 / height

    def _continues_target(self, box):
        if self.target is None:
            return False
        distance = hypot(*(a - b for a, b in zip(self._center(box), self._center(self.target), strict=True)))
        height_ratio = (box[3] - box[1]) / (self.target[3] - self.target[1])
        width_ratio = (box[2] - box[0]) / (self.target[2] - self.target[0])
        return distance <= 0.12 and 0.8 <= height_ratio <= 1.25 and 0.8 <= width_ratio <= 1.35

    @staticmethod
    def _center(box):
        return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2

    def _select(self, boxes):
        if self.target is None:
            return max(
                boxes,
                key=lambda b: (
                    (b[2] - b[0]) * (b[3] - b[1]) * (1 + b[3]) / (1 + 2 * abs(self._center(b)[0] - 0.5))
                ),
                default=None,
            )
        old_center = self._center(self.target)
        old_height = self.target[3] - self.target[1]
        candidates = []
        for box in boxes:
            distance = hypot(*(a - b for a, b in zip(self._center(box), old_center, strict=True)))
            ratio = (box[3] - box[1]) / old_height
            # Permit a target to collapse, while favoring the established size.
            fallen = (box[2] - box[0]) * FRAME_SIZE[0] > 1.6 * (box[3] - box[1]) * FRAME_SIZE[1]
            if distance <= 0.22 and (0.20 <= ratio <= 2.5 or fallen):
                candidates.append((distance + 0.08 * abs(log(ratio)), box))
        return min(candidates, default=(0, None), key=lambda entry: entry[0])[1]

    def _reach(self, obs):
        """How tall a person's box is at arm's length: a share of the figure's own, which stands at
        the same depth in any camera view; the last one seen is kept while the detector misses it."""
        figure = obs.figure
        if figure is not None and figure.kind == "person" and len(figure.box) == 4:
            height = (figure.box[3] - figure.box[1]) / FRAME_SIZE[1]
            if isfinite(height) and 0.1 <= height <= 1:
                self.own_height = height
        return self.REACH_HEIGHT if self.own_height is None else self.REACH_RATIO * self.own_height

    def _stance(self, target, *, pressed):
        """The pad of a punch: the lock, or without it the stick held at the person."""
        buttons = (self.profile.melee,) if pressed else ()
        if not self.free:
            return Pad(buttons=buttons, l2=1.0)
        side = max(-1.0, min(1.0, ((target[0] + target[2]) / 2 - 0.5) / self.FREE_SIDE))
        return Pad(buttons=buttons, left=(side, -((1 - side * side) ** 0.5)))

    def _release(self):
        self.pulse_started = None
        self.ground_since = None
        return SkillResult()

    def _step(self, obs):
        now = obs.time
        if (
            isinstance(now, bool)
            or not isfinite(now)
            or (self.last_time is not None and now < self.last_time)
        ):
            return self.stop("invalid observation time")
        if self.started is None:
            self.started = now
        self.last_time = now
        if now - self.started >= self.limit:
            return self.stop("punch time limit reached; move closer or choose another person")
        hazard = (
            "minimap unreadable; restore an on-foot game view"
            if obs.reading.corrupt or player_mode(obs) == "none"
            else "player is in a vehicle; exit before punching"
            if player_mode(obs) == "vehicle"
            else "gameplay interrupted; restore the game screen"
            if obs.hud is not None and obs.hud.screen != "game"
            else None
        )
        if hazard:
            # Everything is let go at once; one odd reading does not end the skill.
            if self.hazard_since is None:
                self.hazard_since = now
            if now - self.hazard_since >= self.HAZARD_TIMEOUT:
                return self.stop(hazard)
            return self._release()
        self.hazard_since = None
        health = obs.hud.health if obs.hud is not None else None
        if health is not None and isfinite(health) and health < 0.3:
            if self.low_health_since is None:
                self.low_health_since = now
            if now - self.low_health_since >= 0.5:
                return self.stop("health below 30%; retreat and recover")
        else:
            self.low_health_since = None

        stamp = obs.objects_time
        fresh = (
            stamp is not None
            and not isinstance(stamp, bool)
            and isfinite(stamp)
            and 0 <= now - stamp <= self.FRESHNESS
            and (self.last_detection_time is None or stamp >= self.last_detection_time)
        )
        if not fresh:
            if self.bad_detector_since is None:
                self.bad_detector_since = now
            if now - self.bad_detector_since >= self.DETECTOR_TIMEOUT:
                return self.stop("person detector unavailable or stale; check detector delivery")
            return self._release()
        self.bad_detector_since = None
        self.last_detection_time = stamp
        boxes = [box for item in obs.objects if (box := self._box(item)) is not None]
        target = self._select(boxes)
        if target is None:
            if self.target is not None and now - self.last_seen >= self.LOST_TIMEOUT:
                return self.stop("target person lost; restore visibility before retrying")
            if self.target is None and now - self.started >= self.SEARCH_TIMEOUT:
                return self.stop("no person found; face a visible person before retrying")
            return self._release()
        self.target = target
        self.last_seen = now
        x0, y0, x1, y1 = target
        # Compare pixel width/height, not normalized axes with different scales.
        ground = (x1 - x0) * FRAME_SIZE[0] > 1.6 * (y1 - y0) * FRAME_SIZE[1]
        if ground:
            if self.ground_since is None:
                self.ground_since = stamp
            self.pulse_started = None
            if stamp - self.ground_since >= self.GROUND_DURATION:
                if not self.stood:
                    # Nobody went down here: a figure that only ever lay there is no opponent,
                    # and the player's own, knocked over by a car, looks just like it.
                    return self.stop("person already on the ground; face a standing person")
                return self._done("target person remained on the ground")
            return SkillResult()
        self.ground_since = None
        self.stood = True
        error = (x0 + x1) / 2 - 0.5
        near = y1 - y0 >= self._reach(obs)
        tolerance = self.CENTER_TOLERANCE if self.own_height is None else self.LOCK_TOLERANCE
        in_reach = abs(error) <= tolerance and near
        if not in_reach:
            self.pulse_started = None
            turn = max(-0.35, min(0.35, error * 1.5))
            speed = 0.0 if near else 0.65
            if abs(error) > 0.18:
                speed *= 0.45
            return SkillResult(pad=Pad(left=(0.0, -speed), right=(turn, 0.0)))
        if self.pulse_started is not None:
            if now - self.pulse_started < self.PULSE_DURATION:
                return SkillResult(pad=self._stance(target, pressed=True))
            self.pulse_started = None
        if self.delivered_hits >= self.hits * self.PRESSES_PER_PUNCH:
            return self._done(f"pressed {self.delivered_hits} times in reach; nobody seen going down")
        if now >= self.next_pulse:
            self.pulse_started = now
            self.next_pulse = now + self.PULSE_PERIOD
            self.delivered_hits += 1
            return SkillResult(pad=self._stance(target, pressed=True))
        return SkillResult(pad=self._stance(target, pressed=False))
