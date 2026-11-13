"""Walk down from a landing, ending only on a confirmed street."""

import math
from typing import ClassVar

import numpy as np

from . import ahead, indoors, sides
from .contract import Observation, Pad, SkillResult, player_mode
from .wayround import WayRound


class Descend:
    name = "descend"
    parameters: ClassVar = {"duration": (5.0, 60.0, 40.0)}
    prompt = (
        "On foot on a landing: look for stairs and walk down to the street, then straight on to "
        "clear their foot. Needs readable place answers. Done street. Fails place-unread, in-room "
        "(leave the building first), entered-room, no-stairs or time-limit. Never jumps."
    )

    def __init__(self, args: dict):
        if not isinstance(args, dict) or set(args) - self.parameters.keys():
            raise ValueError("descend accepts only duration")
        value = args.get("duration", 40.0)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("duration must be a finite number")
        self.limit = float(max(5.0, min(60.0, value)))
        self.guard = WayRound(climb=False, sides=sides.active(), ahead=ahead.active())
        self.place = ahead.place()
        self.confirm = indoors.Confirm()
        self.asked = None
        self.asked_at = -math.inf
        self.started = self.last = self.clear = None
        self.frame = None
        self.descending = False
        self.finished = None
        self.place_seconds = 0.0
        self.place_last = None
        self.place_confirmed = False
        self.walked = False  # the stick has been pushed since the landing was last confirmed

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
            or not math.isfinite(reading.confidence)
            # The map alone has to be read whole and flat to say "on foot"; the judge's word stands
            # without it. On 13 November the figure stood at the head of the stairs for a hundred
            # seconds: the street grid on the radar lay square to the picture and was read as a
            # tilted map and as codec damage in turn.
            or (
                observation.mode is None
                and (reading.corrupt or reading.confidence < 0.6 or reading.minimap != "flat")
            )
            or reading.minimap == "none"
            or player_mode(observation) != "foot"
        ):
            return self._unknown()
        if (
            not isinstance(frame, np.ndarray)
            or frame.shape != (720, 1280, 3)
            or frame.dtype != np.uint8
            or (self.frame is not None and np.array_equal(frame, self.frame))
        ):
            return self._unknown()
        self.frame = frame.copy()
        if self.place is None:
            return self.stop("place-unread")
        if self.place_last is not None:
            self.place_seconds += now - self.place_last
        self.place_last = now
        place = self._place(observation)
        if place is not None:
            self.place_confirmed = True
        if not self.place_confirmed and self.place_seconds >= 8.0:
            return self.stop("place-unread")
        if place == "landing":
            self.walked = False
        if place == "room" and self.descending and not self.walked:
            # The camera has turned to the door the figure came out of and looks into the room; the
            # figure has not taken a step. On 13 November that ended the search for the stairs.
            place = None
        if place == "room":
            return self.stop("entered-room" if self.descending else "in-room")
        if place == "street":
            if not self.descending:
                self.finished = SkillResult(status="done", reason="street")
                return self.finished
            if self.clear is None:
                self.clear = now
        elif place == "landing" and not self.descending:
            self.descending = True
            self.guard.descend(observation)
        if self.clear is not None:
            if now - self.clear >= self.guard.CLEAR:
                self.finished = SkillResult(status="done", reason="street")
                return self.finished
            return SkillResult(pad=Pad(left=self.guard.AHEAD), reason="clearing stairs")
        if not self.descending:
            return SkillResult()
        if self.guard.state == "go":
            self.guard.descend(observation)
        steer = self.guard.step(observation, self.guard.AHEAD)
        if steer.failed:
            return self.stop("no-stairs")
        if steer.state in {"odd", "idle"}:
            return self._unknown()
        self.walked = self.walked or any(steer.left)
        return SkillResult(
            pad=Pad(left=steer.left, right=steer.right, buttons=steer.buttons),
            reason=f"descending stairs; {self.guard.diagnostic()}",
        )

    def _place(self, observation: Observation):
        now = observation.time
        confirmed = None
        if self.asked is not None:
            view = self.place.answer(self.asked)
            age = now - self.asked
            if view is not None or age >= 2.0:
                value = None
                if view is not None and age < 2.0 and view.error is None:
                    shares = view.where
                    if shares is not None and all(math.isfinite(share) for share in shares):
                        index = max(range(len(ahead.PLACES)), key=lambda index: shares[index])
                        if shares[index] >= 0.6:
                            value = ahead.PLACES[index]
                # Count different captured frames, even when their answers arrive close together.
                confirmed = self.confirm.see(value, self.asked)
                self.asked = None
                if value != "street":
                    self.clear = None
        if self.asked is None and now - self.asked_at >= 0.6:
            self.asked_at = now
            if self.place.ask(observation.frame, now, where=True):
                self.asked = now
        return confirmed

    def _unknown(self):
        self.place_last = None
        self.confirm.reset()
        self.asked = None
        self.clear = None
        if self.last is not None:
            self.guard.resume(self.last)
        return SkillResult()
