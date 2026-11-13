"""Screen reflexes. Call before the skill; any result suspends that skill's tick."""

import re
import unicodedata
from dataclasses import dataclass

from pilot.contract import NEUTRAL_PAD, Observation, Pad
from pilot.profile import active

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
SKIP = re.compile(r"\b(überspringen|uberspringen|skip)\b", re.I)
CONTINUE = re.compile(r"\b(weiter|fortfahren|continue)\b", re.I)
UNSAFE_ALERT = re.compile(
    r"gta\s*online|\bonline\b|speicher|save|laden|load|kauf|buy|purchase|"
    r"geld|money|cash|store|shop|\$|€|\b(ja|nein|yes|no|abbrechen|cancel|zurück|back)\b",
    re.I,
)


def _words(text):
    if isinstance(text, str):
        return text
    lines = getattr(text, "lines", ())
    return " ".join(
        [
            str(getattr(text, field, "") or "")
            for field in ("help", "objective", "subtitle", "banner", "phone_menu")
        ]
        + [line.text for line in lines]
    )


def _skip_offered(text):
    def offered(words):
        words = "".join(
            char for char in unicodedata.normalize("NFKD", words) if not unicodedata.combining(char)
        )
        return bool(SKIP.search(words))

    if isinstance(text, str):
        return offered(text)
    return any(
        line.confidence >= 0.5 and line.box[1] >= 585 and offered(line.text)
        for line in getattr(text, "lines", ())
    )


def _single_continue(text):
    words = _words(text)
    if UNSAFE_ALERT.search(words):
        return False
    lines = getattr(text, "lines", ())
    if lines:
        footer = [line.text for line in lines if line.confidence >= 0.7 and line.box[1] >= 585]
        return len(footer) == 1 and bool(
            re.fullmatch(
                r"\s*(?:[xX\u00d7]\s*)?(?:weiter|fortfahren|fortsetzen|continue)(?:\s*[xX\u00d7])?\s*",
                footer[0],
                re.I,
            )
        )
    return bool(
        re.fullmatch(
            r"\s*(?:[xX\u00d7]\s*)?(?:weiter|fortfahren|fortsetzen|continue)(?:\s*[xX\u00d7])?\s*",
            words,
            re.I,
        )
    )


def _alert(text):
    # HUD has no alert class. Require the dialog title in its central box, not a subtitle.
    return any(
        line.confidence >= 0.8
        and 190 <= line.box[0] <= 1000
        and 80 <= line.box[1] <= 490
        and line.text.strip().casefold() in {"alert", "alarm", "hinweis", "warnung"}
        for line in getattr(text, "lines", ())
    )


def _button(text: object, screen: str, profile) -> str | None:
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
        return profile.retry if RETRY.search(words.lower()) else None
    # Circle: phone t=156.294, map levels t=391.932/392.133. The interaction menu names circle
    # for "Zurück" in its footer, frames 1300 to 1513 of the screen tour of 11 November.
    return profile.back if screen in {"pause", "map", "phone", "interaction_menu"} else None


class Flow:
    """Two distinct timed reads confirm entry/exit; one pulse per unchanged screen.

    Missing HUD pauses an already active reflex. An expected menu returns None,
    allowing its owning skill to act until the absolute observation-time deadline.
    Events are emitted once; the caller queues them for the head after recovery.
    """

    def __init__(self, *, response_timeout: float = 2.0, wait_timeout: float = 30.0, skip: bool = True):
        self.profile = active()
        if response_timeout < 0.14 or wait_timeout < response_timeout:
            raise ValueError("timeouts must allow the 0.14s picture delay")
        self.response_timeout = response_timeout
        self.wait_timeout = wait_timeout
        if not isinstance(skip, bool):
            raise ValueError("skip must be a boolean")
        self.skip = skip
        self.mission = None
        self._mission_candidate = None
        self._mission_reads = 0
        self._play_since = None
        self._objective = None
        self._failed_mission = None
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

    def _track_mission(self, screen, text, now):
        if screen != "game":
            self._play_since = None
            return
        if self._play_since is None:
            self._play_since = now
        if now - self._play_since >= 600:
            self.failures_in_row = 0
            self._failed_mission = None
            self._play_since = now
        objective = getattr(text, "objective", None)
        if objective:
            self._objective = objective.casefold().strip()
        banner = getattr(text, "banner", None)
        candidate = banner.casefold().strip() if banner else None
        self._mission_reads = self._mission_reads + 1 if candidate == self._mission_candidate else 1
        self._mission_candidate = candidate
        if candidate and self._mission_reads >= 2 and candidate != self.mission:
            self.mission = candidate
            self.failures_in_row = 0
            self._failed_mission = None

    def tick(self, observation: Observation, text: object = None) -> FlowResult | None:
        now = observation.time
        if self._last_time is not None and now <= self._last_time:
            return FlowResult(action="await_fresh_read") if self._engaged else None
        self._last_time = now
        if observation.reading.corrupt:
            self._reads = 0
            self._button, self._button_reads = None, 0
            if self._screen == "alert" and self._pressed_at is None:
                self._since = now
            return FlowResult(action="await_frame") if self._engaged else None
        if observation.hud is None:
            self._reads = 0
            self._button, self._button_reads = None, 0
            pending = self._engaged
            return FlowResult(action="await_hud") if pending else None
        screen = observation.hud.screen
        if screen == "game" and _alert(text):
            screen = "alert"
        self._track_mission(screen, text, now)
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
        button = _button(text, screen, self.profile)
        if (
            screen == "failed"
            and self.skip
            and self.failures_in_row + (screen != self._screen) >= 3
            and _skip_offered(text)
        ):
            button = self.profile.skip
        if screen == "alert" and _single_continue(text):
            button = self.profile.confirm
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
                mission = self.mission or self._objective
                if mission and self._failed_mission and mission != self._failed_mission:
                    self.failures_in_row = 0
                self._failed_mission = mission
                self.failures_in_row += 1
                events = ({"kind": "failure", "screen": screen, "count": self.failures_in_row},)
            elif screen == "passed":
                self.last_pass, self.failures_in_row = now, 0
                self.mission = self._objective = self._failed_mission = None
                events = ({"kind": "pass", "time": now},)
        if self._stuck:
            return FlowResult(action="stuck")

        if screen == "alert":
            if not _single_continue(text):
                self._stuck = True
                return FlowResult(action="stuck", events=(*events, {"kind": "stuck", "screen": screen}))
            if self._pressed_at is None and now - self._since >= 2 and self._button_reads >= 2:
                self._pressed_at = now
                return FlowResult(Pad(buttons=(self.profile.confirm,)), "continue", events)
            if self._pressed_at is not None and now - self._pressed_at < PRESS_SECONDS:
                return FlowResult(Pad(buttons=(self.profile.confirm,)), "continue", events)
            if self._pressed_at is not None and now - self._pressed_at >= self.response_timeout:
                self._stuck = True
                return FlowResult(action="stuck", events=(*events, {"kind": "stuck", "screen": screen}))
            return FlowResult(action="observe", events=events)
        waiting = screen in {"passed", "loading", "wasted", "busted"}
        ready = bool(button) and self._button_reads >= 2
        again = False
        if self._pressed_at is not None:
            # A press gets response_timeout to change the picture, then one more press does.
            if now - self._pressed_at >= self.response_timeout:
                again = ready and self._presses < MAX_PRESSES and self._pressed[1] != "skip"
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
            action = (
                "skip"
                if screen == "failed" and button == self.profile.skip
                else "retry"
                if screen == "failed"
                else "back"
            )
            self._pressed = (button, action)
            if action == "skip" and self._presses == 1:
                events = (
                    *events,
                    {"kind": "mission_skip", "mission": self._failed_mission, "count": self.failures_in_row},
                )
            return FlowResult(Pad(buttons=(button,)), self._pressed[1], events)
        return FlowResult(action="observe", events=events)
