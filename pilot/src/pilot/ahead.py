"""What the local model sees in a view the figure might walk into: open ground, or the way out of a room.

Kerim, 13 November, of a figure that is stuck: that is where the model is needed again, to look and
say where the way goes on. Asked for a side in the whole picture it had said "right" to every frame
(see `sides`). Asked the plain questions below, one at a time, about frames of that night:

Whether the way straight ahead is open, of 182 frames of the walks: it called 22 of the 28 on which
the guard had found the figure held up blocked, and 149 of the 154 on which the figure ran free
open; four of the five it called blocked there show the fence, the wall or the wreck the figure was
running at. What it misses is what it can see through or past: a chain-link fence, the posts of a
porch, the gap between two boulders, a shop front by night.

Whether the figure is indoors: 61 of 61 frames of the walks outdoors, 31 of 31 inside the barber's.

Whether a way out of the room is in the picture: inside the barber's, where every direction is open
for a few steps and the first question says nothing, it said yes to the three frames of 31 that show
the shop's door and to no other, not to the door marked private either; shown the picture in three
overlapping parts, it named the part the door was in. Outdoors the question is not asked: there a
door leads in.

An answer took 0.14 to 0.17 s. Its yes is a direction worth trying, which the feet still judge.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np

from . import judge
from .sides import open_share

QUESTION = (
    "This is a screenshot of a game. The player's character is seen from behind in the middle of the "
    "picture. Can the character walk straight ahead, away from the camera, for the next few steps?\n"
    "A: yes, the ground straight ahead of the character is open\n"
    "B: no, a wall, a building, a fence, a rock, a vehicle or another obstacle stands right in front of "
    "the character"
)
INDOORS = (
    "This is a screenshot of a game. Is the player's character inside a building, in a room?\n"
    "A: yes, indoors, in a room\n"
    "B: no, outdoors"
)
# Asked first for "a door or doorway through which a person could walk out of the room to the
# outside", yes or no. In an apartment on 13 November that drew the figure to the balcony again and
# again: of 25 frames of its living room the model said yes with 1.00 to the six that show the glass
# door to the balcony, which does lead outside, and 0.00 to 0.47 to the eight that show the corridor
# to the front door. Asked as below, it gave the corridor 1.00 in 8 of 8, the balcony 0.00 in 7 of
# 7, and on Kerim's own walk out of that apartment 0.00 to the bedroom's glass door and 1.00 to the
# bedroom door, the hall and the front door in 9 of 10 frames. The share of A is what counts.
EXIT = (
    "This is {what} of a game, taken inside a room. Which way out of this room does it show?\n"
    "A: a door, a doorway or a corridor that leads on into the building or out to the street\n"
    "B: a window, or a glass door to a balcony or terrace with a railing\n"
    "C: none, only walls, furniture or people"
)
ENTRANCE = (
    "This is {what} of a game, taken outside a building. Does it show a door or doorway "
    "through which a person could walk into the building?\n"
    "A: yes, an entrance is in this picture\n"
    "B: no, only walls, windows, furniture or people"
)
# Where the figure stands, asked of 333 frames on 13 November (lab/models, `bench.py scene`): the 4B
# model named the room in 133 of 133, the landing outside an apartment's door in 31 of 31 and the
# street in 162 of 169, in 0.11 to 0.19 s. A shop's porch, one step above the ground, it calls a
# landing more often than the street.
WHERE = (
    "This is a screenshot of a game. Where is the player's character?\n"
    "A: inside a building, in a room\n"
    "B: outside a building's door on a raised landing, balcony or outside staircase, above the street\n"
    "C: outside at street level, on a road, a pavement, a yard or open ground"
)
PLACES = ("room", "landing", "street")
STAIRS = (
    "This is {what} of a game, taken outside a building on a landing or balcony above the street. "
    "Does it show stairs or steps that lead down from there?\n"
    "A: yes, stairs going down are in this picture\n"
    "B: no, only walls, railings, fences, doors or windows"
)
# Stairs are stairs to that question, whichever way they lead. On 13 November the figure stood on the
# half landing of an outside staircase, the model said yes to the flight that led back up to the
# door, and the figure ran up it and into the apartment it had just left. Asked which way a
# staircase leads, of each part of the picture that showed one, it said up with 0.95 to 1.00 for
# the 14 parts of that flight seen from below and with 0.00 to 0.27 for the middle part of 12 of 13
# frames that look down a flight (0.71 for the other), and up again for the second flight that
# rises beside the way down in Kerim's walk. A part it calls up is not a way down.
WAY = (
    "This is {what} of a game, seen from behind the player's character. A staircase is in the "
    "picture. Seen from where the character stands, where does the staircase lead?\n"
    "A: up, to a level higher than the character\n"
    "B: down, to a level lower than the character"
)
UP = 0.9  # what the model has to give "up" for a staircase to be left out
# Kerim, 13 November, of a figure held up in a room: at a table or a couch it should go round or
# jump, as a player would try; at a wall a jump makes no sense. The feet say that something holds
# the figure up, the model what it is.
LOW = (
    "This is a screenshot of a game. The player's character is seen from behind in the middle of the "
    "picture and cannot walk on: something stands right in front of it. What is it?\n"
    "A: something low that a person could climb or jump over: a table, a couch, a bed, a chair, a "
    "box, a fence or a low wall\n"
    "B: a wall, a door, a window, a cupboard or something else too high to climb over"
)
WIDTH = 640
# The picture's left, middle and right part, overlapping, without the bars at its upper and lower edge.
PARTS = (slice(0, 520), slice(380, 900), slice(760, 1280))
PART_ROWS = slice(60, 640)
PART_WIDTH = 448
SEEN = 0.5  # what the model has to give a yes for it to count as one


@dataclass(frozen=True)
class View:
    """What was said of one frame; a question that was not asked is None."""

    open: float | None = None  # the way straight ahead
    indoors: float | None = None
    exit: float | None = None  # a way out of the room, in, or down the stairs, somewhere in the picture
    parts: tuple[float, float, float] | None = None  # in its left, middle and right part
    where: tuple[float, float, float] | None = None  # the shares of a room, a landing and the street
    low: float | None = None  # what holds the figure up is low enough to jump
    error: str | None = None


class Ahead:
    """Asks in the background and never holds a tick up; one frame at a time."""

    TIMEOUT = 2.0

    def __init__(self, servers, *, transport=None, clock=time.monotonic):
        self.servers = [judge.endpoint(server) for server in servers]
        self.transport = transport if transport is not None else self._request
        self.clock = clock
        self.lock = threading.Lock()
        self.busy = False
        self.result = None  # (capture, View)
        self.log: list[dict] = []

    def _request(self, url, model, image, question):
        return judge.post(url, model, image, question, 3, timeout=self.TIMEOUT)[0]

    def ask(
        self,
        frame,
        capture: float,
        *,
        indoors: bool | None = None,
        ahead: bool = True,
        exit: bool = True,
        entrance: bool = False,
        stairs: bool = False,
        where: bool = False,
        low: bool = False,
    ) -> bool:
        """Begin asking about this frame; False when a frame is still out or this is none.

        `indoors` is what is known of the place already; None has the model asked. `ahead` false
        leaves out the way straight ahead, of a view the feet have judged, and `exit` false the
        way out of a room, where only the place is asked for. `stairs` asks for stairs down, of a
        figure known to stand on a landing, and answers in `exit` and `parts` as a door does.
        `where` asks nothing but which of the three places the figure stands in, and `low`
        nothing but whether what stands in front of the figure can be jumped.
        """
        if not isinstance(frame, np.ndarray) or frame.shape != (720, 1280, 3) or not self.servers:
            return False
        with self.lock:
            if self.busy:
                return False
            self.busy = True
        work = threading.Thread(
            target=self._work,
            args=(frame.copy(), capture, indoors, ahead, exit, entrance, stairs, where, low),
            daemon=True,
        )
        work.start()
        return True

    def _work(
        self, frame, capture, indoors, ahead, exit, entrance=False, stairs=False, where=False, low=False
    ):
        started = self.clock()
        said = {}
        try:
            url, model = self.servers[0]
            bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            whole = judge.encode(bgr, WIDTH)

            def share(image, question):
                return open_share(self.transport(url, model, image, question))

            def first(image, question):
                shares = places(self.transport(url, model, image, question))
                return None if shares is None else shares[0]

            if low:
                said["low"] = share(whole, LOW)
            elif where:
                said["where"] = places(self.transport(url, model, whole, WHERE))
            elif indoors is None and not stairs:
                said["indoors"] = share(whole, INDOORS)
                indoors = said["indoors"] is not None and said["indoors"] >= SEEN
            if where or low:
                pass
            elif (indoors and exit) or entrance or stairs:
                door = STAIRS if stairs else ENTRANCE if entrance else EXIT
                seen = first if door is EXIT else share
                said["exit"] = seen(whole, door.format(what="a screenshot"))
                if said["exit"] is not None and said["exit"] >= SEEN:
                    question = door.format(what="part of a screenshot")
                    images = [judge.encode(bgr[PART_ROWS, part], PART_WIDTH) for part in PARTS]
                    parts = [seen(image, question) or 0.0 for image in images]
                    if stairs:
                        # Only stairs that lead down count: see WAY.
                        if max(parts) < SEEN:
                            if (share(whole, WAY.format(what="a screenshot")) or 0.0) >= UP:
                                said["exit"] = 0.0
                        else:
                            way = WAY.format(what="part of a screenshot")
                            parts = [
                                0.0 if seen >= SEEN and (share(image, way) or 0.0) >= UP else seen
                                for image, seen in zip(images, parts, strict=True)
                            ]
                            if max(parts) < SEEN:
                                said["exit"] = 0.0
                    said["parts"] = tuple(parts)
            elif ahead and not indoors:
                said["open"] = share(whole, QUESTION)
        except Exception as exc:
            said["error"] = f"{type(exc).__name__}: {exc}"
        view = View(**said)
        with self.lock:
            self.busy = False
            self.result = (capture, view)
            self.log.append({"capture": capture, "duration": self.clock() - started, **said})

    def answer(self, since: float) -> View | None:
        """What was said of the frame asked about at `since` or later; None while it is out."""
        with self.lock:
            if self.result is None or self.result[0] < since:
                return None
            return self.result[1]


def places(choice: dict) -> tuple[float, float, float] | None:
    """The shares the model gave a room, a landing and the street; None for a reply without them."""
    found = judge.letters(choice)
    if not found:
        return None
    letter, top = found[0]
    weights = [math.exp(top[key]) if math.isfinite(top.get(key, -math.inf)) else 0.0 for key in "ABC"]
    if sum(weights) > 0:
        return tuple(weight / sum(weights) for weight in weights)
    return tuple(float(letter == key) for key in "ABC") if letter in "ABC" else None


_active: Ahead | None = None
_place: Ahead | None = None
_where: Ahead | None = None


def active() -> Ahead | None:
    return _active


def place() -> Ahead | None:
    """The asker a walk keeps for the place it is in, beside the one its guard looks round with:
    each takes one frame at a time, and neither reads the other's answer."""
    return _place


def where() -> Ahead | None:
    """The asker of the standing question where the figure is, which waits for neither of the others."""
    return _where


def use(servers) -> Ahead | None:
    """The servers a session asks; none switches the asking off."""
    global _active, _place, _where
    from .indoors import forget

    forget()
    _active = Ahead(servers) if servers else None
    _place = Ahead(servers) if servers else None
    _where = Ahead(servers) if servers else None
    return _active
