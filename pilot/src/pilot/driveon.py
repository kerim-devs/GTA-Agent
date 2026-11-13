"""Follow the road while a waypoint has no visible GPS route."""

from math import isfinite
from typing import ClassVar

from pilot.contract import Hud, Observation, Reading, SkillResult, player_mode
from pilot.drive import DriveConfig, Driver
from pilot.getaway import GetAway


class DriveOn(GetAway):
    name = "drive_on"
    parameters: ClassVar = {"duration": (10.0, 120.0, 30.0), "minimap": ("on", "off")}
    prompt = (
        "In a vehicle with a waypoint but no GPS route: follow the road at half throttle, "
        "around traffic. Done route-back after a sound yellow or purple route for 1 s, "
        "or time-limit after 30 s by default. Fails on-foot, stars-lit, vehicle-held, "
        "water or a non-game screen. Then try drive_route."
    )
    THROTTLE = 0.5
    TURN_THROTTLE = 0.3
    ROUTE_SECONDS = 1.0
    STAR_SECONDS = 0.5

    def __init__(self, args: dict):
        if not isinstance(args, dict) or set(args) - self.parameters.keys():
            raise ValueError("drive_on accepts only duration and minimap")
        super().__init__(args)
        self.driver = Driver(DriveConfig(unknown_throttle=0.5, recovery_throttle=0.5))
        self.route_since: float | None = None
        self.star_since: float | None = None

    def _step(self, obs: Observation) -> SkillResult:
        now = obs.time
        if isinstance(now, bool) or not isinstance(now, (int, float)) or not isfinite(now):
            return self.stop("invalid-clock")
        if self.last_time is not None and now < self.last_time:
            return self.stop("clock-reversed")
        gap = self.last_time is not None and now - self.last_time > 0.5
        self.last_time = now
        if self.started is None:
            self.started = now
        if now - self.started >= self.limit:
            return self._done("time-limit")
        if gap:
            self.route_since = self.star_since = None
            self.foot_since = self.screen_since = self.water_since = None

        hud = obs.hud
        if not isinstance(hud, Hud) or not isinstance(hud.screen, str):
            self.route_since = self.star_since = self.screen_since = None
            if self.hud_since is None:
                self.hud_since = now
            if now - self.hud_since >= self.HUD_SECONDS:
                return self.stop("no-hud; the stars cannot be read")
            return SkillResult()
        ended = self._screen(obs, now)
        if ended is not None:
            self.route_since = self.star_since = None
            return ended
        wanted = hud.wanted
        if not isinstance(wanted, int) or isinstance(wanted, bool) or wanted < 0:
            self.route_since = self.star_since = None
            if self.hud_since is None:
                self.hud_since = now
            if now - self.hud_since >= self.HUD_SECONDS:
                return self.stop("no-hud; the stars cannot be read")
            return SkillResult()
        self.hud_since = None
        if wanted > 0:
            self.route_since = None
            if self.star_since is None:
                self.star_since = now
            if now - self.star_since >= self.STAR_SECONDS:
                return self.stop("stars-lit")
            return SkillResult()
        self.star_since = None

        reading = obs.reading
        mode = player_mode(obs) if isinstance(reading, Reading) else obs.mode
        if mode != "vehicle":
            self.route_since = None
            if mode == "foot":
                if self.foot_since is None:
                    self.foot_since = now
                if now - self.foot_since >= self.FOOT_SECONDS:
                    return self.stop("on-foot")
            else:
                self.foot_since = None
            return SkillResult()
        self.foot_since = None
        if (
            not isinstance(reading, Reading)
            or reading.corrupt is not False
            or reading.minimap != "tilted"
            or isinstance(reading.arrow, bool)
            or not isinstance(reading.arrow, (int, float))
            or not isfinite(reading.arrow)
            or isinstance(reading.confidence, bool)
            or not isinstance(reading.confidence, (int, float))
            or not isfinite(reading.confidence)
            or not 0.5 <= reading.confidence <= 1.0
        ):
            self.route_since = self.water_since = None
            return SkillResult()

        self._look(obs, now)
        if self.terrain is not None and self.terrain.under_water:
            self.route_since = None
            if self.water_since is None:
                self.water_since = now
            if now - self.water_since >= self.WATER_SECONDS:
                return self.stop("water")
            return SkillResult()
        self.water_since = None
        if self._sound_route(reading):
            if self.route_since is None:
                self.route_since = now
            if now - self.route_since >= self.ROUTE_SECONDS:
                return self._done("route-back")
        else:
            self.route_since = None
        return self._drive(obs, now)

    @staticmethod
    def _sound_route(reading: Reading) -> bool:
        return (
            reading.route in {"yellow", "purple"}
            and all(
                isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)
                for value in (reading.bearing, reading.confidence)
            )
            and 0.5 <= reading.confidence <= 1.0
        )
