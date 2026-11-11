"""Local, bounded skills. Every result describes the entire controller state."""

from collections import deque
from dataclasses import dataclass, field
from math import atan2, degrees, hypot
from typing import TYPE_CHECKING, ClassVar

import numpy as np

from .contract import NEUTRAL_PAD, Detection, Hud, Pad, Reading
from .drive import Driver

if TYPE_CHECKING:
    from .head import SkillCall


@dataclass(frozen=True)
class Observation:
    reading: Reading
    moving: bool | None
    time: float
    # Everything below is optional: a caller that has no frame, detector or HUD reader leaves it out,
    # and a skill that needs it fails with a reason instead of guessing.
    frame: np.ndarray | None = field(default=None, compare=False)  # 1280x720 RGB of this tick
    objects: tuple[Detection, ...] = ()  # newest detections; they lag the frame, see `objects_time`
    objects_time: float | None = None  # capture time of the frame the detections come from
    hud: Hud | None = None


@dataclass(frozen=True)
class SkillResult:
    pad: Pad = NEUTRAL_PAD
    status: str = "running"
    reason: str | None = None


def clamp(value, lower, upper):
    return min(upper, max(lower, value))


class Skill:
    def __init__(self, call: "SkillCall", *, driver=None):
        # Direct callers get the same all-or-nothing validation as a head response.
        from .head import parse_response

        parse_response({"plan": [{"name": call.name, "args": call.args}], "sentence": "Weiter."})
        self.name = call.name
        self.args = dict(call.args)
        lower, upper, default = REGISTRY[self.name].parameters["duration"]
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
        self.missing_since = None
        self.stopped_since = None
        self.sidestep_until = None
        self.sidestep = (0.0, 0.0)
        self.recoveries = 0
        self.aligned_since = None
        self.turn_sign = None

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
            status = "failed" if self.name in ("walk_to", "face") else "done"
            self.finished = SkillResult(status=status, reason="time-limit")
            return self.finished
        try:
            if self.name in ("walk_to", "face"):
                return self._blip_step(observation, elapsed)
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

    def _blip_step(self, observation: Observation, elapsed: float) -> SkillResult:
        reading, now = observation.reading, observation.time
        targets = [b for b in reading.blips if b.color == self.args["color"]]
        # Walking/camera geometry is checked only on foot. Unreadable frames never
        # inherit a command, including during a sidestep or camera settling.
        if reading.corrupt or reading.minimap != "flat" or not targets:
            self.aligned_since = self.stopped_since = self.sidestep_until = None
            if self.missing_since is None:
                self.missing_since = now
            if now - self.missing_since >= 2:
                return self.stop("blip-gone")
            return SkillResult()
        self.missing_since = None
        target = min(targets, key=lambda b: hypot(b.x, b.y))
        distance = hypot(target.x, target.y)
        if self.name == "face":
            if distance < 1:
                return self.stop("blip-bearing-undefined")
            angle = degrees(atan2(target.x, target.y))
            if abs(angle) <= 10:
                if self.aligned_since is None:
                    self.aligned_since = now
                if now - self.aligned_since >= 0.2:
                    self.finished = SkillResult(status="done", reason="aligned")
                    return self.finished
                return SkillResult()
            self.aligned_since = None
            if abs(angle) < 160 or self.turn_sign is None:
                self.turn_sign = 1 if angle > 0 else -1
            turn = min(0.65, abs(angle) * 0.01) * self.turn_sign
            return SkillResult(Pad(right=(turn, 0.0)))
        if distance <= 4 and not target.border:
            self.finished = SkillResult(status="done", reason="arrived")
            return self.finished
        if self.sidestep_until is not None and now < self.sidestep_until:
            return SkillResult(Pad(left=self.sidestep))
        if self.sidestep_until is not None:
            self.sidestep_until = self.stopped_since = None
        if observation.moving is False:
            if self.stopped_since is None:
                self.stopped_since = now
            if now - self.stopped_since >= 0.8:
                if self.recoveries >= 3:
                    return self.stop("blocked")
                side = 1 if self.recoveries % 2 == 0 else -1
                self.sidestep = (side * target.y / distance * 0.65, side * target.x / distance * 0.65)
                self.sidestep_until = now + 0.5
                self.stopped_since = None
                self.recoveries += 1
                return SkillResult(Pad(left=self.sidestep))
        else:
            self.stopped_since = None
        speed = clamp(distance / 14, 0.3, 0.85)
        sprinting = self.args.get("sprint", False) and distance > 14 and elapsed % 0.25 < 0.125
        return SkillResult(
            Pad(
                left=(target.x / distance * speed, -target.y / distance * speed),
                buttons=("cross",) if sprinting else (),
            )
        )


BUTTONS = (
    "cross",
    "circle",
    "square",
    "triangle",
    "l1",
    "r1",
    "l3",
    "r3",
    "up",
    "down",
    "left",
    "right",
    "l2",
    "r2",
    "options",
    "touchpad",
)
BLIP_COLORS = ("yellow", "blue", "red")


class RegisteredSkill(Skill):
    opens: ClassVar[tuple[str, ...]] = ()

    def __init__(self, args: dict, *, driver=None):
        from .head import SkillCall

        super().__init__(SkillCall(type(self).name, args), driver=driver)
        for key, value in self.args.items():
            rule = self.parameters[key]
            if not isinstance(value, bool) and isinstance(value, (int, float)):
                self.args[key] = clamp(value, rule[0], rule[1])


class DriveRoute(RegisteredSkill):
    name = "drive_route"
    parameters: ClassVar[dict] = {"duration": (0.1, 120, 60)}
    prompt = "Follow a visible GPS route in a vehicle, for at most duration seconds."


class Wait(RegisteredSkill):
    name = "wait"
    parameters: ClassVar[dict] = {"duration": (0.1, 60, 30)}
    prompt = "Wait with a neutral controller for duration seconds."


class Press(RegisteredSkill):
    name = "press"
    parameters: ClassVar[dict] = {"duration": (0.05, 1, 0.1), "count": (1, 5, 1), "button": BUTTONS}
    prompt = "Press a permitted button count times, with releases between presses."


class Walk(RegisteredSkill):
    name = "walk"
    parameters: ClassVar[dict] = {
        "duration": (0.1, 10, 1),
        "x": (-1, 1, 0),
        "y": (-1, 1, 0),
        "sprint": (False, True),
    }
    prompt = "Walk on foot: x is right, y is down (forward is negative y); optional sprint."


class Look(RegisteredSkill):
    name = "look"
    parameters: ClassVar[dict] = {"duration": (0.1, 5, 0.5), "angle": (-180, 180, 0)}
    prompt = "Turn the camera by an estimated angle in degrees, positive to the right."


class Shoot(RegisteredSkill):
    name = "shoot"
    parameters: ClassVar[dict] = {"duration": (0.05, 1, 0.2), "count": (1, 5, 1)}
    prompt = "Aim and fire count brief bursts, releasing the trigger between bursts."


class WalkTo(RegisteredSkill):
    name = "walk_to"
    parameters: ClassVar[dict] = {"duration": (0.1, 10, 10), "color": BLIP_COLORS, "sprint": (False, True)}
    prompt = "Walk toward the nearest visible blip of color on a flat minimap; fail if lost or blocked."


class Face(RegisteredSkill):
    name = "face"
    parameters: ClassVar[dict] = {"duration": (0.1, 5, 5), "color": BLIP_COLORS}
    prompt = "Turn to face the nearest visible blip of color on a flat minimap."


# New modules plug in with an import and one entry here.
from .combat import Fight, Melee  # noqa: E402
from .punch import Punch  # noqa: E402
from .vehicle_entry import EnterVehicle  # noqa: E402
from .waypoint import SetWaypoint  # noqa: E402

REGISTRY = {
    cls.name: cls
    for cls in (
        DriveRoute,
        Wait,
        Press,
        Walk,
        Look,
        Shoot,
        WalkTo,
        Face,
        SetWaypoint,
        EnterVehicle,
        Fight,
        Melee,
        Punch,
    )
}


def make_skill(call, *, driver=None):
    cls = REGISTRY[call.name]
    if call.name == "drive_route":
        return cls(call.args, driver=driver)
    return cls(call.args)


class SkillRunner:
    def __init__(self, *, driver_factory=Driver):
        self.driver_factory = driver_factory
        self.queue = deque()
        self.active = None
        self.last = None
        self.release_pending = False
        self.completed = False

    def replace(self, calls: tuple["SkillCall", ...]) -> Pad:
        # Construct all skills before touching the existing plan.
        replacements = [
            make_skill(call, driver=self.driver_factory() if call.name == "drive_route" else None)
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
            self.active_started = observation.time
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

    @property
    def has_plan(self):
        return self.active is not None or bool(self.queue)

    def append(self, calls):
        additions = [
            make_skill(call, driver=self.driver_factory() if call.name == "drive_route" else None)
            for call in calls
        ]
        self.queue.extend(additions)

    def remaining_steps(self, t):
        skills = ([self.active] if self.active is not None else []) + list(self.queue)
        result = []
        for skill in skills:
            limit = getattr(skill, "limit", None)
            if limit is None:
                params = REGISTRY[skill.name].parameters
                # Unknown implementations are bounded conservatively by declared duration.
                limit = params.get("duration", (0, 120, 120))[1]
            elapsed = max(0, t - self.active_started) if skill is self.active else 0
            result.append({"name": skill.name, "remaining_seconds": max(0, limit - elapsed)})
        return result

    def remaining(self, t):
        return sum(step["remaining_seconds"] for step in self.remaining_steps(t))
