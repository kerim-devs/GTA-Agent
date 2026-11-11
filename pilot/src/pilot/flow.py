"""Screen reflexes. Call before the skill; any result suspends that skill's tick."""

import re
from dataclasses import dataclass

from pilot.contract import NEUTRAL_PAD, Pad
from pilot.skills import Observation

MENUS = frozenset({"pause", "map", "phone", "weapon_wheel"})
FAILURES = frozenset({"failed", "wasted", "busted"})
# One tick is 33 ms, shorter than Kerim's presses (about 0.14 s) and easy for the console to miss.
PRESS_SECONDS = 0.09


@dataclass(frozen=True)
class FlowResult:
    pad: Pad = NEUTRAL_PAD
    action: str = "confirm"
    events: tuple[dict, ...] = ()


def _named_button(text: object, screen: str) -> str | None:
    """Require a button next to an allowed action, not just anywhere in OCR text."""
    if isinstance(text, str):
        fields = [text]
    else:
        fields = [
            str(getattr(text, field, "") or "")
            for field in ("help", "objective", "subtitle", "banner", "phone_menu")
        ]
    actions = (
        r"retry|restart|erneut versuchen|wiederholen|neustart"
        if screen == "failed"
        else (r"back|close|cancel|zurück|schließen|abbrechen")
    )
    # Only these two controls are supported. Never infer shoulder buttons from text.
    buttons = r"cross|circle|[x\u00d7✕○◯]"
    for field in fields:
        for line in re.split(r"[\n|;]", field.lower()):
            match = re.search(rf"\b({actions})\b\s*[:\[({{]?\s*({buttons})(?!\w)", line)
            if match:
                button = match[2]
            else:
                match = re.search(rf"(?<!\w)({buttons})\s*[\])}}:]?\s*\b({actions})\b", line)
                if not match:
                    continue
                button = match[1]
            return "cross" if button in {"cross", "x", "\u00d7", "✕"} else "circle"
    return None


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
        self._expected: tuple[str, float] | None = None
        self._candidate: str | None = None
        self._reads = 0
        self._screen: str | None = None
        self._since = 0.0
        self._pressed_at: float | None = None
        self._pressed: tuple[str, str] | None = None
        self._stuck = False
        self._last_time: float | None = None
        self._button: str | None = None
        self._button_reads = 0

    def expect(self, screen: str, *, until: float) -> None:
        if screen not in MENUS:
            raise ValueError("only intentional menus may bypass the flow")
        self._expected = (screen, until)

    def tick(self, observation: Observation, text: object = None) -> FlowResult | None:
        now = observation.time
        if self._last_time is not None and now <= self._last_time:
            return (
                FlowResult(action="await_fresh_read")
                if self._candidate not in {None, "game"} or self._screen
                else None
            )
        self._last_time = now
        if observation.hud is None:
            self._reads = 0
            self._button, self._button_reads = None, 0
            pending = self._screen or self._candidate not in {None, "game"}
            return FlowResult(action="await_hud") if pending else None
        screen = observation.hud.screen
        if self._expected and now >= self._expected[1]:
            self._expected = None
        if self._expected and self._expected[0] == screen:
            self._screen, self._candidate, self._reads = None, None, 0
            self._button, self._button_reads = None, 0
            return None

        self._reads = self._reads + 1 if screen == self._candidate else 1
        self._candidate = screen
        button = _named_button(text, screen) if screen in MENUS | {"failed"} else None
        # Circle: phone t=156.294, map levels t=391.932/392.133 in 093238.
        if screen in {"pause", "map", "phone"} and button is None:
            button = "circle"
        self._button_reads = self._button_reads + 1 if button == self._button else 1
        self._button = button
        if screen == "game" and self._screen is None:
            return None
        if self._reads < 2:
            return FlowResult(action="confirm")
        if screen == "game":
            self._screen = None
            return None

        events: tuple[dict, ...] = ()
        if screen != self._screen:
            self._screen, self._since = screen, now
            self._pressed_at, self._stuck = None, False
            if screen in FAILURES:
                self.failures_in_row += 1
                events = ({"kind": "failure", "screen": screen, "count": self.failures_in_row},)
            elif screen == "passed":
                self.last_pass, self.failures_in_row = now, 0
                events = ({"kind": "pass", "time": now},)
        if self._stuck:
            return FlowResult(action="stuck")
        waiting = screen in {"passed", "loading", "wasted", "busted"}
        # The failure banner precedes its actionable footer by roughly three seconds.
        # A known retry button alone does not prove that the menu is ready for it.
        deadline = self._since + (
            self.wait_timeout if waiting or screen == "failed" else self.response_timeout
        )
        if self._pressed_at is not None:
            deadline = self._pressed_at + self.response_timeout
        if now >= deadline:
            self._stuck = True
            return FlowResult(action="stuck", events=(*events, {"kind": "stuck", "screen": screen}))
        if waiting:
            return FlowResult(action="wait", events=events)
        if screen == "weapon_wheel":
            return FlowResult(action="release", events=events)
        if self._pressed_at is not None and now - self._pressed_at < PRESS_SECONDS:
            return FlowResult(Pad(buttons=(self._pressed[0],)), self._pressed[1], events)
        if self._pressed_at is None and button and self._button_reads >= 2:
            self._pressed_at = now
            self._pressed = (button, "retry" if screen == "failed" else "back")
            return FlowResult(Pad(buttons=(button,)), self._pressed[1], events)
        return FlowResult(action="observe", events=events)
