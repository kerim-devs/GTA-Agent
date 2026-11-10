"""Local, bounded skills. Every result describes the entire controller state."""

from collections import deque
from dataclasses import dataclass

from .contract import NEUTRAL_PAD, Pad, Reading
from .drive import Driver
from .head import SkillCall, parse_response


@dataclass(frozen=True)
class Observation:
    reading: Reading
    moving: bool | None
    time: float


@dataclass(frozen=True)
class SkillResult:
    pad: Pad = NEUTRAL_PAD
    status: str = "running"
    reason: str | None = None


def clamp(value, lower, upper):
    return min(upper, max(lower, value))


class Skill:
    def __init__(self, call: SkillCall, *, driver=None):
        # Direct callers get the same all-or-nothing validation as a head response.
        parse_response({"plan": [{"name": call.name, "args": call.args}], "sentence": "Weiter."})
        self.name = call.name
        self.args = dict(call.args)
        limits = {
            "drive_route": (0.1, 120, 60),
            "wait": (0.1, 60, 30),
            "press": (0.05, 1, 0.1),
            "walk": (0.1, 10, 1),
            "look": (0.1, 5, 0.5),
            "shoot": (0.05, 1, 0.2),
        }
        lower, upper, default = limits[self.name]
        self.duration = clamp(self.args.get("duration", default), lower, upper)
        if self.name == "look":
            angle = clamp(self.args.get("angle", 0), -180, 180)
            # Open-loop estimate, not a measured camera calibration.
            self.duration = clamp(self.args.get("duration", abs(angle) / 90), lower, upper)
        self.count = int(clamp(self.args.get("count", 1), 1, 5))
        self.cycle = self.duration + (0.3 if self.name == "shoot" else 0.1)
        self.limit = min(10, self.count * self.cycle) if self.name in ("press", "shoot") else self.duration
        self.driver = (Driver() if driver is None else driver) if self.name == "drive_route" else None
        self.started = None
        self.finished = None

    def stop(self, reason="interrupted") -> SkillResult:
        self.finished = SkillResult(status="failed", reason=reason)
        return self.finished

    def step(self, observation: Observation) -> SkillResult:
        if self.finished is not None:
            return self.finished
        if self.started is None:
            self.started = observation.time
        elapsed = observation.time - self.started
        if elapsed < 0:
            return self.stop("clock-reversed")
        if elapsed >= self.limit:
            self.finished = SkillResult(status="done", reason="time-limit")
            return self.finished
        try:
            if self.name == "drive_route":
                command = self.driver.step(
                    observation.reading,
                    observation.time,
                    observation.moving,
                    speed=observation.reading.gps_speed,
                )
                if command.state in ("route-gone", "failed-recovery"):
                    self.finished = SkillResult(
                        status="done" if command.state == "route-gone" else "failed", reason=command.state
                    )
                    return self.finished
                return SkillResult(Pad.from_command(command))
            if self.name == "wait":
                return SkillResult()
            if self.name == "walk":
                stick = (clamp(self.args.get("x", 0), -1, 1), clamp(self.args.get("y", 0), -1, 1))
                sprinting = self.args.get("sprint", False) and elapsed % 0.25 < 0.125
                return SkillResult(Pad(left=stick, buttons=("cross",) if sprinting else ()))
            if self.name == "look":
                angle = clamp(self.args.get("angle", 0), -180, 180)
                return SkillResult(Pad(right=(clamp(angle / (90 * self.duration), -1, 1), 0)))
            if self.name == "shoot":
                phase = elapsed % self.cycle
                if phase < 0.2:
                    return SkillResult(Pad(l2=1))
                if phase < 0.2 + self.duration:
                    return SkillResult(Pad(l2=1, r2=1))
                return SkillResult()
            pressed = elapsed % (self.duration + 0.1) < self.duration
            if not pressed:
                return SkillResult()
            return SkillResult(Pad(buttons=(self.args["button"],)))
        except Exception as exc:
            return self.stop(f"skill-error: {type(exc).__name__}")


class SkillRunner:
    def __init__(self, *, driver_factory=Driver):
        self.driver_factory = driver_factory
        self.queue = deque()
        self.active = None
        self.last = None
        self.release_pending = False
        self.completed = False

    def replace(self, calls: tuple[SkillCall, ...]) -> Pad:
        # Construct all skills before touching the existing plan.
        replacements = [
            Skill(call, driver=self.driver_factory() if call.name == "drive_route" else None)
            for call in calls
        ]
        self.stop("replaced")
        self.queue.extend(replacements)
        self.release_pending = True
        return NEUTRAL_PAD

    def stop(self, reason="interrupted") -> Pad:
        if self.active is not None:
            result = self.active.stop(reason)
            self.last = {"name": self.active.name, "status": result.status, "reason": result.reason}
        self.active = None
        self.queue.clear()
        self.completed = False
        self.release_pending = True
        return NEUTRAL_PAD

    def tick(self, observation: Observation) -> SkillResult:
        self.completed = False
        if self.release_pending:
            self.release_pending = False
            return SkillResult()
        if self.active is None:
            if not self.queue:
                return SkillResult(status="done")
            self.active = self.queue.popleft()
        result = self.active.step(observation)
        if result.status != "running":
            self.last = {"name": self.active.name, "status": result.status, "reason": result.reason}
            self.active = None
            if result.status == "failed":
                self.queue.clear()
            self.completed = not self.queue
        return result

    def describe(self):
        if self.active is not None:
            return {"name": self.active.name, "status": "running", "reason": None}
        return self.last
