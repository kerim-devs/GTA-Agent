"""Bounded assisted-aim combat; every observation returns a complete pad."""

import math
from typing import ClassVar

from pilot.contract import NEUTRAL_PAD, Observation, Pad, SkillResult, player_mode
from pilot.hits import Hits
from pilot.profile import active
from pilot.punch import Punch

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
COVER_TAP_SECONDS = 0.12  # P77: 26 cover holds during red fire, median 0.11915s.
# P77 recorded-rhythm.json, red fire stretches, rounded to milliseconds.
# Use the observed fast quartile for acquisition; median human waits include
# deliberate aim time. This is a policy choice, not proof of the game's lock time.
AIM_SETTLE = 0.206  # L2 to first overlapping R2: 207 locks, p25 0.2055s.
AIM_HOLD = 1.101  # 210 L2 intervals, median 1.10055s, while the target stays ahead.
BURST_SECONDS = 0.222  # 467 R2 intervals, median 0.2223s.
BURST_GAP = 0.726  # 283 gaps <=2s, median 0.7257s.
BURSTS_PER_LOCK = 1  # 210 locks, median one burst before letting L2 go.
RETARGET_SECONDS = 0.536  # 114 re-lock gaps <=2s, median 0.53565s.
HIT_RESPONSE_SECONDS = 2.0  # P77's prescribed post-hit observation window.
HIT_STRAFE = -1.0  # movement.json: negative lateral post-hit axis median 1.0 (5.348s).
FIGHT_TURN = 0.99  # movement.json: active pre-lock horizontal axis median .99 (31.911s).
# Existing melee settles/releases stay unchanged; punch.py owns press cadence.
MELEE_AIM_SETTLE = 0.3
MELEE_RETARGET_SECONDS = 0.2
MELEE_RANGE = 18.0
MELEE_PULSE = Punch.PULSE_DURATION
MELEE_GAP = Punch.PULSE_PERIOD - Punch.PULSE_DURATION
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
        and reading.minimap != "none"
        and player_mode(observation) == "foot"
        and math.isfinite(reading.confidence)
        and reading.confidence > 0
    )


class Fight:
    name = "fight"
    parameters: ClassVar = {"duration": (0.1, 30.0, 30.0), "cover": ("no", "yes")}
    prompt = (
        "fight(duration=30, cover=no|yes): lock first with L2, fire measured bursts "
        "and turn only between locks. Needs a readable camera-relative "
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
        self.hits = Hits()
        self.evade_until = None
        self.release_since = None

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

        if self.name == "fight" and observation.hud is not None and observation.hud.wanted not in (None, 0):
            return self.stop("stars")

        hit = self.hits.update(now, observation.hud) if self.name == "fight" else None
        if hit is not None:
            self.evade_until = now + HIT_RESPONSE_SECONDS
            if self.args["cover"] == "yes":
                self.cover_until = now + COVER_TAP_SECONDS

        health = observation.hud.health if observation.hud is not None else None
        if health is not None and (not math.isfinite(health) or not 0 <= health <= 1):
            health = None
        if health is not None and health <= 0:
            return self.stop("health-depleted")
        if self.name == "fight" and health is not None and health < 1 / 3:
            return self.stop("health-still-low")

        reading = observation.reading
        if not readable(observation):
            self.clear_since = None
            self.lock_since = None
            self.release_since = None
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
            self.release_since = None
        self.last_readable = now
        self.missing_since = None

        target = nearest_red(reading)
        if target is None:
            self.lock_since = None
            self.release_since = None
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
        if self.name == "fight":
            return self._shoot(now, angle)
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
        hold = MELEE_AIM_SETTLE + count * (pulse + gap)
        if elapsed >= hold:
            if elapsed >= hold + MELEE_RETARGET_SECONDS:
                self.lock_since = None
            return SkillResult()
        attacking = elapsed >= MELEE_AIM_SETTLE and (elapsed - MELEE_AIM_SETTLE) % (pulse + gap) < pulse
        if self.name == "melee":
            return SkillResult(pad=Pad(l2=1.0, buttons=(self.profile.melee,) if attacking else ()))
        return SkillResult(pad=Pad(l2=1.0, r2=1.0 if attacking else 0.0))

    def _shoot(self, now, angle):
        """Let the game turn first; camera correction is strictly L2-up."""
        if self.cover_until is not None and now < self.cover_until:
            self.lock_since = None
            self.release_since = None
            return SkillResult(pad=Pad(buttons=(self.profile.cover,)))
        left = (
            (HIT_STRAFE, 0.0)
            if self.args["cover"] == "no" and self.evade_until is not None and now < self.evade_until
            else (0.0, 0.0)
        )
        if self.release_since is not None:
            if abs(angle) > ALIGN_DEGREES:
                turn = math.copysign(FIGHT_TURN, angle)
                return SkillResult(pad=Pad(left=left, right=(turn, 0.0)))
            if now - self.release_since < RETARGET_SECONDS:
                return SkillResult(pad=Pad(left=left))
            self.release_since = None
        if self.lock_since is None:
            self.lock_since = now
        elapsed = now - self.lock_since
        # A lock ends after its last burst; no final inter-burst gap is added.
        hold = AIM_SETTLE + BURSTS_PER_LOCK * BURST_SECONDS + (BURSTS_PER_LOCK - 1) * BURST_GAP
        # A frontal lock gets the measured hold. If the marker remains off-axis,
        # release after the scheduled bursts so the next lock can face it.
        if abs(angle) <= FRONT_DEGREES:
            hold = max(hold, AIM_HOLD)
        if elapsed >= hold:
            self.lock_since = None
            self.release_since = now
            return SkillResult(pad=Pad(left=left))
        attacking = (
            elapsed >= AIM_SETTLE and (elapsed - AIM_SETTLE) % (BURST_SECONDS + BURST_GAP) < BURST_SECONDS
        )
        return SkillResult(pad=Pad(left=left, l2=1.0, r2=float(attacking)))


class Melee(Fight):
    name = "melee"
    parameters: ClassVar = {"duration": (0.1, 10.0, 10.0), "cover": ("no", "yes")}
    prompt = (
        "melee(duration=10, cover=no|yes): face a nearby red minimap enemy, "
        "lock with L2 and pulse circle. Requires assisted aim and an unarmed "
        "player. Fails if the target is distant, the map is lost, health stays "
        "low or time expires. Done after 2s on a readable map without red."
    )
