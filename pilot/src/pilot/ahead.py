"""Whether the way straight ahead is open, asked of the local model about one frame at a time.

Kerim, 13 November, of a figure that is stuck: that is where the model is needed again, to look and
say where the way goes on. Asked for a side in the whole picture it had said "right" to every frame
(see `sides`). Asked the one plain question below about 182 frames of the walks of that night, it
called 22 of the 28 on which the guard had found the figure held up blocked, and 149 of the 154 on
which the figure ran free open; four of the five it called blocked there show the fence, the wall or
the wreck the figure was running at. An answer took 0.14 to 0.17 s. What it misses is what it can
see through or past: a chain-link fence, the posts of a porch, the gap between two boulders, a shop
front by night. So its yes is a direction worth trying, which the feet still judge, and its no is a
direction not tried first.
"""

from __future__ import annotations

import threading
import time

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
WIDTH = 640


class Ahead:
    """Asks in the background and never holds a tick up; one question at a time."""

    TIMEOUT = 2.0

    def __init__(self, servers, *, transport=None, clock=time.monotonic):
        self.servers = [judge.endpoint(server) for server in servers]
        self.transport = transport if transport is not None else self._request
        self.clock = clock
        self.lock = threading.Lock()
        self.busy = False
        self.result = None  # (capture, how open)
        self.log: list[dict] = []

    def _request(self, url, model, image):
        return judge.post(url, model, image, QUESTION, 3, timeout=self.TIMEOUT)[0]

    def ask(self, frame, capture: float) -> bool:
        """Begin asking about this frame; False when a question is still out or the frame is none."""
        if not isinstance(frame, np.ndarray) or frame.shape != (720, 1280, 3) or not self.servers:
            return False
        with self.lock:
            if self.busy:
                return False
            self.busy = True
        threading.Thread(target=self._work, args=(frame.copy(), capture), daemon=True).start()
        return True

    def _work(self, frame, capture):
        started = self.clock()
        share, error = None, None
        try:
            url, model = self.servers[0]
            image = judge.encode(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR), WIDTH)
            share = open_share(self.transport(url, model, image))
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        with self.lock:
            self.busy = False
            self.result = (capture, share, error)
            self.log.append(
                {"capture": capture, "duration": self.clock() - started, "open": share, "error": error}
            )

    def answer(self, since: float) -> tuple[float | None, str | None] | None:
        """(how open, error) for the frame asked about at `since` or later; None while it is out."""
        with self.lock:
            if self.result is None or self.result[0] < since:
                return None
            return self.result[1], self.result[2]


_active: Ahead | None = None


def active() -> Ahead | None:
    return _active


def use(servers) -> Ahead | None:
    """The servers a session asks; none switches the asking off."""
    global _active
    _active = Ahead(servers) if servers else None
    return _active
