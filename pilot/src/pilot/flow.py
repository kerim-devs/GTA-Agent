"""Screen reflexes. Call before the skill; any result suspends that skill's tick."""

import re
from dataclasses import dataclass

from pilot.contract import NEUTRAL_PAD, Pad
from pilot.skills import Observation

MENUS = frozenset({"pause", "map", "phone", "weapon_wheel", "interaction_menu"})
FAILURES = frozenset({"failed", "wasted", "busted"})
# One tick is 33 ms, shorter than Kerim's presses (about 0.14 s) and easy for the console to miss.
PRESS_SECONDS = 0.09
# A press into a footer that is still fading in is lost, as Kerim's first four on the failure were.
MAX_PRESSES = 2
RECOVER_SECONDS = 0.3


@dataclass(frozen=True)
class FlowResult:
    pad: Pad = NEUTRAL_PAD
    action: str = "confirm"
    events: tuple[dict, ...] = ()


RETRY = re.compile(r"\b(retry|restart|erneut versuchen|wiederholen|neustart)\b")


def _button(text: object, screen: str) -> str | None:
    """The one button a screen is left with, as Kerim pressed it in recording 093238.

    The button is never taken from the text. The footer's glyphs are not read reliably (the
    cross next to "Erneut versuchen" never, the circle as O, l or a bracket), and the reader's
    line order puts a glyph next to the wrong label: "Verlassen O Erneut versuchen" and
    "Wegpunkt X Zurück" would quit the mission and set a waypoint. The text only says whether
    the retry is on offer yet; its footer comes about three seconds after the banner.
    """
    if screen == "failed":
        if isinstance(text, str):
            words = text
        else:
            words = " ".join(
                str(getattr(text, field, "") or "")
                for field in ("help", "objective", "subtitle", "banner", "phone_menu")
            )
        # Cross: the retry at t=39.776.
        return "cross" if RETRY.search(words.lower()) else None
    # Circle: phone t=156.294, map levels t=391.932/392.133. The interaction menu names circle
    # for "Zurück" in its footer, frames 1300 to 1513 of the screen tour of 11 November.
    return "circle" if screen in {"pause", "map", "phone", "interaction_menu"} else None


class Flow:
    """Two distinct timed reads confirm entry/exit; one pulse per unchanged screen.

    Missing HUD pauses an already active reflex. An expected menu returns None,
    allowing its owning skill to act until the absolute observation-time deadline.
    Events are emitted once; the caller queues them for the head after recovery.
    """

    def __init__(self, *, response_timeout: float = 2.0, wait_timeout: float = 30.0):
        if response_timeout < 0.14 or wait_timeout < response_timeout:
            raise ValueError("timeouts must allow the 0.14s picture delay")
        self.response_timeout = response_timeout
        self.wait_timeout = wait_timeout
        self.failures_in_row = 0
        self.last_pass: float | None = None
        self._expected: tuple[frozenset[str], float] | None = None
        self._candidate: str | None = None
        self._candidate_since = 0.0
        self._reads = 0
        self._screen: str | None = None
        self._engaged = False
        self._since = 0.0
        self._pressed_at: float | None = None
        self._pressed: tuple[str, str] | None = None
        self._presses = 0
        self._stuck = False
        self._last_time: float | None = None
        self._button: str | None = None
        self._button_reads = 0

    def expect(self, *screens: str, until: float) -> None:
        if not screens or any(screen not in MENUS for screen in screens):
            raise ValueError("only intentional menus may bypass the flow")
        self._expected = (frozenset(screens), until)

    def end_expectation(self) -> None:
        self._expected = None

    def tick(self, observation: Observation, text: object = None) -> FlowResult | None:
        now = observation.time
        if self._last_time is not None and now <= self._last_time:
            return FlowResult(action="await_fresh_read") if self._engaged else None
        self._last_time = now
        if observation.hud is None:
            self._reads = 0
            self._button, self._button_reads = None, 0
            pending = self._engaged
            return FlowResult(action="await_hud") if pending else None
        screen = observation.hud.screen
        if self._expected and now >= self._expected[1]:
            self._expected = None
        if self._expected and screen in self._expected[0]:
            self._screen, self._candidate, self._reads = None, None, 0
            self._engaged = False
            self._button, self._button_reads = None, 0
            return None

        self._reads = self._reads + 1 if screen == self._candidate else 1
        if screen != self._candidate:
            self._candidate_since = now
        self._candidate = screen
        button = _button(text, screen)
        self._button_reads = self._button_reads + 1 if button == self._button else 1
        self._button = button
        if screen == "game" and not self._engaged:
            return None
        self._engaged = True
        if self._reads < 2:
            return FlowResult(action="confirm")
        if screen == "game":
            # The reader calls a visible phone "game" for a frame or two; a screen that was
            # confirmed is only gone when the game has been read for a while.
            if self._screen is not None and now - self._candidate_since < RECOVER_SECONDS:
                return FlowResult(action="confirm")
            self._screen = None
            self._engaged = False
            return None

        events: tuple[dict, ...] = ()
        if screen != self._screen:
            self._screen, self._since = screen, now
            self._pressed_at, self._stuck, self._presses = None, False, 0
            if screen in FAILURES:
                self.failures_in_row += 1
                events = ({"kind": "failure", "screen": screen, "count": self.failures_in_row},)
            elif screen == "passed":
                self.last_pass, self.failures_in_row = now, 0
                events = ({"kind": "pass", "time": now},)
        if self._stuck:
            return FlowResult(action="stuck")
        waiting = screen in {"passed", "loading", "wasted", "busted"}
        ready = bool(button) and self._button_reads >= 2
        again = False
        if self._pressed_at is not None:
            # A press gets response_timeout to change the picture, then one more press does.
            if now - self._pressed_at >= self.response_timeout:
                again = ready and self._presses < MAX_PRESSES
                if not again:
                    self._stuck = True
        elif now >= self._since + (
            # The failure banner precedes its footer by about three seconds; wait for it.
            self.wait_timeout if waiting or screen == "failed" else self.response_timeout
        ):
            self._stuck = True
        if self._stuck:
            return FlowResult(action="stuck", events=(*events, {"kind": "stuck", "screen": screen}))
        if waiting:
            return FlowResult(action="wait", events=events)
        if screen == "weapon_wheel":
            return FlowResult(action="release", events=events)
        if self._pressed_at is not None and now - self._pressed_at < PRESS_SECONDS:
            return FlowResult(Pad(buttons=(self._pressed[0],)), self._pressed[1], events)
        if ready and (self._pressed_at is None or again):
            self._pressed_at = now
            self._presses += 1
            self._pressed = (button, "retry" if screen == "failed" else "back")
            return FlowResult(Pad(buttons=(button,)), self._pressed[1], events)
        return FlowResult(action="observe", events=events)
