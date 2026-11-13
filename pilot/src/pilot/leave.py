"""Leave a building using the walk's guard and confirmed place readings."""

import math
from typing import ClassVar

import numpy as np

from . import ahead, indoors, sides
from .contract import Observation, Pad, SkillResult, player_mode
from .foot import hud_crop, north_bearing
from .wayround import WayRound


class LeaveBuilding:
    name = "leave_building"
    parameters: ClassVar = {"duration": (5.0, 120.0, 60.0)}
    prompt = (
        "Indoors on foot: go back out the way the figure came in, else look for the way out, else go "
        "round along the walls, then a few steps straight on in the open. Done 'outdoors' (also when "
        "it began outdoors). Fails no-way-out or time-limit."
    )

    def __init__(self, args: dict):
        if not isinstance(args, dict) or set(args) - self.parameters.keys():
            raise ValueError("leave_building accepts only duration")
        value = args.get("duration", 60.0)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("duration must be a finite number")
        self.limit = float(max(5.0, min(120.0, value)))
        self.guard = WayRound(climb=False, sides=sides.active(), ahead=ahead.active(), confirm_place=True)
        self.place = indoors.Place(ahead.place())
        self.started = self.last = self.clear = None
        self.frame = None
        self.leaving = False
        self.finished = None
        self.place_seconds = 0.0
        self.place_last = None
        self.place_confirmed = False

    def stop(self, reason: str = "interrupted") -> SkillResult:
        if self.finished is None:
            self.finished = SkillResult(status="failed", reason=reason)
        return self.finished

    def step(self, observation: Observation) -> SkillResult:
        if self.finished is not None:
            return self.finished
        now = observation.time
        if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now):
            return self._unknown()
        if self.started is None:
            self.started = now
        if now - self.started >= self.limit:
            return self.stop("time-limit")
        if self.last is not None and now <= self.last:
            return self._unknown()
        gap = self.last is not None and now - self.last > 1
        self.last = now
        reading, frame = observation.reading, observation.frame
        if (
            gap
            or reading is None
            or reading.corrupt
            or reading.confidence < 0.6
            or reading.minimap != "flat"
            or player_mode(observation) != "foot"
        ):
            return self._unknown()
        if frame is not None:
            if (
                not isinstance(frame, np.ndarray)
                or frame.shape != (720, 1280, 3)
                or frame.dtype != np.uint8
                or (self.frame is not None and np.array_equal(frame, self.frame))
            ):
                return self._unknown()
            self.frame = frame.copy()
        if self.place.model is None and not indoors.INDEPENDENT:
            return self.stop("place-unread")
        if self.place_last is not None:
            self.place_seconds += now - self.place_last
        self.place_last = now
        place = self.place.sample(observation)
        if place is not None:
            self.place_confirmed = True
        if not self.place_confirmed and self.place_seconds >= 8.0:
            return self.stop("place-unread")
        if place is False:
            if not self.leaving:
                self.finished = SkillResult(status="done", reason="outdoors")
                return self.finished
            if self.clear is None:
                self.clear = now
        elif place is True:
            self.clear = None
            if not self.leaving:
                self.leaving = True
                entry = indoors.entrance()
                north = north_bearing(hud_crop(frame)) if frame is not None else None
                if (
                    entry is not None
                    and entry.heading is not None
                    and entry.at is not None
                    and 0 <= now - entry.at <= (180 if entry.absolute else 30)
                    and (not entry.absolute or north is not None)
                ):
                    heading = entry.heading + (north if entry.absolute else 0) + 180
                    self.guard.leave_heading(observation, heading)
                else:
                    self.guard.leave(observation)
        if self.clear is not None:
            if now - self.clear >= self.guard.CLEAR:
                self.finished = SkillResult(status="done", reason="outdoors")
                indoors.forget()
                return self.finished
            return SkillResult(pad=Pad(left=self.guard.AHEAD), reason="clearing doorway")
        if not self.leaving:
            return SkillResult()
        if self.guard.state == "go":
            self.guard.leave(observation)
        steer = self.guard.step(observation, self.guard.AHEAD)
        if steer.failed:
            return self.stop("no-way-out")
        if steer.state in {"odd", "idle"}:
            return self._unknown()
        return SkillResult(
            pad=Pad(left=steer.left, right=steer.right, buttons=steer.buttons), reason="leaving building"
        )

    def _unknown(self):
        self.place_last = None
        self.place.reset()
        self.guard.outside_confirm.reset()
        self.clear = None
        if self.last is not None:
            self.guard.resume(self.last)
        return SkillResult()
