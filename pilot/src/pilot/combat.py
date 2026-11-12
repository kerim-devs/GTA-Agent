"""Bounded camera-relative combat; requires the game's assisted targeting."""

import math
from typing import ClassVar

from pilot.contract import NEUTRAL_PAD, Observation, Pad, SkillResult, player_mode
from pilot.profile import active

# Conservative estimates pending a cable trial; provenance is in the P18 report.
FRONT_DEGREES = 12.0
ALIGN_DEGREES = 5.0
TURN_GAIN = 0.012
TURN_MAX = 0.55
TURN_MIN = 0.16
READING_GRACE = 0.2
MAP_WAIT = 2.0
CLEAR_WAIT = 2.0
LOW_HEALTH = 0.3
RECOVERED_HEALTH = 0.45
RECOVERY_WAIT = 4.0
COVER_TAP_SECONDS = 0.12
AIM_SETTLE = 0.3
BURST_SECONDS = 0.18
BURST_GAP = 0.2
BURSTS_PER_LOCK = 3
RETARGET_SECONDS = 0.2
MELEE_RANGE = 18.0
MELEE_PULSE = 0.12
MELEE_GAP = 0.2
MELEE_PULSES_PER_LOCK = 2


def nearest_red(reading):
    """Return a finite red blip, with distance measured in minimap pixels."""
    return min(
        (
            blip
            for blip in reading.blips
            if blip.color == "red" and math.isfinite(blip.x) and math.isfinite(blip.y)
        ),
        key=lambda blip: math.hypot(blip.x, blip.y),
        default=None,
    )


def readable(observation):
    reading = observation.reading
    return (
        reading is not None
        and not reading.corrupt
        and player_mode(observation) == "foot"
        and math.isfinite(reading.confidence)
        and reading.confidence > 0
    )


class Fight:
    name = "fight"
    parameters: ClassVar = {"duration": (0.1, 30.0, 30.0), "cover": ("no", "yes")}
    prompt = (
        "fight(duration=30, cover=no|yes): face the nearest red minimap enemy, "
        "aim and fire bursts with retargeting. Needs a readable camera-relative "
        "minimap, equipped weapon and assisted aim. Done after 2s without red. "
        "Fails on lost map, low health or time limit; cover is an unverified R1 tap."
    )

    def __init__(self, args: dict):
        self.profile = active()
        if not isinstance(args, dict) or args.keys() - self.parameters.keys():
            raise ValueError("unknown combat arguments")
        self.args = {}
        for name, values in self.parameters.items():
            if isinstance(values[0], str):
                value = args.get(name, values[0])
                if not isinstance(value, str) or value not in values:
                    raise ValueError(f"invalid {name}")
            else:
                low, high, default = values
                value = args.get(name, default)
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise ValueError(f"invalid {name}")
                value = max(low, min(high, value))
            self.args[name] = value
        self.limit = self.args["duration"]
        self.started = None
        self.last_time = None
        self.last_readable = None
        self.missing_since = None
        self.clear_since = None
        self.clear_seconds = 0.0
        self.lock_since = None
        self.recovery_since = None
        self.cover_until = None
        self.finished = None

    def stop(self, reason="interrupted") -> SkillResult:
        if self.finished is None:
            self.finished = SkillResult(status="failed", reason=reason)
        return self.finished

    def step(self, observation: Observation) -> SkillResult:
        if self.finished is not None:
            return self.finished
        now = observation.time
        if not math.isfinite(now) or (self.last_time is not None and now < self.last_time):
            return self.stop("invalid-observation-time")
        if self.started is None:
            self.started = now
        self.last_time = now
        if now - self.started >= self.limit:
            return self.stop("combat-timeout")

        health = observation.hud.health if observation.hud is not None else None
        if health is not None and (not math.isfinite(health) or not 0 <= health <= 1):
            health = None
        if health is not None and health <= 0:
            return self.stop("health-depleted")

        reading = observation.reading
        if not readable(observation):
            self.clear_since = None
            self.lock_since = None
            self.cover_until = None
            if self.missing_since is None:
                self.missing_since = now
            if now - self.missing_since > READING_GRACE:
                self.clear_seconds = 0.0
            if now - self.missing_since >= MAP_WAIT:
                return self.stop("minimap-unreadable")
            # There is no trustworthy front target, even within the grace period.
            return SkillResult()
        if self.last_readable is not None and now - self.last_readable > READING_GRACE:
            self.clear_since = None
            self.clear_seconds = 0.0
            self.lock_since = None
        self.last_readable = now
        self.missing_since = None

        target = nearest_red(reading)
        if target is None:
            self.lock_since = None
            if self.clear_since is not None:
                self.clear_seconds += now - self.clear_since
            self.clear_since = now
            if self.clear_seconds >= CLEAR_WAIT:
                self.finished = SkillResult(status="done", reason="no-red-blips")
                return self.finished
            return SkillResult()
        self.clear_since = None
        self.clear_seconds = 0.0
        if self.recovery_since is not None:
            self.lock_since = None
            if health is not None and health >= RECOVERED_HEALTH:
                self.recovery_since = None
                self.cover_until = None
            elif now - self.recovery_since >= RECOVERY_WAIT:
                if health is not None and health < LOW_HEALTH:
                    return self.stop("health-still-low")
                self.recovery_since = None
                self.cover_until = None
            else:
                return SkillResult(
                    pad=Pad(buttons=(self.profile.cover,))
                    if self.cover_until is not None and now < self.cover_until
                    else NEUTRAL_PAD
                )
        if health is not None and health < LOW_HEALTH:
            self.lock_since = None
            self.recovery_since = now
            self.cover_until = now + COVER_TAP_SECONDS if self.args["cover"] == "yes" else None
            return SkillResult(
                pad=Pad(buttons=(self.profile.cover,)) if self.args["cover"] == "yes" else NEUTRAL_PAD
            )

        if self.name == "melee" and (target.border or math.hypot(target.x, target.y) > MELEE_RANGE):
            return self.stop("melee-target-too-far")
        angle = math.degrees(math.atan2(target.x, target.y))
        if abs(angle) > FRONT_DEGREES or (self.lock_since is None and abs(angle) > ALIGN_DEGREES):
            self.lock_since = None
            turn = math.copysign(min(TURN_MAX, max(TURN_MIN, abs(angle) * TURN_GAIN)), angle)
            return SkillResult(pad=Pad(right=(turn, 0.0)))

        if self.lock_since is None:
            self.lock_since = now
        elapsed = now - self.lock_since
        pulse = MELEE_PULSE if self.name == "melee" else BURST_SECONDS
        gap = MELEE_GAP if self.name == "melee" else BURST_GAP
        count = MELEE_PULSES_PER_LOCK if self.name == "melee" else BURSTS_PER_LOCK
        hold = AIM_SETTLE + count * (pulse + gap)
        if elapsed >= hold:
            if elapsed >= hold + RETARGET_SECONDS:
                self.lock_since = None
            return SkillResult()
        attacking = elapsed >= AIM_SETTLE and (elapsed - AIM_SETTLE) % (pulse + gap) < pulse
        if self.name == "melee":
            return SkillResult(pad=Pad(l2=1.0, buttons=(self.profile.melee,) if attacking else ()))
        return SkillResult(pad=Pad(l2=1.0, r2=1.0 if attacking else 0.0))


class Melee(Fight):
    name = "melee"
    parameters: ClassVar = {"duration": (0.1, 10.0, 10.0), "cover": ("no", "yes")}
    prompt = (
        "melee(duration=10, cover=no|yes): face a nearby red minimap enemy, "
        "lock with L2 and pulse circle. Requires assisted aim and an unarmed "
        "player. Fails if the target is distant, the map is lost, health stays "
        "low or time expires. Done after 2s on a readable map without red."
    )
