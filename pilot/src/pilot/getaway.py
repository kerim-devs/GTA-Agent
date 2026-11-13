"""Getting away: with stars lit, drive off at once, with no map and no destination.

Kerim on 12 November, as the player: with the police behind you nobody enters a destination. You drive,
right, left, wherever there is room; where the country is open across the fields, up the hills, and
sooner or later you are on a road again; only never into water. So this skill never touches the map
screen or any menu, presses no button at all, and drives from its first tick: full throttle less what
the avoider takes off, away from the police where the minimap shows them and otherwise straight on,
along a road while one leads roughly that way and across country when none does, around what the
detector sees ahead, and away from water before it is reached. What it takes from the minimap (roads,
water and the police's markers, `terrain.py`) sits behind one switch, since by rumour the minimap of
GTA VI no longer shows the police; without it the skill drives on the detector and the recoveries alone.

A car that the picture says stands while the pedal is down is freed by the driver's own recoveries
(`drive.Driver`), fed a route that points where this skill wants to go.
"""

from __future__ import annotations

from math import atan2, cos, degrees, isfinite, radians, sin
from typing import ClassVar

from pilot import terrain
from pilot.avoid import Avoider
from pilot.contract import Observation, Pad, Reading, SkillResult, player_mode
from pilot.drive import LATCHED, DriveConfig, Driver
from pilot.foot import hud_crop


def _clip(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _angle(value: float) -> float:
    return (value + 180.0) % 360.0 - 180.0


class GetAway:
    name = "get_away"
    parameters: ClassVar = {"duration": (10.0, 300.0, 120.0), "minimap": ("on", "off")}
    prompt = (
        "With stars lit in a vehicle: drive off at once, no map, no destination. Full throttle, along a "
        "road or across open ground, away from police markers and water, around traffic; frees a held "
        "car itself. Done when no star has been lit for 3 s. Fails vehicle-held (take another), on-foot, "
        "water, wasted, busted, or time-limit. minimap=off drives on the detector alone."
    )

    # The star row has to say zero this long, with no lit star read in between, before the police are
    # taken as gone. The card's measure: done only after three seconds without a star.
    CLEAR_SECONDS = 3.0
    # One odd tick decides nothing (docs/tasks/README.md): the minimap reader calls a clean picture
    # damaged for a tick or two about once a second and the judge's word flickers at a change.
    FOOT_SECONDS = 1.5  # the figure read on foot this long has left the vehicle
    SCREEN_SECONDS = 1.0  # a screen other than the game this long ends the drive
    BANNER_SECONDS = 0.5  # wasted or busted this long ends it at once
    HUD_SECONDS = 2.0  # no HUD reading at all this long: the stars cannot be told
    WATER_SECONDS = 1.0  # the arrow on water this long: the car is in it
    # Kerim's 20 escapes (report): R2 at 0.9 or more a median 69 % of the time and otherwise mostly off,
    # so the pedal is down; it comes up in a sharp turn, where full throttle spins the car.
    THROTTLE = 1.0
    TURN_THROTTLE = 0.5  # the pedal at a heading error of TURN_FULL degrees and more
    TURN_FROM, TURN_FULL = 30.0, 90.0
    # The heading. Picture degrees, as everything the minimap gives: 0 is where the camera looks.
    ROAD_WITHIN = 45.0  # a road this close to the wanted heading leads "roughly that way"
    MAX_TURN = 100.0  # the wanted heading stays this close to the car's; a U-turn only away from water
    FAN = 10.0  # degrees between the headings tried when one is blocked by water
    STICKY = 20.0  # a road this close to the last one chosen is kept, so that a fork does not flap
    # Water: in crop pixels from the arrow, in a corridor of WATER_SPREAD degrees either side of a heading.
    # The map shows about 1 to 3.7 m a pixel depending on the speed (sim.py's table), so 34 px is 35 to
    # 125 m, two to five seconds at the speeds of Kerim's escapes.
    WATER_NEAR = 34.0
    WATER_SPREAD = 25.0
    WATER_THROTTLE = 0.3  # the pedal with water within WATER_NEAR on the car's own course
    WATER_SLOW = 18.0  # and within this the brake
    POLICE_SECONDS = 2.0  # the police's markers flash; one seen this recently still counts
    TERRAIN_SECONDS = 0.6  # a terrain reading is used this long after it was read

    def __init__(self, args: dict):
        if not isinstance(args, dict) or set(args) - self.parameters.keys():
            raise ValueError("get_away accepts only duration and minimap")
        low, high, default = self.parameters["duration"]
        duration = args.get("duration", default)
        if (
            isinstance(duration, bool)
            or not isinstance(duration, (int, float))
            or (isinstance(duration, float) and not isfinite(duration))
        ):
            raise ValueError("duration must be a finite number")
        self.limit = float(max(low, min(high, duration)))
        switch = args.get("minimap", self.parameters["minimap"][0])
        if not isinstance(switch, str) or switch not in self.parameters["minimap"]:
            raise ValueError("minimap must be one of: on, off")
        self.use_minimap = switch == "on"
        # The driver's recoveries, with a pedal for the way out that is not the crawl it uses when it
        # cannot read the speed: without a route there is no GPS distance and so never a speed.
        self.driver = Driver(DriveConfig(unknown_throttle=0.6, recovery_throttle=0.6))
        self.avoider = Avoider()
        self.finished: SkillResult | None = None
        self.started: float | None = None
        self.last_time: float | None = None
        self.clear = 0.0  # seconds the star row has said zero, tick after tick
        self.last_wanted: int | None = None
        self.stars_seen = False
        self.foot_since: float | None = None
        self.screen_since: float | None = None
        self.hud_since: float | None = None
        self.water_since: float | None = None
        self.arrow = 0.0
        self.terrain: terrain.Terrain | None = None
        self.terrain_at: float | None = None
        self.police: tuple[float, ...] = ()  # relative to the car's heading, degrees
        self.police_at: float | None = None
        self.choice: float | None = None  # the last heading chosen, relative to the car
        self.heading = 0.0  # the heading of this tick, picture degrees, for the log and the tests
        self.state = "start"

    # ------------------------------------------------------------------ ends
    def stop(self, reason: str = "interrupted") -> SkillResult:
        if self.finished is None:
            self.finished = SkillResult(status="failed", reason=reason)
        return self.finished

    def _done(self, reason: str) -> SkillResult:
        self.finished = SkillResult(status="done", reason=reason)
        return self.finished

    def step(self, observation: Observation) -> SkillResult:
        if self.finished is not None:
            return self.finished
        try:
            return self._step(observation)
        except (AttributeError, TypeError, ValueError, OverflowError) as exc:
            return self.stop(f"skill-error: {type(exc).__name__}")

    # ------------------------------------------------------------------ one tick
    def _step(self, obs: Observation) -> SkillResult:
        now = obs.time
        if isinstance(now, bool) or not isinstance(now, (int, float)) or not isfinite(now):
            return self.stop("invalid-clock")
        if self.last_time is not None and now < self.last_time:
            return self.stop("clock-reversed")
        if self.started is None:
            self.started = now
        dt = 0.0 if self.last_time is None else min(now - self.last_time, 0.5)
        self.last_time = now
        if now - self.started >= self.limit:
            return self.stop("time-limit; stars still lit" if self.stars_seen else "time-limit")

        ended = self._stars(obs, now, dt)
        if ended is not None:
            return ended
        ended = self._screen(obs, now)
        if ended is not None:
            return ended
        if player_mode(obs) == "foot":
            # R2 on foot fires whatever is in the hand: nothing is pressed until the vehicle is back.
            if self.foot_since is None:
                self.foot_since = now
            if now - self.foot_since >= self.FOOT_SECONDS:
                return self.stop("on-foot")
            self.state = "foot?"
            return SkillResult()
        self.foot_since = None
        self._look(obs, now)
        if self.terrain is not None and self.terrain.under_water:
            if self.water_since is None:
                self.water_since = now
            if now - self.water_since >= self.WATER_SECONDS:
                return self.stop("water")
        else:
            self.water_since = None
        return self._drive(obs, now)

    def _stars(self, obs: Observation, now: float, dt: float) -> SkillResult | None:
        hud = obs.hud
        if hud is None:
            if self.hud_since is None:
                self.hud_since = now
            if now - self.hud_since >= self.HUD_SECONDS:
                return self.stop("no-hud; the stars cannot be read")
            return None
        self.hud_since = None
        wanted = hud.wanted
        wanted = wanted if isinstance(wanted, int) and not isinstance(wanted, bool) else None
        if wanted is not None and wanted > 0:
            self.clear = 0.0
            self.stars_seen = True
        elif wanted == 0 and self.last_wanted == 0:
            # Only a zero after a zero counts; a row the reader cannot read neither clears nor relights.
            self.clear += dt
        if wanted is not None:
            self.last_wanted = wanted
        if self.clear >= self.CLEAR_SECONDS:
            return self._done("stars-gone")
        return None

    def _screen(self, obs: Observation, now: float) -> SkillResult | None:
        screen = obs.hud.screen if obs.hud is not None else "game"
        if screen == "game" or not isinstance(screen, str):
            self.screen_since = None
            return None
        if self.screen_since is None:
            self.screen_since = now
        lasted = now - self.screen_since
        if screen in ("wasted", "busted") and lasted >= self.BANNER_SECONDS:
            return self.stop(screen)
        if lasted >= self.SCREEN_SECONDS:
            return self.stop(f"screen-{screen}")
        self.state = f"screen-{screen}?"
        return SkillResult()

    # ------------------------------------------------------------------ what the picture gives
    def _look(self, obs: Observation, now: float) -> None:
        reading = obs.reading if isinstance(obs.reading, Reading) else None
        arrow = reading.arrow if reading is not None else None
        if isinstance(arrow, (int, float)) and not isinstance(arrow, bool) and isfinite(arrow):
            self.arrow = _angle(float(arrow))
        if not self.use_minimap:
            return
        damaged = reading is None or reading.corrupt is not False
        if not damaged:
            found = terrain.read(hud_crop(obs.frame)) if obs.frame is not None else None
            if found is not None:
                self.terrain, self.terrain_at = found, now
            police = terrain.police(reading)
            if police:
                self.police, self.police_at = tuple(_angle(p - self.arrow) for p in police), now
        if self.terrain_at is not None and now - self.terrain_at > self.TERRAIN_SECONDS:
            self.terrain = self.terrain_at = None
        if self.police_at is not None and now - self.police_at > self.POLICE_SECONDS:
            self.police, self.police_at = (), None

    def choose(self) -> tuple[float, str]:
        """The heading for this tick in picture degrees, and why: "straight", "away", "road", "country",
        "water"."""
        arrow = self.arrow
        wanted, why = 0.0, "straight"  # relative to the car
        if self.police:
            x = sum(-sin(radians(p)) for p in self.police)
            y = sum(-cos(radians(p)) for p in self.police)
            if abs(x) + abs(y) > 1e-6:
                wanted, why = _clip(degrees(atan2(x, y)), -self.MAX_TURN, self.MAX_TURN), "away"
        land = self.terrain
        if land is None:
            self.choice = wanted
            return _angle(arrow + wanted), why

        def wet(relative: float) -> float | None:
            return land.water_within(arrow + relative, self.WATER_SPREAD, self.WATER_NEAR)

        roads = [_angle(b - arrow) for b, width in land.roads if abs(_angle(b - arrow)) <= self.MAX_TURN]
        # A pursuer does not make the roadside a useful escape. Keep the forward
        # road until there is a real choice of onward roads at a junction.
        forward = [r for r in roads if abs(r) <= self.ROAD_WITHIN]
        road = min(forward, key=abs, default=None)
        if len(roads) >= 2:
            road = min(roads, key=lambda r: abs(_angle(r - wanted)))
            if self.choice is not None:
                kept = [r for r in roads if abs(_angle(r - self.choice)) <= self.STICKY]
                if kept and abs(_angle(self.choice - wanted)) <= self.ROAD_WITHIN:
                    road = min(kept, key=lambda r: abs(_angle(r - self.choice)))
        elif road is None and roads:
            road = min(roads, key=abs)
        heading, why = (road, "road") if road is not None else (wanted, why if why == "away" else "country")
        if wet(heading) is not None:
            # Water ahead within reach: the nearest heading round it that is dry, along a dry road if one
            # leads roughly that way; with water all round, the heading where it lies farthest.
            fan = [float(a) for a in range(-180, 180, int(self.FAN))]
            dry = [a for a in fan if wet(a) is None]
            if dry:
                heading = min(dry, key=lambda a: abs(_angle(a - heading)))
                along = [r for r in roads if wet(r) is None and abs(_angle(r - heading)) <= self.ROAD_WITHIN]
                heading = min(along, key=lambda r: abs(_angle(r - heading)), default=heading)
            else:
                heading = max(fan, key=lambda a: wet(a) or 0.0)
            why = "water"
        self.choice = heading
        return _angle(arrow + heading), why

    # ------------------------------------------------------------------ the hands
    def _drive(self, obs: Observation, now: float) -> SkillResult:
        heading, why = self.choose()
        self.heading = heading
        command = self.driver.step(_towards(heading, self.arrow), now, obs.moving, speed=None)
        if command.state in LATCHED:
            return self.stop("vehicle-held")
        # Water on the car's own course: the pedal comes up within reach, and close to it the brake goes
        # on, which on a car that has stopped backs it away from the shore.
        land = self.terrain
        course = land.water_within(self.arrow, self.WATER_SPREAD, self.WATER_NEAR) if land else None
        shore = course is not None and course <= self.WATER_SLOW
        if command.state.startswith("recovery"):
            self.state = command.state
            pad = Pad.from_command(command)
            if shore and command.state == "recovery-forward":
                pad = Pad(left=pad.left, l2=1.0)
            return SkillResult(pad)
        around = self.avoider.step(obs.objects, obs.objects_time, now)
        error = abs(_angle(heading - self.arrow))
        turn = _clip((error - self.TURN_FROM) / (self.TURN_FULL - self.TURN_FROM), 0.0, 1.0)
        pedal = self.THROTTLE - turn * (self.THROTTLE - self.TURN_THROTTLE)
        brake = 0.0
        if course is not None:
            pedal = min(pedal, self.WATER_THROTTLE)
        if shore:
            pedal, brake = 0.0, 1.0
        throttle = 0.0 if around.urgent else pedal * around.pedal
        self.state = f"drive-{why}"
        steer = _clip(command.steer + around.steer)
        return SkillResult(Pad(left=(steer, 0.0), r2=_clip(throttle, 0.0), l2=brake))


def _towards(heading: float, arrow: float) -> Reading:
    """A route for the driver that leads from the arrow towards `heading`, in picture degrees."""
    return Reading(
        minimap="tilted",
        route="yellow",
        bearing=_angle(heading),
        far_bearing=_angle(heading),
        arrow=_angle(arrow),
        corrupt=False,
        confidence=1.0,
    )
