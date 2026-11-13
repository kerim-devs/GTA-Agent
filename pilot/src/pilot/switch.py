"""Story-character switching with a story stick held across every wheel release.

External stop has a one-pad fallback: the current runner discards that pad, so the
runner must support an exit drain before this skill can be used on a console.
"""

import math
import threading
from typing import ClassVar

import numpy as np

from pilot.contract import Observation, Pad, SkillResult, player_mode
from pilot.scene import TextReader
from pilot.wheel import wheel

STORY = ("michael", "franklin", "trevor")
SLOTS = {"michael": "left", "franklin": "top", "trevor": "right"}
DIRECTIONS = {"left": (-1.0, 0.0), "top": (0.0, -1.0), "right": (1.0, 0.0)}
RELEASE_SECONDS = 0.25


class _Objectives:
    """One pending bottom-text scan; OCR never holds the hands clock."""

    def __init__(self):
        self.condition = threading.Condition()
        self.pending = None
        self.latest = None
        self.closed = False
        self.thread = None

    def submit(self, frame, now):
        with self.condition:
            if self.closed:
                return
            self.pending = (frame.copy(), now)
            if self.thread is None:
                self.thread = threading.Thread(target=self._run, daemon=True)
                self.thread.start()
            self.condition.notify()

    def _run(self):
        try:
            reader = TextReader()
        except Exception:
            return
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.closed or self.pending is not None)
                if self.closed:
                    return
                frame, now = self.pending
                self.pending = None
            try:
                result = (now, reader.read(frame, "bottom").objective)
            except Exception:
                result = None
            with self.condition:
                if not self.closed:
                    self.latest = result

    def read(self):
        with self.condition:
            return self.latest

    def close(self):
        with self.condition:
            self.closed = True
            self.pending = None
            self.condition.notify()


class SwitchCharacter:
    name = "switch_character"
    parameters: ClassVar = {
        "duration": (4.0, 40.0, 25.0),
        "to": ("next", "michael", "franklin", "trevor"),
    }
    prompt = (
        "Switch between story characters using the wheel, never the fourth slot. Free roam on "
        "foot or seated, no stars or objective. Done 'switched: <name>; was: <name>' when the "
        "game returns. Fails switch-refused, wheel-unread, online-slot-seen or time-limit."
    )

    def __init__(self, args: dict):
        if not isinstance(args, dict) or set(args) - self.parameters.keys():
            raise ValueError("switch_character accepts only duration, to")
        duration = args.get("duration", 25.0)
        if (
            isinstance(duration, bool)
            or not isinstance(duration, (int, float))
            or not math.isfinite(duration)
        ):
            raise ValueError("duration must be a finite number")
        self.limit = float(max(4.0, min(40.0, duration)))
        self.target = args.get("to", "next")
        if self.target not in self.parameters["to"]:
            raise ValueError("to must be next, michael, franklin or trevor")
        self.phase = "preflight"
        self.started = None
        self.last_time = None
        self.last_pad = Pad()
        self.phase_time = None
        self.was = None
        self.chosen = None
        self.slot = "top"
        self.matches = 0
        self.game_since = None
        self.failure = None
        self.finished = None
        self.text = _Objectives()

    def _reason(self, reason):
        return f"{reason}; was: {self.was}" if self.was else reason

    def _finish(self, status, reason):
        self.text.close()
        self.phase = "finished"
        self.finished = SkillResult(status=status, reason=self._reason(reason))
        return self.finished

    def _held(self):
        return SkillResult(Pad(buttons=("down",), right=DIRECTIONS[self.slot]))

    def _release(self, now, failure=None, slot=None):
        self.phase = "releasing"
        self.phase_time = now
        self.failure = failure
        if slot is not None:
            self.slot = slot
        return SkillResult(Pad(right=DIRECTIONS[self.slot]))

    @staticmethod
    def _picture_ok(obs):
        return (
            isinstance(obs.frame, np.ndarray)
            and obs.frame.shape == (720, 1280, 3)
            and obs.frame.dtype == np.uint8
            and not obs.reading.corrupt
        )

    @staticmethod
    def _refusal(obs):
        if not SwitchCharacter._picture_ok(obs):
            return "picture-unread"
        if obs.hud is None or obs.hud.screen != "game":
            return "not-game"
        if obs.reading.minimap not in ("flat", "tilted") or obs.reading.confidence < 0.5:
            return "minimap-unread"
        if obs.hud.wanted != 0:
            return "wanted-or-unknown"
        if player_mode(obs) not in ("foot", "vehicle"):
            return "not-on-foot-or-seated"
        return None

    def step(self, observation: Observation) -> SkillResult:
        # A repeated capture cannot count as another confirmed highlight.
        if self.finished is None and self.last_time == observation.time:
            return SkillResult(self.last_pad)
        result = self._step(observation)
        self.last_pad = result.pad
        return result

    def _step(self, observation: Observation) -> SkillResult:
        if self.finished is not None:
            return self.finished
        now = observation.time
        bad_clock = (
            "clock-unread"
            if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now)
            else "clock-reversed"
            if self.last_time is not None and now < self.last_time
            else None
        )
        if bad_clock:
            if self.phase == "preflight":
                return self._finish("failed", f"switch-refused: {bad_clock}")
            if self.phase == "returning":
                return self._finish("failed", bad_clock)
            if self.phase != "releasing":
                return self._release(self.last_time, bad_clock)
            self.failure = self.failure or bad_clock
            return SkillResult(Pad(right=DIRECTIONS[self.slot]))
        self.last_time = now
        if self.started is None:
            self.started = now

        # No picture, timeout or repeated stop may shorten the release interval.
        if self.phase == "releasing":
            if now - self.phase_time < RELEASE_SECONDS:
                return SkillResult(Pad(right=DIRECTIONS[self.slot]))
            if self.failure:
                return self._finish("failed", self.failure)
            self.phase = "returning"
            self.game_since = None

        if self.phase == "preflight":
            refusal = self._refusal(observation)
            if refusal:
                return self._finish("failed", f"switch-refused: {refusal}")
            if now - self.started >= self.limit:
                return self._finish("failed", "switch-refused: objective-unread")
            self.text.submit(observation.frame, now)
            text = self.text.read()
            if text is None or not 0 <= now - text[0] <= 1.0:
                return SkillResult()
            if text[1]:
                return self._finish("failed", "switch-refused: objective")
            self.text.close()
            self.phase = "opening"
            self.phase_time = now
            return SkillResult(Pad(buttons=("down",)))

        if self.phase == "rescuing":
            reading = (
                wheel(observation.frame)
                if self._picture_ok(observation)
                and observation.hud is not None
                and observation.hud.screen == "game"
                else None
            )
            if (
                reading is not None and reading.visible and reading.highlight in DIRECTIONS
            ) or now - self.phase_time >= 2.0:
                return self._release(now, self.failure)
            return self._held()

        if now - self.started >= self.limit:
            if self.phase == "returning":
                return self._finish("failed", "time-limit")
            return self._release(now, "time-limit")

        if self.phase == "returning":
            valid = self._refusal(observation) is None
            reading = wheel(observation.frame) if valid else None
            if not valid or reading.visible:
                self.game_since = None
            elif self.game_since is None:
                self.game_since = now
            elif now - self.game_since >= 1.0:
                return self._finish("done", f"switched: {self.chosen}")
            return SkillResult()

        if not self._picture_ok(observation) or (observation.hud is None or observation.hud.screen != "game"):
            return self._release(now, "wheel-unread")
        reading = wheel(observation.frame)
        if reading.visible and reading.highlight in ("bottom", None):
            # No recorded Online selection is available to calibrate that
            # wedge. An unread selection gets the same conservative rescue.
            self.failure = "online-slot-seen" if reading.highlight == "bottom" else "wheel-unread"
            self.phase = "rescuing"
            self.phase_time = now
            self.slot = "top"
            return self._held()

        if self.phase == "opening":
            if reading.visible and reading.highlight in DIRECTIONS:
                self.was = next(name for name, slot in SLOTS.items() if slot == reading.highlight)
                self.slot = SLOTS[self.was]
                candidates = STORY[STORY.index(self.was) + 1 :] + STORY[: STORY.index(self.was)]
                if self.target == "next":
                    self.chosen = next(
                        (name for name in candidates if SLOTS[name] not in reading.disabled), None
                    )
                else:
                    self.chosen = self.target
                if self.chosen is None or SLOTS[self.chosen] in reading.disabled:
                    return self._release(now, "switch-refused: unavailable")
                if self.chosen == self.was:
                    return self._release(now, "switch-refused: already-current")
                self.slot = SLOTS[self.chosen]
                self.phase = "selecting"
                self.phase_time = now
                return self._held()
            if now - self.phase_time >= 3.0:
                return self._release(now, "wheel-unread")
            return SkillResult(Pad(buttons=("down",)))

        if now - self.phase_time >= 3.0:
            return self._release(now, "wheel-unread", SLOTS[self.was])
        if reading.visible and self.slot in reading.disabled:
            return self._release(now, "switch-refused: unavailable", SLOTS[self.was])
        self.matches = self.matches + 1 if reading.visible and reading.highlight == self.slot else 0
        if self.matches >= 2:
            return self._release(now)
        return self._held()

    def stop(self, reason: str = "interrupted") -> SkillResult:
        if self.finished is not None:
            return self.finished
        if self.phase == "preflight":
            return self._finish("failed", reason)
        # The contract cannot drain ticks after an external stop. Return the
        # card's one-tick story-stick fallback, never a neutral wheel release.
        result = SkillResult(Pad(right=DIRECTIONS[self.slot]), "failed", self._reason(reason))
        self._finish("failed", reason)
        return result
