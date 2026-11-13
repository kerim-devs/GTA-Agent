"""Read the pause map's legend and select a destination by its printed name."""

import math
import re
from dataclasses import dataclass, replace
from itertools import pairwise

import numpy as np

from .contract import Pad, SkillResult
from .profile import active
from .scene import TextReader

KINDS = {
    "mission": (
        "Fremde und Freaks",
        "Lester",
        "Michael",
        "Franklin",
        "Trevor",
        "B",
        "D",
        "F",
        "H",
        "L",
        "M",
        "S",
        "T",
    ),
    "shop": (
        "Ammu-Nation",
        "Ammu-Nation mit Schießstand",
        "Autowaschanlage",
        "Beekers Garage",
        "Binco Bekleidung",
        "Discount Store",
        "Friseursalon",
        "Garage in Pillbox Hill",
        "Los Santos Customs",
        "Ponsonbys",
        "Suburban",
        "Tattoo-Studio",
    ),
    "pastime": (
        "Fahrgeschäft",
        "Geländerennen Motorrad/Quad",
        "Golf",
        "Kino",
        "Seilbahn",
        "Tennis",
        "Triathlon",
        "Straßenrennen",
        "Seerennen",
        "Flugschule",
        "Fallschirmsprung",
    ),
    "none": ("Spieler", "Wegpunkt", "Persönliches Fahrzeug", "Fahrzeug"),
}
DIRECTIONS = {"up", "down", "left", "right"}
ARROWS = re.compile(r"[<\u2039\u00ab]\s*(\d+)\s*/\s*(\d+)\s*[>\u203a\u00bb]")
# What follows a name when its arrows are misread ("Los Santos Customs < 114> i" for "< 1/4 >").
ARROWS_LEFT = re.compile(r"\s*[<\u2039\u00ab]\s*\d.*$")
COUNTER = re.compile(r"^(\d+)\s*/\s*(\d+)$")
WAYPOINT = re.compile(r"^Wegpunkt\s*\(\s*(\d+(?:[.,]\d+)?)\s*(km|m)\s*\)", re.I)


def kind_of(name):
    if re.search(r"[$€£]|\b(immobilie|property|kaufen|purchase|for sale|zum verkauf)\b", name, re.I):
        return "property"
    return next(
        (kind for kind, names in KINDS.items() if name.casefold() in {n.casefold() for n in names}), "other"
    )


def clean_name(text):
    text = text.strip()
    # OCR reads the icon before or after a known name as a stray letter.
    known = [n for names in KINDS.values() for n in names] + ["Chinesen"]
    for name in sorted(known, key=len, reverse=True):
        match = re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text, re.I)
        if match and len(text[: match.start()].strip()) <= 2 and len(text[match.end() :].strip()) <= 3:
            return name
    return text


@dataclass(frozen=True)
class Entry:
    name: str
    kind: str
    instance: int | None = None
    count: int | None = None


@dataclass(frozen=True)
class Legend:
    screen: str | None = None
    entries: tuple[Entry, ...] = ()
    selected: Entry | None = None
    position: int | None = None
    total: int | None = None
    distance: float | None = None
    distances: tuple[
        float, ...
    ] = ()  # of every waypoint row: after a cross the old one lingers beside the new


def white_bar(frame, box):
    """The legend prints the selected row black on a white bar and every other row white on dark.

    In the recording by hand (20261112-104238, 106 readings of the map) exactly one row is white in
    every reading: the darkest channel's median under a selected name is 246 and more, under 95 in
    100 of the others 86 and less.
    """
    x, y, w, h = (int(value) for value in box)
    patch = frame[y : y + h, x : x + w]
    return patch.size > 0 and float(np.median(patch.min(axis=2))) >= 180


def read_legend(lines, frame=None):
    """Parse native TextLines or stored OCR dictionaries; with the frame the white bar names the selection.

    The counter's denominator is kept as OCR evidence, not a traversal bound.
    """
    lines = getattr(lines, "lines", lines)
    rows = []
    for line in lines:
        confidence = line.get("confidence", 1.0) if isinstance(line, dict) else line.confidence
        if confidence < 0.5:
            continue
        text = line["text"] if isinstance(line, dict) else line.text
        box = line["box"] if isinstance(line, dict) else line.box
        rows.append((text.strip(), box))
    footer = " ".join(text.casefold() for text, box in rows if box[1] > 610)
    map_open = "markierung wählen" in footer and "wegpunkt" in footer
    pause = any(text.upper() == "KARTE" and box[1] < 160 for text, box in rows)
    screen = "map" if map_open else "pause" if pause else None
    entries, selected, position, total, distance = [], None, None, None, None
    distances = []
    entry_rows = []
    selections = []
    bars = []
    # The legend is set flush right: all 2,012 rows of the recording by hand end between 1188 and 1215.
    # Writing of the world behind the map (a sign reading "SANDY'S", session 20261112-121107) does not.
    # A long row begins far to the left: "Immobilie: McKenzie-Feldhangar: 150.000 $" at 877, where the
    # selection stood on it unread for forty seconds (session 20261113-000319).
    body = sorted(
        (
            row
            for row in rows
            if row[1][0] >= 780 and 25 <= row[1][1] < 600 and 1180 <= row[1][0] + row[1][2] <= 1225
        ),
        key=lambda row: row[1][1],
    )
    grouped = []
    for row in body:
        if grouped and abs(row[1][1] - grouped[-1][1][1]) <= 8:
            if len(row[0]) > len(grouped[-1][0]):
                grouped[-1] = row
        else:
            grouped.append(row)
    for text, box in grouped:
        counter = COUNTER.fullmatch(text)
        if counter and box[1] >= 540:
            position, total = map(int, counter.groups())
            if position < 1 or total < position:
                position, total = None, None
            continue
        if box[1] >= 540:
            continue
        barred = frame is not None and white_bar(frame, box)
        waypoint = WAYPOINT.match(text)
        if waypoint:
            distance = float(waypoint[1].replace(",", ".")) * (1000 if waypoint[2].lower() == "km" else 1)
            distances.append(distance)
            entries.append(Entry("Wegpunkt", "none"))
            entry_rows.append(box[1])
            if barred:
                bars.append(entries[-1])
            continue
        arrows = ARROWS.search(text)
        name = clean_name(text[: arrows.start()] if arrows else ARROWS_LEFT.sub("", text))
        if not name or not any(c.isalpha() for c in name) or (len(name) <= 2 and kind_of(name) == "other"):
            continue
        entry = Entry(
            name, kind_of(name), int(arrows[1]) if arrows else None, int(arrows[2]) if arrows else None
        )
        entries.append(entry)
        entry_rows.append(box[1])
        if barred:
            bars.append(entry)
        if arrows and 1 <= entry.instance <= entry.count:
            selections.append(entry)
    # A kind with one place has no arrows; the bar is there for every entry on every page.
    if len(bars) == 1:
        selected = bars[0]
    elif len(selections) == 1:
        selected = selections[0]
    # Without arrows, a counter is sufficient only on the anchored first page.
    if (
        selected is None
        and position is not None
        and entries
        and entries[0].name == "Spieler"
        and position <= len(entries)
        and not selections
        and all(18 <= b - a <= 35 for a, b in pairwise(entry_rows))
    ):
        selected = entries[position - 1]
    return Legend(screen, tuple(entries), selected, position, total, distance, tuple(distances))


class LegendWaypoint:
    """A bounded map transaction; every new press requires a stable readable screen."""

    settle = 0.35  # More than twice the measured clean-cable frame delay (0.14 s).
    stable_for = 0.15
    max_attempts = 3
    # The legend showed a new waypoint 0.7 s after its cross (session 20261112-115941).
    legend_lag = 2.0
    max_steps = 80

    def __init__(self, args):
        self.profile = active()
        self.place = args.get("place", "").strip()
        self.kind = args.get("kind", "none")
        self.instance = args.get("instance", 0)
        self.limit = min(45.0, max(1.0, args.get("duration", 45.0)))
        self.reader = None
        self.started = self.last_time = None
        self.finished = None
        self.phase = "open"
        self.failure = None
        self.held = Pad()
        self.release_at = self.ready_at = 0.0
        self.pressed = None
        self.hold = False
        self.command_frame = None
        self.stable_key = self.stable_since = None
        self.pending = None
        self.attempts = 0
        self.visited = set()
        self.observed_places = {}
        self.candidate_places = {}
        self.destination = None
        self.distance = None
        self.before = None
        self.standing = None
        self.total_before = None
        self.steps = 0

    def stop(self, reason="interrupted"):
        self.finished = SkillResult(status="failed", reason=reason)
        return self.finished

    def _picture(self, frame):
        if self.reader is None:
            self.reader = TextReader()
        text = self.reader.read(frame)
        picture = read_legend(text, frame)
        # The OCR sees KARTE on every pause tab; only its selected white tab authorises Cross.
        from .waypoint import map_screen

        screen = map_screen(frame, text)
        if screen == "overview":
            screen = "pause"
        elif screen != "map":
            tabs = {line.text.upper() for line in text.lines if line.box[1] < 160}
            screen = "menu" if len(tabs & {"KARTE", "STATISTIKEN", "EINSTELLUNGEN", "SPIEL"}) >= 3 else None
        return replace(picture, screen=screen)

    def _press(self, button, observation, pending):
        self.held = Pad(buttons=(button,))
        self.release_at = observation.time + (0.06 if button in DIRECTIONS else 0.10)
        self.pressed = observation.time
        self.hold = True
        self.ready_at = self.release_at + self.settle
        self.command_frame = observation.frame.copy()
        self.pending = pending
        self.stable_key = None
        return SkillResult(self.held)

    def _fail(self, reason):
        self.failure = self.failure or reason
        self.phase = "exit"
        self.pending = None
        self.attempts = 0
        return SkillResult()

    def _stable(self, key, now):
        if key != self.stable_key:
            self.stable_key, self.stable_since = key, now
            return False
        return now - self.stable_since >= self.stable_for

    def _result(self):
        places = ", ".join(self.observed_places)
        if self.failure:
            return self.stop(f"{self.failure}; gameplay observed; places: {places}")
        distance = "distance not read" if self.distance is None else f"{self.distance:g}m"
        self.finished = SkillResult(
            status="done",
            reason=f"waypoint set: {self.destination} ({distance}); gameplay observed; places: {places}",
        )
        return self.finished

    def step(self, observation):
        if self.finished is not None:
            return self.finished
        now = observation.time
        if not math.isfinite(now) or (self.last_time is not None and now < self.last_time):
            return self.stop("clock-invalid; screen not verified")
        self.last_time = now
        if self.started is None:
            self.started = now
        elapsed = now - self.started
        if elapsed >= self.limit:
            return self.stop(f"time-limit: {self.failure or self.phase}; gameplay not verified")
        # Reserve time for two backs and their observed releases before the hard deadline.
        if self.phase != "exit" and elapsed >= max(0.0, self.limit - 4.0):
            self._fail("time-limit")
        if observation.frame is None or observation.reading.corrupt:
            self.stable_key = None
            self.candidate_places.clear()
            self.release_at = 0.0
            self.hold = False
            return SkillResult()
        game = (
            observation.reading.minimap in {"flat", "tilted"}
            and observation.reading.confidence >= 0.6
            and (observation.hud is None or observation.hud.screen == "game")
        )
        try:
            picture = Legend() if game else self._picture(observation.frame)
        except Exception:
            self.stable_key = None
            self.candidate_places.clear()
            self.release_at = 0.0
            self.hold = False
            return SkillResult()
        screen = "game" if game else picture.screen
        if self.hold:
            # A direction that is held moves the selection again: in session 20261112-115658 holds of
            # 0.25 s and 0.35 s each stepped over an entry, one of 0.19 s did not. A tick with the text
            # reader in it takes 0.08 to 0.17 s, so a direction is let go on the tick after its press.
            # So is every other button, on a tick that read the screen's text: its pad goes out when
            # the reading is done, and the button has been down for as long by then. The bridge lets
            # go of a pad that is not sent again within 250 ms, so a button sent on two such ticks is
            # two presses where the second is slower than that: on 13 November, 01:12 and 01:28, it
            # took 0.37 s, the game got the cross twice, the second took away the waypoint the first
            # had set, and the skill, which had read the new distance, called it set.
            if self.held.buttons[0] not in DIRECTIONS and not game:
                self.release_at = now
                self.ready_at = now + 0.10 + self.settle
            self.hold = False
        if now < self.release_at:
            allowed = {"game", "pause"} if self.held.buttons == (self.profile.pause,) else {"pause", "map"}
            if self.held.buttons == (self.profile.back,):
                allowed.add("menu")
            return SkillResult(self.held) if screen in allowed else SkillResult()
        if now < self.ready_at:
            return SkillResult()
        if self.command_frame is not None and np.array_equal(observation.frame, self.command_frame):
            self.stable_key = None
            return SkillResult()
        candidates = {}
        if screen == "map":
            for entry in picture.entries:
                if entry.kind != "none":
                    since = self.candidate_places.get(entry.name, now)
                    candidates[entry.name] = since
                    if now - since >= self.stable_for:
                        self.observed_places[entry.name] = entry.kind
        self.candidate_places = candidates
        if screen == "map" and picture.entries and picture.entries[0].name == "Spieler":
            # The waypoint's row is the second of the list: with the list's head in sight it is known.
            self.standing = picture.distances[-1] if picture.distances else None
        key = (screen, picture.selected, picture.position, picture.distances)
        if not self._stable(key, now):
            return SkillResult()
        if self.phase == "exit":
            if game:
                return self._result()
            # Unknown pictures never authorise even a back button.
            if screen in {"map", "pause", "menu"}:
                return self._press(self.profile.back, observation, ("exit", screen))
            return SkillResult()
        if self.phase == "open":
            if not game:
                return self.stop("start-screen-unverified; start from visible gameplay")
            self.phase = "enter"
            self.attempts = 1
            return self._press(self.profile.pause, observation, ("open",))
        if screen is None or screen == "menu":
            return self._fail("menu-not-map; inspect the screen")
        if screen == "game":
            if self.phase == "enter" and self.pending == ("open",) and self.attempts < self.max_attempts:
                self.attempts += 1
                return self._press(self.profile.pause, observation, ("open",))
            return self._fail("menu-not-map")
        if screen == "pause":
            if self.phase not in {"enter", "browse"}:
                return self._fail("menu-not-map")
            self.attempts = self.attempts + 1 if self.pending == ("enter",) else 1
            if self.attempts > self.max_attempts:
                return self._fail("map-did-not-open")
            self.phase = "browse"
            return self._press(self.profile.confirm, observation, ("enter",))
        if self.phase == "confirm":
            # The cross moves a waypoint that stands elsewhere and takes away one that stands on this
            # very place: in session 20261112-115941 a second cross on Los Santos Customs took the new
            # waypoint away again, and the skill called it set. The legend follows a press late and
            # lists the old waypoint beside the new for a while. So the proof is a distance that was
            # not there before the press, and the cross is pressed again only when the legend has had
            # its time and shows that the first one took a waypoint away or did nothing.
            fresh = [value for value in picture.distances if value != self.before]
            if fresh:
                self.distance = fresh[0]
                self.phase = "exit"
                return SkillResult()
            if picture.selected is None or picture.selected.name != self.destination:
                return self._fail("selection-changed-before-waypoint")
            if not picture.entries or picture.entries[0].name != "Spieler":
                # On a later page the waypoint's row is out of sight. A new waypoint shows there as
                # one entry more in the counter; without that sign the try ends here.
                if self.total_before is not None and picture.total == self.total_before + 1:
                    self.phase = "exit"
                    return SkillResult()
                if now - self.pressed < self.legend_lag:
                    return SkillResult()
                return self._fail("waypoint-unproven-on-a-later-page")
            if now - self.pressed < self.legend_lag:
                return SkillResult()
            if not picture.distances and self.before is not None:
                self.before = None  # it stood on this very place and is gone: the next cross sets it
            self.attempts += 1
            if self.attempts > self.max_attempts:
                return self._fail("waypoint-not-visible-after-cross")
            return self._press(self.profile.confirm, observation, ("confirm",))
        selected = picture.selected
        if selected is None:
            return SkillResult()
        self.phase = "browse"
        # A name stands in the legend once; the counter under it is misread too often to be asked for.
        identity = (selected.name, selected.instance)
        if self.pending and self.pending[0] == "move":
            if identity == self.pending[1]:
                self.attempts += 1
                if self.attempts > self.max_attempts:
                    return self._fail("legend-selection-did-not-move")
                return self._press(self.pending[2], observation, self.pending)
            self.attempts = 0
            self.pending = None
        if self._wanted(selected):
            if self.instance and selected.instance != self.instance:
                if selected.count is None or self.instance > selected.count:
                    return self._fail("place-instance-not-present")
                button = "right" if selected.instance < self.instance else "left"
                self.attempts = 1
                return self._press(button, observation, ("move", identity, button))
            self.destination = selected.name
            self.before = self.standing
            self.total_before = picture.total
            self.phase = "confirm"
            self.attempts = 1
            return self._press(self.profile.confirm, observation, ("confirm",))
        self.steps += 1
        if self.steps > self.max_steps:
            return self._fail("legend-selection-skips-the-place")
        # A press now and then moves the selection by two (the third of 20261112-115941, held for
        # 0.15 s), so the way is read off the page: towards the place while it is in sight.
        names = [entry.name for entry in picture.entries]
        here = names.index(selected.name) if selected.name in names else None
        there = next((i for i, entry in enumerate(picture.entries) if self._wanted(entry)), None)
        button = "down"
        if there is None:
            if selected.name in self.visited:
                seen = any(self._wanted(Entry(name, kind)) for name, kind in self.observed_places.items())
                reason = "legend-selection-skips-the-place" if seen else "place-not-in-legend"
                return self._fail(f"{reason}: {self.place or self.kind}")
            self.visited.add(selected.name)
        elif here is not None and there < here:
            button = "up"
        self.attempts = 1
        return self._press(button, observation, ("move", identity, button))

    def _wanted(self, entry):
        if entry.kind in {"none", "property"} or kind_of(entry.name) == "property":
            return False
        return entry.name.casefold() == self.place.casefold() if self.place else entry.kind == self.kind
