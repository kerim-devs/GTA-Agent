"""Bring the camera's tilt back to straight ahead behind the figure: a move without a reading.

On foot the game never levels a tilted camera by itself: in the probe of 11 November the tilt was
still there after 2.5 s of standing and after 2 s of walking. The tilt has hard stops, so the move
runs into the upper one and comes back down by a fixed amount. From three different tilts it ended
on the same picture on the console; the sheets are in lab/camera-live.
"""

from math import isfinite
from typing import ClassVar

from pilot.contract import Observation, Pad, SkillResult


class LevelCamera:
    name = "level_camera"
    parameters: ClassVar = {"duration": (6.0, 12.0, 8.0)}
    prompt = (
        "Bring the camera's tilt back to straight ahead behind the figure. On foot only; the figure "
        "stands still for six seconds. Use it when the picture looks down on the figure from above "
        "or up into the sky. It does not turn the camera sideways. duration is only a time limit."
    )
    # A plan that arrives while the move runs waits for its end: half a move leaves the camera
    # anywhere.
    uninterruptible: ClassVar = True

    # Measured on the console on 11 November: two seconds of full stick reach the upper stop from
    # the lower one, and four pulses down from there look straight ahead (five look at the ground
    # in front of the figure, as the game does after a cutscene).
    UP_SECONDS = 2.0
    REST_SECONDS = 0.5
    PULSES = 4
    PULSE_SECONDS = 0.3
    GAP_SECONDS = 0.5
    PULSE_STICK = 0.5
    # The reader holds a wrong map class for up to 0.83 s on foot, so one tick does not say "vehicle".
    FOOT_TIMEOUT = 1.5
    # A tick that comes late has not held the stick for all that time.
    LONGEST_TICK = 0.1

    def __init__(self, args: dict):
        if not isinstance(args, dict) or set(args) - self.parameters.keys():
            raise ValueError("level_camera accepts only duration")
        low, high, default = self.parameters["duration"]
        value = args.get("duration", default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
            raise ValueError("duration must be a finite number")
        self.limit = float(max(low, min(high, value)))
        self.finished = None
        self.started = None
        self.last_time = None
        self.on_foot = False
        self.progress = 0.0

    def stop(self, reason: str = "interrupted") -> SkillResult:
        self.finished = SkillResult(status="failed", reason=reason)
        return self.finished

    def step(self, obs: Observation) -> SkillResult:
        if self.finished is not None:
            return self.finished
        now = obs.time
        if self.started is None:
            self.started = now
        if self.last_time is not None and now < self.last_time:
            return self.stop("clock-reversed")
        if now - self.started >= self.limit:
            return self.stop("time-limit")
        if not self.on_foot:
            if obs.reading.minimap == "flat" and not obs.reading.corrupt:
                self.on_foot = True
            elif now - self.started >= self.FOOT_TIMEOUT:
                # Nothing to level is not a failure the head has to hear about.
                self.finished = SkillResult(status="done", reason="not on foot")
                return self.finished
            else:
                self.last_time = now
                return SkillResult()
        elif self.last_time is not None:
            self.progress += min(now - self.last_time, self.LONGEST_TICK)
        self.last_time = now
        at = self.progress
        if at < self.UP_SECONDS:
            return SkillResult(Pad(right=(0.0, -1.0)))
        at -= self.UP_SECONDS + self.REST_SECONDS
        if at < 0:
            return SkillResult()
        pulse, within = divmod(at, self.PULSE_SECONDS + self.GAP_SECONDS)
        if pulse >= self.PULSES:
            self.finished = SkillResult(status="done", reason="levelled")
            return self.finished
        if within < self.PULSE_SECONDS:
            return SkillResult(Pad(right=(0.0, self.PULSE_STICK)))
        return SkillResult()
