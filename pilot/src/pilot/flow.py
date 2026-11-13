"""Screen reflexes. Call before the skill; any result suspends that skill's tick."""

import re
import unicodedata
from dataclasses import dataclass

from pilot.contract import NEUTRAL_PAD, Observation, Pad
from pilot.profile import active

# "shop_menu" is no class of the HUD reader, which calls a shop's menu the game (docs/reports/P71): it
# is told here, from a screen without a minimap whose footer offers the way back.
MENUS = frozenset({"pause", "map", "phone", "weapon_wheel", "interaction_menu", "shop_menu"})
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


# The footer of a shop's menu as the reader gives it: "ZurÖck O Kaufen", "ZurÖek O Auswahlen" on the
# three recorded menus (Ammu-Nation 20261111-185323 at 60 s, Suburban 20261111-193105 at 594 s, the
# wardrobe 20261111-210812 at 157 s), each at x 1051 to 1071 and y 663. "Verlassen" is not taken: it
# stands in the footer of a failed mission, where the circle gives the mission up.
BACK = re.compile(r"\bzur\w{1,3}k\b")
# A menu nobody asked for is left after this long: a skill that opened one has said so (`expect`),
# and one that was stopped in the middle of it has had its time.
MENU_OPEN_SECONDS = 3.0
# Between two presses of the way back; the text is read twice a second.
MENU_PRESS_EVERY = 1.0
# Levels of a shop's menu that are backed out of, one press each, before the head is told.
MENU_LEVELS = 6
# The footer is held to be there this long after its last reading: one reading in six misses a line.
MENU_HELD_SECONDS = 1.5
# With an objective read this short a time ago a mission is on, and the menu may be the mission's own
# (the suit for the jeweller, the gun before the long stretch): the head is told first and has this
# long to use it, once in two minutes, before the reflex leaves the menu after all.
MISSION_SECONDS = 90.0
# A footer has to stand this long before it is a menu at all. The text is read half a second behind
# the picture: the map a skill has just closed still stands in it while the screen is the game's again
# and the minimap has not come back, and a reflex that took that for a menu ended the skill.
MENU_SURE_SECONDS = 1.2
# From a press to the picture that shows it; a footer read from an older picture proves nothing.
PICTURE_SECONDS = 0.15
MENU_HEAD_SECONDS = 20.0
MENU_TOLD_EVERY = 120.0


# A call on the phone as the reader gives it on Kerim's recordings. One that comes in: "EINGEHENDER
# ANRUF", "EINGEHENDE ANRUF", "ANBUF", "It¥1 ANRUF" (20261111-183820 at 214.5 s, 20261111-172549 at
# 70.0 s); he takes it with the cross (215.61 s, 70.48 s). One that runs: "VERBUNDEN" read as
# "VER8UNDEN", and "WIRD GEWÄHLT" read as "WIRD QEWAHLT" for one he makes. In the second recording
# nothing on the phone could be read for the thirty seconds the call then ran.
RINGING = re.compile(r"\ban[rb]uf\b|\bein\w{2,5}hende[rn]?\b")
TALKING = re.compile(r"\bve[rb]\wunden\b|ewahlt")
# A phone that has just come up may be a call, and is left alone this long for its text to be read.
PHONE_SECONDS = 2.5
# A call is taken after it has been read to ring this long, so that one misread line takes nothing.
RING_SECONDS = 0.5
# After the last thing read of a call the phone on screen is held to be that call for this long.
CALL_SECONDS = 60.0
# The phone has to be gone this long for a call to be over; the reader loses it for a moment in between.
CALL_GONE_SECONDS = 2.0


def _call(text) -> str | None:
    """`ringing`, `talking` or None, from what stands on the phone."""
    if text is None or isinstance(text, str):
        return None
    words = _fold(
        " ".join(
            line.text
            for line in getattr(text, "lines", ())
            if line.confidence >= 0.5 and (line.region == "phone" or line.box[0] >= 900)
        )
    )
    if TALKING.search(words):
        return "talking"
    return "ringing" if RINGING.search(words) else None


def _menu_left_open(observation, text) -> bool:
    """The game's screen without a minimap, with a footer at the bottom right that offers the way back.

    That is a menu of the game the HUD reader has no name for: a shop's, a wardrobe's. A scene has no
    footer, and what is spoken in one is centred and so begins in the left half of the picture.
    """
    if observation.reading.minimap != "none" or text is None or isinstance(text, str):
        return False
    words = _fold(_words(text))
    if RETRY.search(words) or SKIP.search(words):
        return False
    for line in getattr(text, "lines", ()):
        x, y = line.box[0], line.box[1]
        if line.confidence < 0.5 or y < 640 or x < 640 or len(line.text) > 60:
            continue
        if BACK.search(_fold(line.text)):
            return True
    return False


def _fold(words: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", words.casefold()) if not unicodedata.combining(char)
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
    return profile.back if screen in {"pause", "map", "phone", "interaction_menu", "shop_menu"} else None


class Flow:
    """Two distinct timed reads confirm entry/exit; one pulse per unchanged screen.

    Missing HUD pauses an already active reflex. An expected menu returns None,
    allowing its owning skill to act until the absolute observation-time deadline.
    Events are emitted once; the caller queues them for the head after recovery.
    """

    def __init__(
        self,
        *,
        response_timeout: float = 2.0,
        wait_timeout: float = 30.0,
        skip: bool = True,
        calls: bool = False,
    ):
        self.profile = active()
        if not isinstance(calls, bool):
            raise ValueError("calls must be a boolean")
        # With `calls` a phone is not put away the moment it shows: a call that rings is taken, and
        # one that runs is left to run (see `on_call`). Without, every phone is left by the way back.
        self.calls = calls
        self._phone_time: float | None = None
        self._phone_since: float | None = None
        self._phone_gone: float | None = None
        self._phone_masked = False
        self._call_until: float | None = None
        self._ring_since: float | None = None
        self._answer_at: float | None = None
        self._answers = 0
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
        self._objective_at: float | None = None
        self._menu_seen = 0.0
        self._menu_first: float | None = None
        self._menu_text: float | None = None
        self._menu_told: float | None = None
        self._menu_head = False

    @property
    def screen(self) -> str | None:
        """The screen as the reflex names it: the HUD's class, or what it tells apart on the game's."""
        return self._screen or self._candidate

    def on_call(self, observation: Observation, text: object = None) -> bool:
        """Whether the phone on screen is, for everything behind the reflex, the game.

        It is while a call rings or runs, and for the first seconds of any phone, which may be one:
        the figure walks and drives on through a call as a player does, and the plan is kept. A phone
        that shows no call in those seconds is a menu like any other and is left by the way back.
        The conductor asks this before the skills and the head see the tick; `tick` asks it as well.
        """
        now = observation.time
        if not self.calls:
            return False
        if self._phone_time is not None and now <= self._phone_time:
            return self._phone_masked
        self._phone_time = now
        hud = observation.hud
        if hud is None or observation.reading.corrupt:
            return self._phone_masked  # nothing read: as it was
        if hud.screen != "phone":
            if self._phone_since is not None:
                if self._phone_gone is None:
                    self._phone_gone = now
                if now - self._phone_gone >= CALL_GONE_SECONDS:
                    self._phone_since = self._phone_gone = self._call_until = None
                    self._ring_since = self._answer_at = None
                    self._answers = 0
            self._phone_masked = False
            return False
        self._phone_gone = None
        if self._phone_since is None:
            self._phone_since = now
        call = _call(text)
        if call is not None:
            self._call_until = now + CALL_SECONDS
        if call == "ringing":
            if self._ring_since is None:
                self._ring_since = now
        elif call == "talking" or text is not None:
            self._ring_since = None  # read, and not ringing; an unread tick keeps what was read last
        calling = self._call_until is not None and now < self._call_until
        self._phone_masked = calling or now - self._phone_since < PHONE_SECONDS
        return self._phone_masked

    def _answer(self, now: float) -> FlowResult | None:
        """The one press that takes a ringing call, once more if it still rings after its time."""
        confirm = self.profile.confirm
        if self._answer_at is not None and now - self._answer_at < PRESS_SECONDS:
            return FlowResult(Pad(buttons=(confirm,)), "answer")
        if (
            self._ring_since is not None
            and now - self._ring_since >= RING_SECONDS
            and self._answers < MAX_PRESSES
            and (self._answer_at is None or now - self._answer_at >= self.response_timeout)
        ):
            self._answer_at, self._answers = now, self._answers + 1
            return FlowResult(Pad(buttons=(confirm,)), "answer")
        return None

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
            self._objective_at = now
        banner = getattr(text, "banner", None)
        candidate = banner.casefold().strip() if banner else None
        self._mission_reads = self._mission_reads + 1 if candidate == self._mission_candidate else 1
        self._mission_candidate = candidate
        if candidate and self._mission_reads >= 2 and candidate != self.mission:
            self.mission = candidate
            self.failures_in_row = 0
            self._failed_mission = None

    def reset(self) -> None:
        """Forget the screen in hand, after time in which the pad was not the pilot's.

        What was pressed into a refused pad never reached the console: the counts and the times of it
        would leave the reflex stuck on a screen it has not yet pressed anything into."""
        self._candidate = self._screen = None
        self._reads = 0
        self._engaged = False
        self._pressed_at = self._pressed = None
        self._presses = 0
        self._stuck = False
        self._button, self._button_reads = None, 0
        self._menu_first = None
        self._menu_head = False
        self._ring_since = self._answer_at = None
        self._answers = 0

    def tick(
        self, observation: Observation, text: object = None, text_time: float | None = None
    ) -> FlowResult | None:
        """`text_time`: when the picture was taken that `text` was read from, where the caller knows."""
        now = observation.time
        if self._last_time is not None and now <= self._last_time:
            return FlowResult(action="await_fresh_read") if self._engaged else None
        self._last_time = now
        if observation.reading.corrupt and (observation.hud is None or observation.hud.screen not in MENUS):
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
        if self.on_call(observation, text) and screen == "phone":
            answer = self._answer(now)
            if answer is not None:
                return answer
            screen = "game"  # a call, or a phone that may be one: not a screen to leave
        if screen == "game" and _alert(text):
            screen = "alert"
        elif screen == "game" and _menu_left_open(observation, text):
            screen, self._menu_seen, self._menu_text = "shop_menu", now, text_time
        elif (
            screen == "game"
            and self._menu_first is not None
            and observation.reading.minimap == "none"
            and now - self._menu_seen < MENU_HELD_SECONDS
        ):
            screen = "shop_menu"
        if screen != "shop_menu":
            self._menu_first = None
        else:
            if self._menu_first is None:
                self._menu_first = now
            if now - self._menu_first < MENU_SURE_SECONDS or (self._expected and now < self._expected[1]):
                # Not a menu yet, or a skill has a screen of its own open and this is its doing.
                screen = "game"
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
                self._objective_at = None
                events = ({"kind": "pass", "time": now},)
            elif screen == "shop_menu":
                mission = self._objective_at is not None and now - self._objective_at < MISSION_SECONDS
                told = self._menu_told is not None and now - self._menu_told < MENU_TOLD_EVERY
                self._menu_head = mission and not told
        if screen == "shop_menu":
            return self._shop_menu(now, events)
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

    def _shop_menu(self, now, events):
        """A shop's menu that no skill has asked for: left by the way back, level by level.

        In a mission the head is told first, since the menu may be what the mission wants used; it has
        its seconds, and after them, or when it has been told within the last two minutes, the menu is
        left as in free roam. Nothing but the way back is ever pressed here.
        """
        stuck = {"kind": "stuck", "screen": "shop_menu"}
        held = now - self._since
        back = self.profile.back
        if self._pressed_at is not None and now - self._pressed_at < PRESS_SECONDS:
            return FlowResult(Pad(buttons=(back,)), "back", events)
        if self._menu_head:
            if held < MENU_HEAD_SECONDS:
                if self._stuck:
                    return FlowResult(action="stuck", events=events)
                self._stuck, self._menu_told = True, now
                return FlowResult(action="stuck", events=(*events, stuck))
            self._menu_head = self._stuck = False
        elif self._stuck:
            return FlowResult(action="stuck", events=events)
        elif self._pressed_at is None and held < MENU_OPEN_SECONDS:
            return FlowResult(action="observe", events=events)
        if self._pressed_at is not None:
            if now - self._pressed_at < MENU_PRESS_EVERY:
                return FlowResult(action="observe", events=events)
            if self._presses >= MENU_LEVELS:
                self._stuck = True
                return FlowResult(action="stuck", events=(*events, stuck))
        stale = (
            self._pressed_at is not None
            and self._menu_text is not None
            and self._menu_text <= self._pressed_at + PICTURE_SECONDS
        )
        if self._menu_seen != now or stale:
            # The footer is only held to be there, or was read from a picture older than the last
            # press: a press needs it read since, so that the last press of the way out is not followed
            # by one more into the game, where on foot the circle is a punch.
            return FlowResult(action="observe", events=events)
        self._pressed_at, self._pressed = now, (back, "back")
        self._presses += 1
        return FlowResult(Pad(buttons=(back,)), "back", events)
