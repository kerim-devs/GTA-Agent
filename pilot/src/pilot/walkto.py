"""Walking to a point on foot: the waypoint or a blip. Distances are minimap pixels only."""

from __future__ import annotations

import math
from typing import ClassVar

import numpy as np

from .contract import NEUTRAL_PAD, Observation, Pad, SkillResult, player_mode
from .foot import FootGuard, hud_crop, road_position, stick_for
from .profile import active
from .waymark import find_waypoint, way_by_road


def _turn(degrees: float) -> float:
    """An angle as the shorter turn, from -180 to 180."""
    return (degrees + 180.0) % 360.0 - 180.0


class WalkTo:
    name = "walk_to_point"
    # Kerim, 12 November: he sprints most of the way (four parts in five by his own word) and walks
    # only when he has time, and on foot the game draws no line, so the walker finds the road on
    # the map itself. Both are what the skill does unless it is told otherwise.
    parameters: ClassVar = {
        "color": ("purple", "yellow", "blue", "red"),
        "duration": (1.0, 180.0, 180.0),
        "radius": (1.0, 12.0, 4.0),
        "sprint": (True, False),
        "roads": (True, False),
        "side": (False, True),
    }
    prompt = (
        "Go on foot to the purple waypoint, or the nearest blip of color, for up to 180 s, sprinting "
        "unless sprint=false. roads=true keeps to the minimap's roads while one leads there, "
        "side=true to a road's side. Done when the blip stays within radius map pixels, or the "
        "game removes a near waypoint. A rim blip gives direction only. Reports map pixels, not metres."
    )
    SETTLE = 0.6
    LOST_AFTER = 3.0
    ROAD_FALLBACK = True
    PLAN_EVERY = 0.15  # seconds between two looks for the way on the map; the map turns with the camera
    DIRECT_WITHIN = 15.0  # map pixels: this near, the last steps go straight at the point
    OTHER_WAY = 60.0  # degrees between two looks that mean another way, not a bend in the same one
    OTHER_WAY_PLANS = 5
    # The game takes a waypoint off the map before the figure reaches it: on the console on
    # 12 November at 33 and at 31 map pixels, the figure sprinting. A marker last seen inside the
    # map this close and then gone counts as reached.
    GONE_WITHIN = 40.0
    HOLD = 2.0  # seconds the walk keeps its direction while an icon lies over the marker
    COAST = 0.5  # seconds the stick is kept over ticks that say nothing: a damaged or repeated frame
    BLIND = 5.0  # seconds of such ticks in a row after which the walk gives up
    # After the marker has gone the walk goes on to where it was: for as long as the last distance
    # takes at the rate the marker came nearer that evening (64 map pixels in 15 s of sprinting;
    # 7.4 in 8.4 s of walking, not straight at it), and never longer than CARRY_MAX.
    SPRINT_PACE, WALK_PACE = 4.3, 0.9
    CARRY_MAX = 6.0
    # After half a minute without an input the game shows the scene from changing cameras, and the
    # map turns with each of them. The third run of 12 November began under that view and the stick
    # swung three times in five seconds. Where the detector does not see the figure in its place
    # on the first tick, the camera is touched first and the walk waits for the game's own view.
    WAKE_PUSH, WAKE = 0.2, 0.45

    def __init__(self, args: dict):
        if not isinstance(args, dict) or set(args) - self.parameters.keys():
            raise ValueError("unknown walk_to arguments")
        for key in ("duration", "radius"):
            low, high, default = self.parameters[key]
            value = args.get(key, default)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{key} must be a finite number")
            if not math.isfinite(value):
                raise ValueError(f"{key} must be a finite number")
            setattr(self, key, max(low, min(high, value)))
        self.color = args.get("color", "purple")
        if self.color not in self.parameters["color"]:
            raise ValueError("unknown blip color")
        for key in ("sprint", "roads", "side"):
            value = args.get(key, self.parameters[key][0])
            if not isinstance(value, bool):
                raise ValueError(f"{key} must be boolean")
            setattr(self, key, value)
        self.limit = float(self.duration)
        self.profile = active()
        self.guard = FootGuard()
        self.started = None
        self.last_tick = None
        self.last_frame = None
        self.seen = False  # the target has been seen at all
        self.fresh = False  # and since the last gap in the ticks
        self.absent = 0.0  # seconds of readable ticks on foot without the target
        self.carried = 0.0  # of them, seconds the walk went on
        self.blind_since = None
        self.close_since = None
        self.bad_since = None
        self.wake_until = None
        self.wake_push = None
        self.start_distance = None
        self.end_distance = None
        self.start_border = False
        self.end_border = False
        self.finished = None
        self.road_mode = False
        self.road_entries = 0
        self.road_start_distance = None
        self.road_until = 0.0
        self.road_retry = 0.0
        self.on_road = False
        self.way = None  # (degrees from the line to the target, on a road)
        self.other = None
        self.other_looks = 0
        self.way_time = 0.0
        self.last_direction = None
        self.last_left = None
        self.last_left_time = 0.0
        self.road_seconds = 0.0
        self.walk_seconds = 0.0

    def _reason(self, reason: str) -> str:
        def distance(value, border):
            if value is None:
                return "unknown"
            return f"{value:.2f}px" + (" (rim; direction only)" if border else "")

        roads = f"on a road {self.road_seconds:.0f} of {self.walk_seconds:.0f} s; " if self.roads else ""
        return (
            f"{reason}; start={distance(self.start_distance, self.start_border)}; "
            f"end={distance(self.end_distance, self.end_border)}; {roads}"
            "pixels are not metres; rim target distance and arrival are unknown"
        )

    def _finish(self, status: str, reason: str) -> SkillResult:
        self.finished = SkillResult(status=status, reason=self._reason(reason))
        return self.finished

    def stop(self, reason: str) -> SkillResult:
        return self._finish("failed", reason)

    def _by_road(self, observation, target):
        """The stick for the first stretch of the way along the map's roads, or None to walk straight."""
        now = observation.time
        toward = math.degrees(math.atan2(target.x, target.y))
        if now - self.way_time > 3 * self.PLAN_EVERY:
            # A way kept over a stretch without looks is no measure for the next look.
            self.way, self.other, self.other_looks = None, None, 0
        if self.way is None or now - self.way_time >= self.PLAN_EVERY:
            found = way_by_road(hud_crop(observation.frame), target.x, target.y, side=self.side)
            self.way_time = now
            # The map turns with the camera and the target with it: a way is kept as its angle to
            # the line to the target, which a turn of the camera leaves as it is.
            look = None if found is None else (_turn(found[0] - toward), found[1])
            if look is None or self.way is None or abs(_turn(look[0] - self.way[0])) <= self.OTHER_WAY:
                self.way, self.other, self.other_looks = look, None, 0
            else:
                # Two ways that cost about the same swap places from one look to the next: the one
                # being walked is kept until the other has been found several times running.
                agrees = self.other is not None and abs(_turn(look[0] - self.other[0])) <= self.OTHER_WAY
                self.other, self.other_looks = look, self.other_looks + 1 if agrees else 1
                if self.other_looks >= self.OTHER_WAY_PLANS:
                    self.way, self.other, self.other_looks = look, None, 0
        if self.way is None:
            return None
        self.on_road = self.way[1]
        return stick_for(toward + self.way[0], 1.0)

    def _direction(self, observation, target, distance):
        want = (target.x / distance, -target.y / distance)
        self.on_road = False
        if self.roads and (target.border or distance > self.DIRECT_WITHIN):
            return self._by_road(observation, target) or want
        if self.roads or not self.ROAD_FALLBACK:
            return want
        now = observation.time
        if not self.road_mode and self.guard.failures >= 2 and now >= self.road_retry:
            self.road_mode = True
            self.road_entries += 1
            self.road_start_distance = None if target.border else distance
            self.road_until = now + 12.0
        if not self.road_mode:
            return want
        road = road_position(observation)
        if road is None or road.along is None:
            return want
        along = stick_for(road.along, 1.0)
        dot = sum(a * b for a, b in zip(along, want, strict=True))
        if dot < 0:
            along = (-along[0], -along[1])
            dot = -dot
        away = (
            not target.border
            and self.road_start_distance is not None
            and distance > self.road_start_distance + max(3.0, self.radius)
        )
        if dot < 0.15 or away or now >= self.road_until:
            self.road_mode = False
            self.road_retry = now + 4.0
            return want
        # Approach the nearest road first, then follow its best aligned tangent.
        if road.distance > 5.0:
            approach = stick_for(road.bearing, 1.0)
            if sum(a * b for a, b in zip(approach, want, strict=True)) >= -0.15:
                return approach
            self.road_mode = False
            self.road_retry = now + 4.0
            return want
        return along

    def step(self, observation: Observation) -> SkillResult:
        if self.finished is not None:
            return self.finished
        now = observation.time
        if isinstance(now, bool) or not isinstance(now, (float, int)) or not math.isfinite(now):
            self.close_since = None
            return self._stand()
        if self.started is None:
            self.started = now
        if now - self.started >= self.duration:
            return self._finish("failed", "time limit")
        if self.last_tick is not None and now <= self.last_tick:
            # A tick out of its order: nothing is decided on it and nothing is kept going by it.
            self.close_since = None
            return self._blind(now, coast=False)
        gap = self.last_tick is not None and now - self.last_tick > 1.0
        step = 0.0 if self.last_tick is None or gap else now - self.last_tick
        self.last_tick = now
        if gap:
            # What was seen before a gap in the ticks says nothing about now.
            self.close_since = self.bad_since = self.blind_since = None
            self.fresh, self.absent, self.last_direction, self.way = False, 0.0, None, None
            return self._stand()
        frame = observation.frame
        if frame is not None:
            valid_frame = (
                isinstance(frame, np.ndarray) and frame.shape == (720, 1280, 3) and frame.dtype == np.uint8
            )
            repeated = self.last_frame is not None and np.array_equal(frame, self.last_frame)
            if not valid_frame or repeated:
                self.close_since = None
                return self._blind(now)
            self.last_frame = frame.copy()
        reading = observation.reading
        if reading is None:
            self.close_since = None
            return self._blind(now, coast=False)
        if reading.corrupt:
            # A damaged picture says neither where the target is nor whether the figure is on foot.
            self.close_since = None
            return self._blind(now)
        if player_mode(observation) != "foot":
            self.close_since = self.blind_since = None
            if self.bad_since is None:
                self.bad_since = now
            if now - self.bad_since >= 0.6:
                return self._finish("failed", "no longer on foot")
            return self._stand()
        if reading.confidence < 0.6:
            self.close_since = None
            # With no map on the screen something else is being shown, and nothing is pushed into it.
            return self._blind(now, coast=reading.minimap != "none")
        self.bad_since = self.blind_since = None
        if self.wake_until is None:
            unseen = observation.objects_time is not None and observation.figure is None
            self.wake_push = now + self.WAKE_PUSH if unseen else now
            self.wake_until = now + self.WAKE if unseen else now
        if now < self.wake_until:
            self.last_left = None
            return SkillResult(
                pad=Pad(right=(0.4, 0.0)) if now < self.wake_push else NEUTRAL_PAD,
                reason="touching the camera for the game's own view",
            )
        targets = [
            blip
            for blip in reading.blips
            if blip.color == self.color and math.isfinite(blip.x) and math.isfinite(blip.y)
        ]
        if not targets and self.color == "purple" and reading.route != "purple":
            # The minimap reader knows no purple disc: the waypoint's marker is read from the frame.
            # Not beside a purple route, which is a vehicle's and whose end the bars cut to a disc.
            marker = find_waypoint(hud_crop(frame))
            targets = [] if marker is None else [marker]
        if not targets:
            self.close_since = None
            # Only a readable tick on foot counts as one without the target.
            self.absent += step
            if not self.seen:
                if self.absent >= self.LOST_AFTER:
                    return self._finish("failed", "no matching blip")
                return self._stand()
            reached = (
                self.color == "purple"
                and self.fresh
                and not self.end_border
                and self.end_distance is not None
                and self.end_distance <= self.GONE_WITHIN
            )
            pace = self.SPRINT_PACE if self.sprint else self.WALK_PACE
            keep = min(self.CARRY_MAX, self.end_distance / pace) if reached else self.HOLD
            # The direction is the camera's: it holds only while the guard leaves the camera alone.
            if (
                self.fresh
                and self.absent < keep
                and self.last_direction is not None
                and self.guard.state == "go"
            ):
                self.carried += step
                return self._push(observation, self.last_direction, step)
            if self.absent >= self.LOST_AFTER:
                if reached:
                    return self._finish(
                        "done",
                        "arrived; the game took the near waypoint off the map, "
                        f"walked on {self.carried:.1f} s",
                    )
                return self._finish("failed", "blip lost; end is last observed distance")
            return self._stand()
        target = min(targets, key=lambda blip: math.hypot(blip.x, blip.y))
        distance = math.hypot(target.x, target.y)
        self.seen = self.fresh = True
        self.absent = self.carried = 0.0
        if self.start_distance is None:
            self.start_distance, self.start_border = distance, target.border
        self.end_distance, self.end_border = distance, target.border
        if not target.border and distance <= self.radius:
            if self.close_since is None:
                self.close_since = now
            if now - self.close_since >= self.SETTLE:
                return self._finish("done", "arrived; stable interior blip")
            return self._stand()
        self.close_since = None
        if distance == 0:
            return self._stand()
        self.last_direction = self._direction(observation, target, distance)
        return self._push(observation, self.last_direction, step)

    def _stand(self) -> SkillResult:
        """Nothing on the pad, and nothing left over for a later tick to send again."""
        self.last_left = None
        return SkillResult()

    def _blind(self, now, *, coast: bool = True) -> SkillResult:
        """A tick that says nothing decides nothing, and does not stop a figure that is running."""
        if self.blind_since is None:
            self.blind_since = now
        if now - self.blind_since >= self.BLIND:
            return self._finish("failed", f"nothing readable for {self.BLIND:.0f} s")
        if coast and self.last_left is not None and 0 <= now - self.last_left_time <= self.COAST:
            buttons = self.profile.sprint_buttons(now - self.started) if self.sprint else ()
            return SkillResult(pad=Pad(left=self.last_left, buttons=buttons))
        return self._stand()

    def _push(self, observation, direction, step):
        steer = self.guard.step(observation, direction)
        if steer.failed:
            return self._finish("failed", "stuck; guard exhausted")
        buttons = (
            self.profile.sprint_buttons(observation.time - self.started)
            if self.sprint and steer.state in {"go", "idle"}
            else ()
        )
        self.walk_seconds += step
        self.road_seconds += step if self.on_road else 0.0
        if steer.state == "odd":
            self.last_left = None
            return SkillResult(
                pad=NEUTRAL_PAD, reason=self._reason("following road" if self.on_road else "walking")
            )
        # Only a plain push forward is kept for a tick that says nothing, never the guard's own moves.
        self.last_left = steer.left if steer.state == "go" else None
        self.last_left_time = observation.time
        return SkillResult(
            pad=Pad(left=steer.left, right=steer.right, buttons=buttons),
            reason=self._reason("following road" if self.road_mode or self.on_road else "walking"),
        )
