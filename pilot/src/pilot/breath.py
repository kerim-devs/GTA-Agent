"""Whether the figure has the breath to sprint, read from the colour of the health track.

The game draws no bar for stamina. On the console on 12 November, 23:54, the figure had sprinted
for 49.6 s on Kerim's taps when its whole health track went from green to red between two frames,
in open desert with nothing near it. Eleven seconds later the map began to pulse red and the
health fell, from 0.99 to about 0.76 in the eighteen seconds until the picture was lost. So a
track that turns red under a sprint is the game saying the figure has run itself out, and running
on costs health. A player lets go of the button then; so does this.
"""

from __future__ import annotations

import numpy as np

# The same rows and columns the HUD reader takes the bars from: the health track is the first
# ninety columns of the band under the minimap.
_BAND = (slice(676, 680), slice(64, 154))
_ABOVE, _BELOW = 672, 682


def track(frame) -> str | None:
    """The colour of the health track in a frame: "green", "red", or None where it shows neither."""
    try:
        if not isinstance(frame, np.ndarray) or frame.shape != (720, 1280, 3) or frame.dtype != np.uint8:
            return None
        r, g, b = frame[_BAND].astype(np.float32).mean(axis=0).T
        sr, sg, sb = frame[[_ABOVE, _BELOW], _BAND[1]].astype(np.float32).mean(axis=0).T
        green = (g - np.maximum(r, b) > 16) & (g - np.maximum(r, b) - (sg - np.maximum(sr, sb)) > 10)
        red = (r - np.maximum(g, b) > 35) & (r - np.maximum(g, b) - (sr - np.maximum(sg, sb)) > 20)
        if red.mean() > 0.6:
            return "red"
        if green.mean() > 0.6:
            return "green"
        return None
    except Exception:
        return None


class Breath:
    """Says on every tick whether a walking skill may tap the sprint button."""

    # A hit colours the track too, for less than this long. Only a track that was green in this
    # walk and has now been red for this long is taken for a figure out of breath.
    RED_FOR = 0.7
    # The sprint is taken up again when the track has been green for this long.
    GREEN_FOR = 6.0
    # A track still red after this long of not sprinting is red for another reason, such as low
    # health; the sprint goes on and is not given up again until the track has been green.
    REST_MAX = 30.0

    def __init__(self):
        self.seen_green = False
        self.red_since = None
        self.green_since = None
        self.rest_since = None
        self.rests: list[tuple[float, float | None]] = []  # (begun, ended), for logs

    def gap(self) -> None:
        """What the track showed before a gap in the ticks is no measure of how long it has shown it."""
        self.red_since = self.green_since = None

    def sprint(self, frame, now: float) -> bool:
        colour = track(frame)
        if colour == "green":
            self.seen_green, self.red_since = True, None
            if self.green_since is None:
                self.green_since = now
        elif colour == "red":
            self.green_since = None
            if self.red_since is None:
                self.red_since = now
        if self.rest_since is None:
            if self.seen_green and self.red_since is not None and now - self.red_since >= self.RED_FOR:
                self.rest_since = now
                self.rests.append((now, None))
        else:
            rested = self.green_since is not None and now - self.green_since >= self.GREEN_FOR
            if rested or now - self.rest_since >= self.REST_MAX:
                self.seen_green = rested
                self.rests[-1] = (self.rest_since, now)
                self.rest_since = None
        return self.rest_since is None
