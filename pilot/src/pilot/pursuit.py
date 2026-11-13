"""Drive towards a colored radar marker, without a GPS route or button presses."""

import math
from typing import ClassVar

from pilot import terrain
from pilot.avoid import Avoider, waits_behind
from pilot.contract import Observation, Pad, SkillResult, player_mode
from pilot.drive import LATCHED, DriveConfig, Driver
from pilot.foot import hud_crop
from pilot.getaway import _angle, _towards


class DriveToBlip:
    name = "drive_to_blip"
    parameters: ClassVar = {
        "color": ("blue", "red", "yellow"),
        "mode": ("reach", "follow", "catch"),
        "duration": (1.0, 300.0, 120.0),
    }
    prompt = (
        "Drive towards a colored minimap marker without a route. Reach a place, follow at a distance, "
        "or catch a car. Needs a seated driver and a visible minimap. Fails if the marker disappears, "
        "the car stays held, water is entered, the driver leaves, another screen persists, or time runs out."
    )

    # Interior marker distances in the yacht and van recordings, in map pixels.
    FOLLOW_DISTANCE = 27.0
    FOLLOW_BAND = (16.0, 40.0)
    UNDER_ARROW = 8.0

    def __init__(self, args: dict):
        if not isinstance(args, dict) or set(args) - self.parameters.keys():
            raise ValueError("invalid drive_to_blip arguments")
        self.color = args.get("color", "blue")
        self.mode = args.get("mode", "reach")
        if self.color not in self.parameters["color"] or self.mode not in self.parameters["mode"]:
            raise ValueError("invalid color or mode")
        duration = args.get("duration", 120.0)
        if (
            isinstance(duration, bool)
            or not isinstance(duration, (int, float))
            or not math.isfinite(duration)
        ):
            raise ValueError("duration must be finite")
        self.duration = max(1.0, min(300.0, float(duration)))
        self.driver = Driver(DriveConfig(unknown_throttle=1.0, recovery_throttle=0.6))
        self.avoider = Avoider()
        self.finished: SkillResult | None = None
        self.started: float | None = None
        self.last_time: float | None = None
        self.seen: float | None = None
        self.bearing: float | None = None
        self.distance: float | None = None
        self.range_rate = 0.0
        self.border = False
        self.behind_since: float | None = None
        self.reached_since: float | None = None
        self.blocked_since: float | None = None
        self.land: terrain.Terrain | None = None
        self.land_time: float | None = None
        self.heading = 0.0
        self.state = "start"
        self.holding = False
        self.uncertain: dict[str, float] = {}

    def stop(self, reason: str = "interrupted") -> SkillResult:
        if self.finished is None:
            self.finished = SkillResult(status="failed", reason=reason)
        return self.finished

    def step(self, observation: Observation) -> SkillResult:
        if self.finished is not None:
            return self.finished
        try:
            return self._step(observation)
        except (AttributeError, TypeError, ValueError, OverflowError) as exc:
            return self.stop(f"skill-error: {type(exc).__name__}")

    def _step(self, obs: Observation) -> SkillResult:
        now = float(obs.time)
        if not math.isfinite(now) or (self.last_time is not None and now < self.last_time):
            return self.stop("invalid-time")
        self.last_time = now
        if self.started is None:
            self.started = now
        if now - self.started >= self.duration:
            return self.stop("time-limit")
        suspect = f"screen-{obs.hud.screen}" if obs.hud is not None and obs.hud.screen != "game" else None
        if suspect is None and not obs.reading.corrupt and player_mode(obs) == "foot":
            suspect = "on-foot"
        for reason in tuple(self.uncertain):
            if reason != suspect and reason != "water":
                self.uncertain.pop(reason)
        if suspect:
            self.reached_since = None
            since = self.uncertain.setdefault(suspect, now)
            return self.stop(suspect) if now - since >= 1.0 else SkillResult()

        reading = obs.reading
        arrow = reading.arrow
        readable = (
            reading.minimap == "tilted" and not reading.corrupt and arrow is not None and math.isfinite(arrow)
        )
        if readable and obs.frame is not None:
            self.land = terrain.read(hud_crop(obs.frame))
            self.land_time = now
        if self.land_time is None or now - self.land_time > 0.6:
            self.land = None
        if self.land is not None and self.land.under_water:
            self.reached_since = None
            since = self.uncertain.setdefault("water", now)
            return self.stop("water") if now - since >= 1.0 else SkillResult()
        self.uncertain.pop("water", None)

        candidates = (
            [b for b in reading.blips if b.color == self.color and math.isfinite(b.x) and math.isfinite(b.y)]
            if readable
            else []
        )
        fresh = bool(candidates)
        if fresh:
            # Keep the nearest bearing when several same-color markers exist.
            blip = min(
                candidates,
                key=lambda b: (
                    abs(_angle(math.degrees(math.atan2(b.x, b.y)) - self.bearing))
                    if self.bearing is not None
                    else math.hypot(b.x, b.y)
                ),
            )
            bearing = math.degrees(math.atan2(blip.x, blip.y))
            distance = math.hypot(blip.x, blip.y)
            gap = now - self.seen if self.seen is not None else 0.0
            if self.bearing is None or gap > 2.0:
                self.bearing = bearing
                self.range_rate = 0.0
            else:
                alpha = 1.0 - math.exp(-max(gap, 0.001) / 0.2)
                self.bearing = _angle(self.bearing + alpha * _angle(bearing - self.bearing))
                if gap > 0 and not blip.border and not self.border:
                    rate = (distance - self.distance) / gap
                    # Zoom changes are discontinuities, not a target accelerating.
                    if abs(rate) < 80:
                        self.range_rate += alpha * (rate - self.range_rate)
                    else:
                        self.range_rate = 0.0
            self.distance, self.border, self.seen = distance, blip.border, now

        age = now - (self.seen if self.seen is not None else self.started)
        if age >= 5.0:
            return self.stop("blip-gone")
        if not fresh:
            self.reached_since = None
        if self.bearing is None or age > 2.0 or not readable:
            # A damaged map may still use the last valid arrow for up to 2 seconds.
            if self.bearing is None or age > 2.0:
                self.state = "blip-unread"
                self.holding = True
                return SkillResult()
            arrow = self.last_arrow
        else:
            self.last_arrow = arrow

        if not fresh and self.mode == "reach" and self.distance <= self.UNDER_ARROW:
            self.state = "arrival-unread"
            self.holding = True
            return SkillResult()

        error = _angle(self.bearing - arrow)
        if abs(error) > 100:
            if self.behind_since is None:
                self.behind_since = now
        else:
            self.behind_since = None
        turning = self.behind_since is not None and now - self.behind_since > 1.0
        heading = self.bearing
        if self.land is not None and not turning:
            road = self.land.road_towards(heading, 45.0)
            if road is not None and (self.border or self.distance > 14):
                heading = road
        water_detour = False
        if self.land is not None and self.land.water_within(heading, 18.0, 45.0) is not None:
            alternatives = [
                _angle(heading + offset)
                for delta in range(20, 181, 20)
                for offset in (delta, -delta)
                if self.land.water_within(_angle(heading + offset), 18.0, 45.0) is None
            ]
            if not alternatives:
                self.state = "water-blocked"
                self.holding = True
                if self.blocked_since is None:
                    self.blocked_since = now
                if now - self.blocked_since >= 4.0:
                    return self.stop("vehicle-held")
                return SkillResult(pad=Pad(l2=0.25 if obs.moving is True else 0.0))
            heading = alternatives[0]
            water_detour = True
        self.blocked_since = None
        self.heading = _angle(heading - arrow)

        if self.mode == "reach" and fresh and not self.border and self.distance <= self.UNDER_ARROW:
            if obs.moving is True:
                self.reached_since = None
                self.state = "arriving"
                self.holding = True
                # A full reverse trigger can skip the observed standstill window.
                return SkillResult(pad=Pad(l2=0.25 if self.range_rate <= 0 else 0.0))
            if obs.moving is None:
                self.reached_since = None
                self.state = "arriving"
                self.holding = True
                return SkillResult()
            if self.reached_since is None:
                self.reached_since = now
            self.state = "arriving"
            self.holding = True
            if now - self.reached_since >= 0.5 - 1e-9:
                self.finished = SkillResult(status="done", reason="reached")
                return self.finished
            return SkillResult()
        self.reached_since = None

        command = self.driver.step(
            _towards(heading, arrow),
            now,
            True if self.holding else obs.moving,
            ahead=waits_behind(obs.objects, obs.objects_time, now),
        )
        if command.state in LATCHED:
            return self.stop("vehicle-held")
        around = self.avoider.step(obs.objects, obs.objects_time, now)
        pedal, brake = command.throttle, command.brake
        recovering = command.state != "follow"
        if not recovering and not self.border and not turning:
            if self.mode == "follow":
                control = 0.45 + 0.045 * (self.distance - self.FOLLOW_DISTANCE) + 0.18 * self.range_rate
                pedal = min(pedal, max(0.0, min(1.0, control)))
                brake = max(brake, min(1.0, max(0.0, -control)))
            elif self.mode == "reach":
                pedal = min(pedal, max(0.12, min(1.0, (self.distance - 8) / 38)))
                if self.distance < 20 and self.range_rate < -7:
                    pedal, brake = 0.0, max(brake, 0.6)
        if water_detour:
            pedal = min(pedal, 0.3)
        if self.land is not None:
            course = self.land.water_within(arrow, 25.0, 45.0)
            if course is not None:
                pedal = min(pedal, 0.2)
                if course <= 22:
                    pedal, brake = 0.0, 1.0
        if around.urgent:
            pedal, brake = 0.0, max(brake, 1.0)
        else:
            pedal *= around.pedal
        self.holding = not recovering and (pedal < 0.1 or brake > 0.1)
        self.state = "turn-around" if turning else command.state
        return SkillResult(
            pad=Pad(left=(max(-1.0, min(1.0, command.steer + around.steer)), 0.0), r2=pedal, l2=brake)
        )
