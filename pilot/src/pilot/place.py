"""One help-text interaction, or one visit to an already entered shop."""

import math
import random
import re
import threading
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import ClassVar

from pilot.contract import Observation, Pad, SkillResult
from pilot.profile import active
from pilot.prompts import normalize, offer, refusal
from pilot.scene import SceneText, TextReader


@dataclass(frozen=True)
class Picture:
    time: float
    text: SceneText


class _TextStream:
    """One reader, one pending frame; slow OCR cannot queue obsolete pictures."""

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
                picture = Picture(now, reader.read(frame))
            except Exception:
                picture = None
            with self.condition:
                if not self.closed:
                    self.latest = picture

    def read(self):
        with self.condition:
            return self.latest

    def close(self):
        with self.condition:
            self.closed = True
            self.pending = None
            self.condition.notify()


class _PlaceSkill:
    parameters: ClassVar = {}

    def __init__(self, args: dict):
        if not isinstance(args, dict) or set(args) - self.parameters.keys():
            raise ValueError(f"{self.name} accepts only {', '.join(self.parameters)}")
        low, high, default = self.parameters["duration"]
        duration = args.get("duration", default)
        if (
            isinstance(duration, bool)
            or not isinstance(duration, (float, int))
            or not math.isfinite(duration)
        ):
            raise ValueError("duration must be a finite number")
        self.limit = float(max(low, min(high, duration)))
        for name, options in self.parameters.items():
            if name != "duration":
                value = args.get(name, options[0])
                if value not in options:
                    raise ValueError(f"{name} must be one of {options}")
                setattr(self, name, value)
        self.profile = active()
        self.text = _TextStream()
        self.started = None
        self.last_time = None
        self.finished = None
        self.button = None
        self.press_time = None
        self.release_at = 0.0
        self.holding = False
        self.consumed = -math.inf

    def stop(self, reason="interrupted") -> SkillResult:
        return self._finish("failed", reason)

    def _finish(self, status, reason):
        self.text.close()
        self.button = None
        self.finished = SkillResult(status=status, reason=reason)
        return self.finished

    def _picture(self, observation):
        now = observation.time
        if isinstance(now, bool) or not isinstance(now, (float, int)) or not math.isfinite(now):
            return None
        if self.last_time is not None and now <= self.last_time:
            return None
        self.last_time = now
        if self.started is None:
            self.started = now
        frame = observation.frame
        if (
            frame is None
            or observation.reading.corrupt
            or getattr(frame, "shape", None) != (720, 1280, 3)
            or str(getattr(frame, "dtype", None)) != "uint8"
        ):
            return None
        self.text.submit(frame, now)
        picture = self.text.read()
        if picture is None or not 0 <= now - picture.time <= 1.0 or picture.time <= self.consumed:
            return None
        self.consumed = picture.time
        return picture

    def _press(self, button, now, kind="press", seconds=0.1):
        self.button = button
        self.press_time = now
        self.release_at = now + seconds
        self.holding = kind == "hold"
        return SkillResult(Pad(buttons=(button,)))

    def _release(self, now):
        if self.button is None:
            return None
        if self.holding and math.isfinite(now) and now < self.release_at:
            return SkillResult(Pad(buttons=(self.button,)))
        # A slow tick must never resend a short press after the bridge released it.
        self.button = None
        return SkillResult()

    def _expired(self, now):
        return self.started is not None and isinstance(now, (float, int)) and now - self.started >= self.limit


class DoPrompt(_PlaceSkill):
    name = "do_prompt"
    parameters: ClassVar = {"duration": (0.2, 10.0, 3.0)}
    prompt = (
        "Press the safe offer in the game's help text once. Done 'pressed: <button>' only when "
        "the text changes or disappears. Fails no-prompt, no-effect, refused: <why> or time-limit."
    )

    def __init__(self, args):
        super().__init__(args)
        self.selected = None
        self.original = None

    def step(self, observation: Observation) -> SkillResult:
        if self.finished:
            return self.finished
        picture = self._picture(observation)
        now = observation.time
        if picture is None:
            self.button = None
            return self.stop("time-limit") if self._expired(now) else SkillResult()
        if self._expired(now):
            return self.stop("time-limit")
        released = self._release(now)
        if released is not None:
            return released
        text = picture.text.help
        if self.selected is None:
            if self._expired(now):
                return self.stop("time-limit")
            why = refusal(text)
            if why:
                return self.stop(f"refused: {why}")
            self.selected = offer(text, observation.frame)
            if self.selected is None:
                return self.stop("no-prompt")
            self.original = normalize(text)
            return self._press(self.selected.button, now, self.selected.kind, self.selected.seconds)
        end = self.release_at if self.selected.kind == "hold" else self.press_time
        if picture.time > end and now - end <= 2.0 and _changed(self.original, normalize(text)):
            return self._finish("done", f"pressed: {self.selected.button}")
        if now - end >= 2.0:
            return self.stop("no-effect")
        return self.stop("time-limit") if self._expired(now) else SkillResult()


def _changed(before: str, after: str) -> bool:
    """Another help text or none, and not the same one read with a letter wrong."""
    return SequenceMatcher(None, before, after).ratio() < 0.8


@dataclass(frozen=True)
class Entry:
    name: str
    price: int | None


AMOUNT = r"\d[\d.,]*"


def _price(label: str) -> tuple[int | None, str]:
    """The price a row shows and the row without it.

    The game writes the sign first: "$115". A number that stands before the sign is the row's own
    ("Jacke 2 $500" costs 500, not 2), so the sign-first reading is tried alone, and a number before
    the sign counts only where no sign-first price is there at all. Of several the highest is taken:
    it is held against a limit, and the mistake to make is not to buy.
    """
    pattern = rf"\$\s*({AMOUNT})"
    found = re.findall(pattern, label)
    if not found:
        pattern = rf"({AMOUNT})\s*\$"
        found = re.findall(pattern, label)
    values = [int(digits) for digits in (re.sub(r"[.,]", "", item) for item in found) if digits]
    if not values:
        return None, label
    return max(values), " ".join(re.sub(pattern, " ", label).split())


RECEIPT = r"gekauft|erworben|purchased|ausgerustet|angelegt"


def menu_entries(text: SceneText) -> list[Entry]:
    """Read left-hand shop rows, including prices OCR split into a separate box."""
    rows = []
    for line in sorted(text.lines, key=lambda item: (item.box[1], item.box[0])):
        x, y, _width, height = line.box
        if line.confidence < 0.5 or x > 650 or y < 145 or y > 610:
            continue
        label = line.text.strip().lstrip("*• ")
        if not label or re.search(
            r"zuruck|auswahl|kaufen|verlassen|select|back|zoom|kamera|gesamt", normalize(label)
        ):
            continue
        if rows and abs(rows[-1][0] - y) <= max(12, height // 2):
            rows[-1][1] += " " + label
        else:
            rows.append([y, label])
    result = []
    for _, label in rows:
        amount, name = _price(label)
        if name and not re.fullmatch(
            r"frisuren|bekleidung|ammu nation|tattoos|garderobe|barber|haarschnitt", normalize(name)
        ):
            result.append(Entry(name, amount))
    return result


class UsePlace(_PlaceSkill):
    name = "use_place"
    parameters: ClassVar = {
        "duration": (5.0, 120.0, 60.0),
        "spend": ("yes", "no"),
        "choice": ("random", "first"),
    }
    prompt = (
        "Inside a shop or at a wardrobe, find its help offer, inspect one menu entry and back out. "
        "spend=no never confirms; spend=yes buys at most one readable item costing at most $150. "
        "Done 'used: <prompt>; bought ...'. Fails no-prompt, menu-unread, wrong-screen or time-limit."
    )
    opens: ClassVar = ("interaction_menu", "shop_menu")
    SPEND_LIMIT = 150  # Kerim sets the maximum price for a single visit.

    def __init__(self, args):
        super().__init__(args)
        self.phase = "search"
        self.phase_time = 0.0
        self.selected = None
        self.random = random.Random(0)
        self.rows_left = None
        self.entry = None
        self.selected_index = None
        self.depth = 0
        self.bought = None
        self.receipts = 0
        self.failure = None
        self.last_action = -math.inf
        self.search_time = 0.0
        self.previous_search_tick = None

    def _closing(self, now, reason=None):
        self.phase = "closing"
        self.phase_time = now
        self.failure = reason

    def _menu(self, observation, text):
        if observation.hud and observation.hud.screen == "interaction_menu":
            return True
        footer = normalize(" ".join(line.text for line in text.lines if line.box[1] > 600))
        if observation.reading.minimap == "none" and re.search(r"kaufen|ausw\w*hlen|zur\w{1,3}k", footer):
            return True
        words = normalize(" ".join(line.text for line in text.lines))
        return bool(
            re.search(
                r"frisuren|haarschnitt|ammu nation|tattoos|garderobe|bekleidung|kleidung|suburban", words
            )
        ) and bool(re.search(r"zuruck|kaufen|auswahl|back|select", words))

    def _game(self, observation, text):
        return (
            observation.hud is not None
            and observation.hud.screen == "game"
            and observation.reading.minimap != "none"
            and not self._menu(observation, text)
        )

    def _action(self, button, now, kind="press", seconds=0.1):
        self.last_action = now
        return self._press(button, now, kind, seconds)

    def step(self, observation: Observation) -> SkillResult:
        if self.finished:
            return self.finished
        picture = self._picture(observation)
        now = observation.time
        if picture is None:
            self.button = None
            return self.stop("time-limit") if self._expired(now) else SkillResult()
        if self._expired(now):
            return self.stop("time-limit")
        released = self._release(now)
        if released is not None:
            return released
        text = picture.text
        screen = observation.hud.screen if observation.hud else "unknown"
        if self.phase != "closing" and now - self.started >= self.limit - min(5.0, self.limit / 3):
            self._closing(now, "time-limit")
        if self.phase != "closing" and screen not in ("game", "interaction_menu", "loading"):
            self._closing(now, f"wrong-screen: {screen}")
        if self.phase == "closing":
            if self._game(observation, text) and picture.time > self.last_action:
                if self.failure:
                    return self.stop(self.failure)
                result = f"used: {self.selected.wording}; bought "
                result += f"{self.bought.name} for {self.bought.price}" if self.bought else "nothing"
                return self._finish("done", result)
            if screen not in ("game", "interaction_menu", "loading"):
                # Another screen has come up, and its buttons are not this skill's: on a failed
                # mission the circle gives the mission up. The reflex has it from here.
                return self.stop(self.failure or f"wrong-screen: {screen}")
            if (
                picture.time > self.last_action + 0.4
                and screen != "loading"
                and self._menu(observation, text)
            ):
                # Only into a menu that is seen: with no map and no menu the picture is a scene, and
                # on foot the circle is a punch.
                return self._action(self.profile.back, now)
            return SkillResult()
        if self.phase == "search":
            why = refusal(text.help)
            if why:
                self._closing(now, f"refused: {why}")
                return SkillResult()
            self.selected = offer(text.help, observation.frame)
            if self.selected:
                self.phase = "opening"
                self.phase_time = now
                return self._action(self.selected.button, now, self.selected.kind, self.selected.seconds)
            if not self._game(observation, text):
                self.previous_search_tick = None
                return SkillResult()
            if self.previous_search_tick is not None:
                self.search_time += min(0.2, now - self.previous_search_tick)
            self.previous_search_tick = now
            if self.search_time >= 8 * 1.2:
                return self.stop("no-prompt")
            # Eight short walks and camera nudges bound the search; indoor yaw is uncalibrated.
            part = self.search_time % 1.2
            return SkillResult(Pad(left=(0.0, -0.25)) if part < 0.6 else Pad(right=(0.45, 0.0)))
        if self.phase == "opening":
            if picture.time <= self.last_action + 0.4:
                return SkillResult()
            if self._menu(observation, text):
                self.phase = "menu"
                self.phase_time = now
            elif now - self.phase_time > 4.0:
                self._closing(now, "menu-unread")
            return SkillResult()
        if self.phase == "menu":
            if picture.time <= self.last_action + 0.4:
                return SkillResult()
            entries = menu_entries(text)
            if not entries:
                if now - self.phase_time > 2.0:
                    self._closing(now, "menu-unread")
                return SkillResult()
            if self.rows_left is None:
                index = self.random.randrange(len(entries)) if self.choice == "random" else 0
                self.rows_left = index
                self.entry = entries[index]
                self.selected_index = index
            if self.rows_left:
                self.rows_left -= 1
                return self._action("down", now)
            if self.spend == "no":
                self._closing(now)
                return SkillResult()
            if self.selected_index >= len(entries) or entries[self.selected_index] != self.entry:
                self._closing(now, "menu-unread")
                return SkillResult()
            if self.entry.price is None:
                categories = {
                    "cheveux",
                    "barte",
                    "frisuren",
                    "haare",
                    "oberteile",
                    "hosen",
                    "schuhe",
                    "hute",
                    "brillen",
                }
                if self.depth == 0 and all(
                    entry.price is None and normalize(entry.name) in categories for entry in entries
                ):
                    self.depth = 1
                    self.rows_left = None
                    self.phase = "submenu"
                    self.phase_time = now
                    return self._action(self.profile.confirm, now)
                self._closing(now, "menu-unread")
                return SkillResult()
            # Which row the game has highlighted is not read, and a press of the d-pad can be lost on
            # its way: the cross may confirm any row on screen. So it is pressed only where every row
            # that is shown has its price read and none is above the limit.
            within = all(item.price is not None and item.price <= self.SPEND_LIMIT for item in entries)
            if self.entry.price <= self.SPEND_LIMIT and within:
                self.phase = "purchase"
                self.phase_time = now
                words = normalize(" ".join(line.text for line in text.lines))
                self.receipts = len(re.findall(RECEIPT, words))
                return self._action(self.profile.confirm, now)
            self._closing(now)
            return SkillResult()
        if self.phase == "submenu":
            if picture.time > self.last_action + 0.4:
                self.phase = "menu"
                self.phase_time = now
            return SkillResult()
        if self.phase == "purchase":
            if picture.time > self.last_action + 0.4:
                # A confirmation is not evidence of a purchase. Require the game's receipt.
                # One more than stood there before the cross: a row that says so of something owned
                # already is no receipt for this one.
                words = normalize(" ".join(line.text for line in text.lines))
                if len(re.findall(RECEIPT, words)) > self.receipts:
                    self.bought = self.entry
                    self._closing(now)
                elif now - self.phase_time >= 2.0:
                    self._closing(now, "menu-unread")
            return SkillResult()
        return SkillResult()
