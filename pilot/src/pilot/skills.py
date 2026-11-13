"""Local, bounded skills. Every result describes the entire controller state."""

from collections import deque
from dataclasses import dataclass
from math import atan2, degrees, hypot
from typing import TYPE_CHECKING, ClassVar

from .avoid import Avoider, waits_behind
from .contract import NEUTRAL_PAD, Observation, Pad, SkillResult, player_mode
from .drive import Driver
from .foot import FootGuard, WalkRoad
from .profile import active

if TYPE_CHECKING:
    from .head import SkillCall


def clamp(value, lower, upper):
    return min(upper, max(lower, value))


class Skill:
    def __init__(self, call: "SkillCall", *, driver=None):
        # Direct callers get the same all-or-nothing validation as a head response.
        self.profile = active()
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
        self.avoider = Avoider()
        self.started = None
        self.finished = None
        self.missing_since = None
        # Walking that pushes the stick and gets nowhere turns away and tries again (foot.py).
        self.guard = FootGuard() if self.name in ("walk", "walk_to") else None
        self.aligned_since = None
        self.turn_sign = None

    @property
    def recoveries(self):
        """How many times in a row walking has had to get free."""
        return 0 if self.guard is None else self.guard.failures

    def stop(self, reason="interrupted") -> SkillResult:
        self.finished = SkillResult(status="failed", reason=reason)
        return self.finished

    def _walk(self, observation: Observation, want, buttons) -> SkillResult:
        steer = self.guard.step(observation, want)
        if steer.failed:
            return self.stop(steer.failed)
        # Sprint belongs to the wanted direction only, not to a way round or a look.
        return SkillResult(
            Pad(left=steer.left, right=steer.right, buttons=buttons if steer.state in ("go", "idle") else ()),
            reason=self.guard.diagnostic(),
        )

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
                return SkillResult(self._around(command, observation))
            if self.name == "wait":
                return SkillResult()
            if self.name == "walk":
                stick = (clamp(self.args.get("x", 0), -1, 1), clamp(self.args.get("y", 0), -1, 1))
                sprinting = self.args.get("sprint", False)
                return self._walk(
                    observation, stick, self.profile.sprint_buttons(elapsed) if sprinting else ()
                )
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

    AROUND_BRAKE = 0.6  # L2 before something close and straight ahead
    AROUND_BRAKE_SPEED = 5.0  # m/s the speed has to be known above; a brake held at a standstill is reverse

    def _around(self, command, observation: Observation) -> Pad:
        """The driver's command, bent around what the detector sees in the way while the route is followed."""
        if command.state not in ("follow", "coast"):
            return Pad.from_command(command)
        bypass = (
            self.driver is not None
            and self.driver.config.queue_wait <= 2.0
            and self.driver.bypassing
            and waits_behind(observation.objects, observation.objects_time, observation.time)
        )
        around = self.avoider.step(
            observation.objects, observation.objects_time, observation.time, bypass=bypass
        )
        speed = observation.reading.gps_speed
        brake = command.brake
        rolling = speed is not None and speed > self.AROUND_BRAKE_SPEED and observation.moving is not False
        if around.urgent and rolling:
            brake = max(brake, self.AROUND_BRAKE)
        return Pad(
            left=(around.steer if bypass else clamp(command.steer + around.steer, -1, 1), 0.0),
            l2=brake,
            r2=0.0 if brake > command.brake else command.throttle * around.pedal,
        )

    def _blip_step(self, observation: Observation, elapsed: float) -> SkillResult:
        reading, now = observation.reading, observation.time
        targets = [b for b in reading.blips if b.color == self.args["color"]]
        # Walking/camera geometry is checked only on foot. Unreadable frames never
        # inherit a command, including during a way round or camera settling.
        if reading.corrupt or player_mode(observation) != "foot" or not targets:
            self.aligned_since = None
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
        speed = clamp(distance / 14, 0.3, 0.85)
        sprinting = self.args.get("sprint", False) and distance > 14
        result = self._walk(
            observation,
            (target.x / distance * speed, -target.y / distance * speed),
            self.profile.sprint_buttons(elapsed) if sprinting else (),
        )
        if result.status == "failed" and result.reason == "stuck":
            # The head knows "blocked" from walk_to as the end of every way round to a marker.
            return self.stop("blocked")
        return result


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
    @dataclass(frozen=True)
    class Result(SkillResult):
        start_distance: float | None = None
        end_distance: float | None = None
        distance_age: float | None = None
        # Seconds driven on a map the reader flagged as damaged, that stood for longer than damage does.
        flagged_seconds: float = 0.0

    name = "drive_route"
    parameters: ClassVar[dict] = {"duration": (0.1, 120, 60), "style": ("bold", "careful")}
    prompt = (
        "Follow a visible GPS route in a vehicle. Done with arrived after small, falling distances and "
        "route loss, or with time-limit. Fails on lost route, no progress, dead-or-held car, "
        "exhausted recovery or a picture it cannot read (map-unreadable)."
    )
    # The failed town drives made 0-10 m in 25-37 s; useful drives made 350-480 m/min.
    progress_window = 20.0
    progress_gap = 10.0  # The growing-distance town drive has a 7.6 s OCR gap.
    progress_metres = 20.0  # Two kilometre HUD increments, above quantisation noise.
    # The route vanished with 27 m and 23 m still printed on the two recorded arrivals.
    arrival_metres = 50.0
    arrival_age = 5.0  # Includes the driver's two seconds of confirmed route absence.

    def __init__(self, args: dict, *, driver=None):
        super().__init__(args, driver=driver)
        if driver is None:
            from .cli import drive_config

            self.driver = Driver(drive_config([f"style={self.args.get('style', 'bold')}"]))
        self.start_distance = self.end_distance = self.distance_time = None
        self._distances = deque()
        self._now = self._previous_time = None
        self._moving_time = 0.0
        self._was_moving = False
        self._water_seen = None
        self._water_time = 0.0
        self._foot_since = None

    # A figure the judge sees on foot over a sound flat map, for this long: nobody drives. The map
    # lies flat and sound in no car, and on 13 November, 17:20, a drive planned on the judge's word
    # about the pause map stood for 30 s on foot beside a car, with a neutral pad and no end.
    FOOT_SECONDS = 2.0

    def _afoot(self, observation, now) -> bool:
        reading = observation.reading
        if (
            player_mode(observation) == "foot"
            and reading.minimap == "flat"
            and not reading.corrupt
            and reading.confidence >= 0.45
        ):
            if self._foot_since is None:
                self._foot_since = now
            return now - self._foot_since >= self.FOOT_SECONDS
        self._foot_since = None
        return False

    # Water under the arrow and a car known to stand, for this long in all: it has gone in. A car that
    # moves is on a bridge, in a ford or on the beach, where the map shows water round the arrow too.
    WATER_SECONDS = 2.0

    def _sunk(self, observation, now) -> bool:
        previous, self._water_seen = self._water_seen, now
        if observation.frame is None or observation.reading.corrupt is not False:
            return False  # a damaged picture neither shows water nor clears it
        from . import terrain
        from .foot import hud_crop

        land = terrain.read(hud_crop(observation.frame))
        if land is None or observation.moving is None:
            return False  # not known: neither counted nor cleared
        if not land.under_water or observation.moving is True:
            self._water_time = 0.0
            return False
        if previous is not None:
            self._water_time += min(max(0.0, now - previous), self.driver.config.max_step_time)
        return self._water_time >= self.WATER_SECONDS

    def _result(self, *, pad=NEUTRAL_PAD, status="running", reason=None):
        return self.Result(
            pad,
            status,
            reason,
            self.start_distance,
            self.end_distance,
            None if self.distance_time is None else self._now - self.distance_time,
            self.driver.flagged_time,
        )

    def stop(self, reason="interrupted") -> SkillResult:
        self.finished = self._result(status="failed", reason=reason)
        return self.finished

    def _distance(self, observation):
        from .drive import _number

        reading, now = observation.reading, observation.time
        distance, at = _number(reading.gps_distance), _number(reading.gps_time)
        if (
            reading.corrupt
            or reading.minimap != "tilted"
            or distance is None
            or at is None
            or not 0 <= distance < 100000
            or not 0 <= now - at <= self.driver.config.gps_stale
            or (self.distance_time is not None and at <= self.distance_time)
        ):
            return
        if self.distance_time is not None and (
            at - self.distance_time > self.progress_gap
            or abs(distance - self.end_distance)
            > self.driver.config.gps_max_speed * (at - self.distance_time) + 20
        ):
            # A reroute or OCR gap starts a new progress window, never an arrival trend.
            self._distances.clear()
        if self.start_distance is None:
            self.start_distance = distance
        self.end_distance, self.distance_time = distance, at
        self._distances.append((at, distance, self._moving_time))
        while len(self._distances) > 1 and at - self._distances[1][0] >= self.progress_window:
            self._distances.popleft()

    def _route_end(self):
        from itertools import pairwise

        if self.distance_time is None or self._now - self.distance_time > self.arrival_age:
            return self.stop("route-lost-unknown")
        if self.end_distance > self.arrival_metres:
            return self.stop("route-lost-far")
        close = [(t, d) for t, d, _ in self._distances if self.distance_time - t <= 5]
        if (
            len(close) >= 3
            and close[-1][0] - close[0][0] >= 0.5
            and all(d <= 2 * self.arrival_metres for _, d in close)
            and close[0][1] - close[-1][1] >= 3
            and all(b[1] <= a[1] + 1 for a, b in pairwise(close))
        ):
            self.finished = self._result(status="done", reason="arrived")
            return self.finished
        return self.stop("route-lost-unknown")

    def step(self, observation: Observation) -> SkillResult:
        from .drive import _number

        if self.finished is not None:
            return self.finished
        now = _number(observation.time)
        if now is None:
            return self.stop("invalid-clock")
        if self._previous_time is not None and now < self._previous_time:
            return self.stop("clock-reversed")
        self._now = now
        if self.started is None:
            self.started = now
        moving = observation.moving is True and not observation.reading.corrupt
        if moving and self._was_moving and self._previous_time is not None:
            self._moving_time += min(now - self._previous_time, self.driver.config.max_step_time)
        self._was_moving, self._previous_time = moving, now
        try:
            self._distance(observation)
            if now - self.started >= self.limit:
                self.finished = self._result(status="done", reason="time-limit")
                return self.finished
            if self._sunk(observation, now):
                return self.stop("dead-or-held")
            if self._afoot(observation, now):
                return self.stop("on-foot")
            from .avoid import STALE, passing_side

            command = self.driver.step(
                observation.reading,
                now,
                observation.moving,
                speed=observation.reading.gps_speed,
                ahead=waits_behind(observation.objects, observation.objects_time, now),
                bypass_side=passing_side(observation.objects, observation.objects_time, now),
                boxes_fresh=(observation.objects_time is None and not observation.objects)
                or (observation.objects_time is not None and 0 <= now - observation.objects_time <= STALE),
            )
            if command.state == "route-gone":
                if command.brake:
                    return self._result(pad=Pad.from_command(command))
                return self._route_end()
            if command.state in ("dead-or-held", "failed-recovery", "map-unreadable"):
                return self.stop(command.state)
            if len(self._distances) >= 3 and self.distance_time is not None:
                first, last = self._distances[0], self._distances[-1]
                if (
                    now - self.distance_time <= self.driver.config.gps_stale
                    and last[0] - first[0] >= self.progress_window
                    and last[2] - first[2] >= self.progress_window / 2
                    and first[1] - last[1] < self.progress_metres
                ):
                    return self.stop("no-progress")
            return self._result(pad=self._around(command, observation))
        except Exception as exc:
            return self.stop(f"skill-error: {type(exc).__name__}")


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
    prompt = (
        "Walk on foot: x is right, y is down (forward is negative y); optional sprint. When the figure "
        "gets nowhere it walks round to either side and tries again; fails stuck after four ways round."
    )


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
from .camera import SetFarView  # noqa: E402
from .combat import Fight, Melee  # noqa: E402
from .descend import Descend  # noqa: E402
from .getaway import GetAway  # noqa: E402
from .leave import LeaveBuilding  # noqa: E402
from .level import LevelCamera  # noqa: E402
from .place import DoPrompt, UsePlace  # noqa: E402
from .punch import Punch  # noqa: E402
from .pursuit import DriveToBlip  # noqa: E402
from .switch import SwitchCharacter  # noqa: E402
from .vehicle_entry import EnterVehicle  # noqa: E402
from .walkto import WalkTo as WalkToPoint  # noqa: E402
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
        LevelCamera,
        SetFarView,
        WalkRoad,
        WalkToPoint,
        GetAway,
        UsePlace,
        DoPrompt,
        LeaveBuilding,
        Descend,
        SwitchCharacter,
        DriveToBlip,
    )
}


def make_skill(call, *, driver=None):
    cls = REGISTRY[call.name]
    skill = cls(call.args, driver=driver) if call.name == "drive_route" else cls(call.args)
    skill.call_args = dict(call.args)
    return skill


class SkillRunner:
    def __init__(self, *, driver_factory=Driver):
        self.driver_factory = driver_factory
        self.queue = deque()
        self.active = None
        self.last = None
        self.release_pending = False
        self.completed = False
        self.road_reached = False
        self.route_seen = False
        # The skills a session begins with. One that fails leaves the queue alone: whatever
        # follows it, the next opening skill and then the head's first plan, still runs.
        self.opening: tuple = ()
        self.opening_failures: list[dict] = []

    def replace(self, calls: tuple["SkillCall", ...], *, opening: bool = False) -> Pad:
        # Construct all skills before touching the existing plan.
        replacements = [
            make_skill(call, driver=self.driver_factory() if call.name == "drive_route" else None)
            for call in calls
        ]
        self.stop("replaced")
        self.queue.extend(replacements)
        self.opening = tuple(replacements) if opening else ()
        self.release_pending = True
        return NEUTRAL_PAD

    def stop(self, reason="interrupted") -> Pad:
        if self.active is not None:
            result = self.active.stop(reason)
            self.last = {
                "name": self.active.name,
                **({"road_reached": self.road_reached} if self.active.name == "walk_road" else {}),
                **({"route_seen": self.route_seen} if self.active.name == "drive_route" else {}),
                "status": result.status,
                "reason": result.reason,
                "queue": [],
                "queue_disposition": "cleared" if self.queue else "empty",
                "dropped": [skill.name for skill in self.queue],
            }
        self.active = None
        self.queue.clear()
        self.opening = ()
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
            self.route_seen = False
            self.road_reached = False
        result = self.active.step(observation)
        self.route_seen |= self.active.name == "drive_route" and observation.reading.route in {
            "yellow",
            "purple",
        }
        road_since = getattr(self.active, "on_road_since", None)
        self.road_reached = (
            self.active.name == "walk_road"
            and road_since is not None
            and observation.time - road_since >= self.active.ON_ROAD_SECONDS
        )
        if result.status != "running":
            if result.status == "failed" and any(self.active is skill for skill in self.opening):
                # Not the plan's failure: it is logged, and neither the head nor the queue hears of it.
                self.opening_failures.append(
                    {"name": self.active.name, "reason": result.reason, "queue": [s.name for s in self.queue]}
                )
                self.active = None
                self.completed = False
                return result
            queued = [skill.name for skill in self.queue]
            failed = result.status == "failed"
            self.last = {
                "name": self.active.name,
                **({"road_reached": self.road_reached} if self.active.name == "walk_road" else {}),
                **({"route_seen": self.route_seen} if self.active.name == "drive_route" else {}),
                "status": result.status,
                "reason": result.reason,
                "queue": [] if failed else queued,
                "queue_disposition": ("cleared" if failed else "kept") if queued else "empty",
                "dropped": queued if failed else [],
            }
            self.active = None
            if result.status == "failed":
                self.queue.clear()
            self.completed = not self.queue
        return result

    def describe(self):
        if self.active is None and self.queue:
            return {
                **(self.last or {"name": self.queue[0].name, "status": "queued", "reason": None}),
                "pending": [skill.name for skill in self.queue],
            }
        if self.active is not None:
            guard = getattr(self.active, "guard", None)
            return {
                "name": self.active.name,
                # What it was called with, so that a head can tell the same call from another one.
                "args": dict(getattr(self.active, "call_args", None) or {}),
                **({"road_reached": self.road_reached} if self.active.name == "walk_road" else {}),
                **({"route_seen": self.route_seen} if self.active.name == "drive_route" else {}),
                "status": "running",
                "reason": guard.diagnostic() if guard is not None else None,
                "queue": [skill.name for skill in self.queue],
            }
        return self.last

    @property
    def has_plan(self):
        return self.active is not None or bool(self.queue)

    @property
    def uninterruptible(self):
        """A move that cannot be cut short is running, or is the next thing to run."""
        skill = self.active if self.active is not None else (self.queue[0] if self.queue else None)
        return getattr(skill, "uninterruptible", False)

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
