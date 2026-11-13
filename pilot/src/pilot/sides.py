"""Which side round an obstacle is open, asked of the local model one strip at a time.

Asked for a side in the whole picture, the model said "right" to every one of twelve frames of
13 November, mirrored or not. Shown the strip left of the figure and the strip right of it, and
asked of each alone whether a person could walk across the ground in it, it called the open desert
open and the boulders closed on the six frames of a figure held up by a rock, and both sides open
on the two of a figure running free; an answer took 0.13 to 0.24 s. So the model is not asked to
choose a side: it is asked the same plain question twice, and the choosing is done here.
"""

from __future__ import annotations

import math
import threading
import time

import cv2
import numpy as np

from . import judge

QUESTION = (
    "This is one side of a game screenshot. Could a person walk forward across the ground shown here, "
    "away from the camera?\n"
    "A: yes, there is open ground to walk on\n"
    "B: no, rocks, a wall, a fence, a vehicle or another obstacle fills it"
)
# The strips left and right of the figure, without the sky and without the corner the HUD stands in.
LEFT = (slice(200, 620), slice(140, 560))
RIGHT = (slice(200, 620), slice(720, 1140))
WIDTH = 448
CLEARLY = 0.3  # one side has to be this much more open than the other to be chosen


def open_share(choice: dict) -> float | None:
    """How sure the model was that the strip is open, from 0 to 1, or None for a reply without it."""
    found = judge.letters(choice)
    if not found:
        return None
    letter, top = found[0]
    weights = {key: math.exp(value) for key, value in top.items() if key in "AB" and math.isfinite(value)}
    if weights and sum(weights.values()) > 0:
        return weights.get("A", 0.0) / sum(weights.values())
    return {"A": 1.0, "B": 0.0}.get(letter)


def choose(left: float | None, right: float | None) -> int | None:
    """-1 for the left side, 1 for the right, None where neither is clearly the more open."""
    if left is None or right is None or abs(left - right) < CLEARLY:
        return None
    return -1 if left > right else 1


class Sides:
    """Asks in the background and never holds a tick up; one question at a time."""

    TIMEOUT = 2.0

    def __init__(self, servers, *, transport=None, clock=time.monotonic):
        self.servers = [judge.endpoint(server) for server in servers]
        self.transport = transport if transport is not None else self._request
        self.clock = clock
        self.lock = threading.Lock()
        self.busy = False
        self.result = None  # (capture, left, right)
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
        strips = [frame[LEFT].copy(), frame[RIGHT].copy()]
        threading.Thread(target=self._work, args=(strips, capture), daemon=True).start()
        return True

    def _work(self, strips, capture):
        started = self.clock()
        shares, error = [], None
        try:
            url, model = self.servers[0]
            for strip in strips:
                image = judge.encode(cv2.cvtColor(strip, cv2.COLOR_RGB2BGR), WIDTH)
                shares.append(open_share(self.transport(url, model, image)))
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        with self.lock:
            self.busy = False
            entry = {"capture": capture, "duration": self.clock() - started, "error": error}
            if error is None and len(shares) == 2:
                self.result = (capture, shares[0], shares[1])
                entry.update(left=shares[0], right=shares[1], side=choose(*shares))
            self.log.append(entry)

    def answer(self, since: float) -> tuple[float | None, float | None] | None:
        """(left open, right open) for a frame taken at `since` or later, or None while there is none."""
        with self.lock:
            if self.result is None or self.result[0] < since:
                return None
            return self.result[1], self.result[2]


_active: Sides | None = None


def active() -> Sides | None:
    return _active


def use(servers) -> Sides | None:
    """The servers a session asks; none switches the asking off."""
    global _active
    _active = Sides(servers) if servers else None
    return _active
