"""Walking to a point on foot: the waypoint or a blip. Distances are minimap pixels only."""

from __future__ import annotations

import math
from typing import ClassVar

import numpy as np

from .contract import NEUTRAL_PAD, Observation, Pad, SkillResult, player_mode
from .foot import FootGuard, hud_crop, road_position, stick_for
from .profile import active
from .waymark import find_waypoint, way_by_road


class WalkTo:
    name = "walk_to_point"
    parameters: ClassVar = {
        "color": ("purple", "yellow", "blue", "red"),
        "duration": (1.0, 180.0, 180.0),
        "radius": (1.0, 12.0, 4.0),
        "sprint": (False, True),
        "roads": (False, True),
    }
    prompt = (
        "Walk on foot to the purple waypoint, or the nearest blip of color, for up to 180 s. "
        "roads=true keeps to the minimap's roads while one leads towards the point. "
        "Done when the blip stays within radius map pixels, or the game removes a near waypoint. "
        "A rim blip gives direction only. Reports start/end map pixels, not metres."
    )
    SETTLE = 0.6
    LOST_AFTER = 3.0
    ROAD_FALLBACK = True
    # Kerim, 12 November: on foot the game draws no line, the walker finds the road on the map itself.
    PLAN_EVERY = 0.15  # seconds between two looks for the way on the map; the map turns with the camera
    DIRECT_WITHIN = 15.0  # map pixels: this near, the last steps go straight at the point
    OTHER_WAY = 60.0  # degrees between two looks that mean another way, not a bend in the same one
    OTHER_WAY_PLANS = 5
    # The game takes a waypoint off the map when the figure reaches it: on the console on 12 November
    # it went at 33 map pixels, the figure sprinting. A marker last seen inside the map this close
    # and then gone counts as reached.
    GONE_WITHIN = 40.0
    HOLD = 2.0  # seconds the walk keeps its direction while an icon lies over the marker
    COAST = 0.5  # seconds the last pad is kept over ticks that say nothing: a damaged or repeated frame
    # The marker goes before the point is reached, so the walk goes on to where it was: for as long
    # as the last distance takes at the pace seen that evening (64 map pixels in 15 s of sprinting,
    # 7.4 in 8.4 s of walking), and never longer than CARRY_MAX.
    SPRINT_PACE, WALK_PACE = 4.3, 0.9
    CARRY_MAX = 6.0

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
        self.sprint = args.get("sprint", False)
        if not isinstance(self.sprint, bool):
            raise ValueError("sprint must be boolean")
        self.roads = args.get("roads", False)
        if not isinstance(self.roads, bool):
            raise ValueError("roads must be boolean")
        self.profile = active()
        self.guard = FootGuard()
        self.started = None
        self.last_tick = None
        self.last_frame = None
        self.last_seen = None
        self.close_since = None
        self.bad_since = None
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
        self.way = None
        self.way_time = 0.0
        self.last_direction = None
        self.last_pad = None
        self.last_pad_time = 0.0
        self.other_ways = 0
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
        if self.way is None or now - self.way_time >= self.PLAN_EVERY:
            way = way_by_road(hud_crop(observation.frame), target.x, target.y)
            self.way_time = now
            turn = None if way is None or self.way is None else abs((way[0] - self.way[0] + 180) % 360 - 180)
            if turn is not None and turn > self.OTHER_WAY and self.other_ways < self.OTHER_WAY_PLANS:
                # Two ways that cost about the same swap places from one look to the next: the one
                # being walked is kept until the other has been found several times running.
                self.other_ways += 1
            else:
                self.way = way
                self.other_ways = 0
        if self.way is None:
            return None
        bearing, self.on_road = self.way
        return stick_for(bearing, 1.0)

    def _direction(self, observation, target, distance):
        want = (target.x / distance, -target.y / distance)
        self.on_road = False
        if self.roads and (target.border or distance > self.DIRECT_WITHIN):
            return self._by_road(observation, target) or want
        if not self.ROAD_FALLBACK:
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
        if not isinstance(now, (float, int)) or not math.isfinite(now):
            self.close_since = None
            return SkillResult()
        if self.started is None:
            self.started = now
        if now - self.started >= self.duration:
            return self._finish("failed", "time limit")
        if self.last_tick is not None and now <= self.last_tick:
            self.close_since = None
            self.bad_since = None
            return self._coast(now)
        gap = self.last_tick is not None and now - self.last_tick > 1.0
        step = 0.0 if self.last_tick is None or gap else now - self.last_tick
        self.last_tick = now
        frame = observation.frame
        if frame is not None:
            valid_frame = (
                isinstance(frame, np.ndarray) and frame.shape == (720, 1280, 3) and frame.dtype == np.uint8
            )
            repeated = self.last_frame is not None and np.array_equal(frame, self.last_frame)
            if not valid_frame or repeated:
                self.close_since = self.bad_since = None
                return self._coast(now)
            self.last_frame = frame.copy()
        reading = observation.reading
        mode = player_mode(observation) if reading is not None else None
        if reading is None or reading.corrupt or reading.confidence < 0.6:
            self.close_since = None
            self.bad_since = None
            return self._coast(now)
        if gap:
            self.close_since = None
            self.bad_since = None
            return SkillResult()
        if mode != "foot":
            self.close_since = None
            if self.bad_since is None:
                self.bad_since = now
            if now - self.bad_since >= 0.6:
                return self._finish("failed", "no longer on foot")
            return SkillResult()
        self.bad_since = None
        targets = [
            blip
            for blip in reading.blips
            if blip.color == self.color and math.isfinite(blip.x) and math.isfinite(blip.y)
        ]
        if not targets and self.color == "purple":
            # The minimap reader knows no purple disc: the waypoint's marker is read from the frame.
            marker = find_waypoint(hud_crop(frame))
            targets = [] if marker is None else [marker]
        if not targets:
            self.close_since = None
            if self.last_seen is None:
                if now - self.started >= self.LOST_AFTER:
                    return self._finish("failed", "no matching blip")
                return SkillResult()
            gone = now - self.last_seen
            reached = (
                self.color == "purple"
                and not self.end_border
                and self.end_distance is not None
                and self.end_distance <= self.GONE_WITHIN
            )
            pace = self.SPRINT_PACE if self.sprint else self.WALK_PACE
            keep = min(self.CARRY_MAX, self.end_distance / pace) if reached else self.HOLD
            if gone < keep and self.last_direction is not None:
                return self._push(observation, self.last_direction, step)
            if gone >= self.LOST_AFTER:
                if reached:
                    return self._finish(
                        "done",
                        f"arrived; the game took the near waypoint off the map, walked on {keep:.1f} s",
                    )
                return self._finish("failed", "blip lost; end is last observed distance")
            return SkillResult()
        target = min(targets, key=lambda blip: math.hypot(blip.x, blip.y))
        distance = math.hypot(target.x, target.y)
        self.last_seen = now
        if self.start_distance is None:
            self.start_distance, self.start_border = distance, target.border
        self.end_distance, self.end_border = distance, target.border
        if not target.border and distance <= self.radius:
            if self.close_since is None:
                self.close_since = now
            if now - self.close_since >= self.SETTLE:
                return self._finish("done", "arrived; stable interior blip")
            return SkillResult()
        self.close_since = None
        if distance == 0:
            return SkillResult()
        self.last_direction = self._direction(observation, target, distance)
        return self._push(observation, self.last_direction, step)

    def _coast(self, now):
        """A tick that says nothing decides nothing, and does not stop a figure that is running."""
        if self.last_pad is not None and abs(now - self.last_pad_time) <= self.COAST:
            return SkillResult(pad=self.last_pad)
        return SkillResult()

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
        pad = (
            Pad(left=steer.left, right=steer.right, buttons=buttons) if steer.state != "odd" else NEUTRAL_PAD
        )
        self.last_pad, self.last_pad_time = pad, observation.time
        return SkillResult(
            pad=pad,
            reason=self._reason("following road" if self.road_mode or self.on_road else "walking"),
        )
