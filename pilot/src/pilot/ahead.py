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
EXIT = (
    "This is {what} of a game, taken inside a room. Does it show a door or doorway through "
    "which a person could walk out of the room to the outside?\n"
    "A: yes, an exit to the outside is in this picture\n"
    "B: no, only walls, windows, furniture or people"
)
ENTRANCE = (
    "This is {what} of a game, taken outside a building. Does it show a door or doorway "
    "through which a person could walk into the building?\n"
    "A: yes, an entrance is in this picture\n"
    "B: no, only walls, windows, furniture or people"
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
    exit: float | None = None  # a way out of the room, somewhere in the picture
    parts: tuple[float, float, float] | None = None  # in its left, middle and right part
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
    ) -> bool:
        """Begin asking about this frame; False when a frame is still out or this is none.

        `indoors` is what is known of the place already; None has the model asked. `ahead` false
        leaves out the way straight ahead, of a view the feet have judged, and `exit` false the
        way out of a room, where only the place is asked for.
        """
        if not isinstance(frame, np.ndarray) or frame.shape != (720, 1280, 3) or not self.servers:
            return False
        with self.lock:
            if self.busy:
                return False
            self.busy = True
        work = threading.Thread(
            target=self._work, args=(frame.copy(), capture, indoors, ahead, exit, entrance), daemon=True
        )
        work.start()
        return True

    def _work(self, frame, capture, indoors, ahead, exit, entrance=False):
        started = self.clock()
        said = {}
        try:
            url, model = self.servers[0]
            bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            whole = judge.encode(bgr, WIDTH)

            def share(image, question):
                return open_share(self.transport(url, model, image, question))

            if indoors is None:
                said["indoors"] = share(whole, INDOORS)
                indoors = said["indoors"] is not None and said["indoors"] >= SEEN
            if (indoors and exit) or entrance:
                door = ENTRANCE if entrance else EXIT
                said["exit"] = share(whole, door.format(what="a screenshot"))
                if said["exit"] is not None and said["exit"] >= SEEN:
                    question = door.format(what="part of a screenshot")
                    said["parts"] = tuple(
                        share(judge.encode(bgr[PART_ROWS, part], PART_WIDTH), question) or 0.0
                        for part in PARTS
                    )
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


_active: Ahead | None = None
_place: Ahead | None = None


def active() -> Ahead | None:
    return _active


def place() -> Ahead | None:
    """The asker a walk keeps for the place it is in, beside the one its guard looks round with:
    each takes one frame at a time, and neither reads the other's answer."""
    return _place


def use(servers) -> Ahead | None:
    """The servers a session asks; none switches the asking off."""
    global _active, _place
    from .indoors import forget

    forget()
    _active = Ahead(servers) if servers else None
    _place = Ahead(servers) if servers else None
    return _active
