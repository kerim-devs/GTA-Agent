"""A hit as a signal: the health bar getting shorter, told from what the HUD reader returns.

In free roam a brawl or a stray shot shows no marker on the map; the bar getting shorter is the
plainest thing the game draws. `Hits` is fed the HUD reading of every fresh frame and
says when the figure has been hit and by how much. It knows nothing of the guard or the skills.

A hit makes the bar shorter from one frame to the next, and the reader reads the new length on the
first frame, across the orange the game paints over the lost part; so a hit is a step down from
the level the figure had, with the new level there at once. The level is the median of the last
one and a half seconds of readings: a reading that runs long for a moment and comes back is no
fall, and a fall that slides down over several frames is a background moving, not a hit. One odd
frame decides nothing, since the lower level has to be read on three frames that agree, and a
frame without a value is stood out, neither confirming a fall nor breaking one. Nothing counts in
the first second after the HUD comes back from a screen without it: the picture fades in, and the
level before the screen is not the level after it. Measured in docs/reports/P66-a-hit-as-a-signal.md.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from statistics import median

from pilot.contract import Hud

# The smallest fall that counts: four of the track's 90 columns, measured from the level the signal
# holds. Readings of a still bar can be a column apart, and an icon at the bar's end can shorten it
# by three; the two hits of three columns in lab/health/ are each followed within a second by a
# larger one.
DROP = 3.5 / 90
# Readings of the lower level, on distinct frames, that must agree before a fall is a hit: at 30
# frames a second the third arrives 0.07 s after the first.
CONFIRM = 3
AGREE = 0.03
# A fall that has not settled on one level within this long was no hit; the level is read anew.
SETTLE_S = 0.5
# The level a fall is measured from: the median of the readings of this long, at least five.
LEVEL_S = 1.5
LEVEL_READINGS = 5
# Without a reading for this long the level is forgotten, and a lower one later is no hit.
STALE_S = 2.0
# The HUD counts as gone when no bar has been read for this long, and nothing counts for this long
# after it is back.
GONE_S = 0.3
QUIET_S = 1.0


@dataclass(frozen=True)
class Hit:
    time: float  # capture time of the frame that confirmed the hit
    since: float  # capture time of the first frame read at the lower level
    before: float  # health before the hit
    after: float  # health after it

    @property
    def drop(self) -> float:
        return self.before - self.after


class Hits:
    def __init__(self):
        self.readings: deque[tuple[float, float]] = deque()  # (capture time, health) at the level
        self.fall: list[tuple[float, float]] = []  # readings since a step down from the level
        self.below: float | None = None  # first of a run of lower readings that began as no step
        self.previous: tuple[float, float] | None = None  # the last reading with a value
        self.last_time: float | None = None
        self.last_bars: float | None = None  # capture time of the last frame with any bar read
        self.back: float | None = None  # capture time the HUD came back after it was gone

    @property
    def level(self) -> float | None:
        """The health the figure has, as far as the readings agree on it; None while unknown."""
        if len(self.readings) < LEVEL_READINGS:
            return None
        return median(h for _, h in self.readings)

    def reset(self):
        self.readings.clear()
        self.fall.clear()
        self.below = None

    def update(self, time: float, hud: Hud | None) -> Hit | None:
        """Feed the HUD reading of the frame captured at `time`; a Hit on the frame that confirms one."""
        if self.last_time is not None and time <= self.last_time:
            return None  # the same frame again
        self.last_time = time
        # The reader reads no bars on a screen that hides them; the weapon wheel and the phone do not.
        bars = hud is not None and any(v is not None for v in (hud.health, hud.armour, hud.special))
        if not bars:
            if self.last_bars is not None and time - self.last_bars >= GONE_S:
                self.reset()
                self.previous = None
            return None
        if self.last_bars is None or time - self.last_bars >= GONE_S:
            self.reset()
            self.previous = None
            self.back = time
        self.last_bars = time
        health = hud.health
        if health is None or (self.back is not None and time - self.back < QUIET_S):
            return None
        previous, self.previous = self.previous, (time, health)
        if previous is not None and time - previous[0] >= STALE_S:
            self.reset()
        level = self.level
        if level is None or health > level - DROP:
            # At the level or above it, or a dip that did not last: the dip decided nothing.
            self.fall.clear()
            self.below = None
            self.readings.append((time, health))
            while time - self.readings[0][0] > LEVEL_S:
                self.readings.popleft()
            return None
        if not self.fall:
            # A step: the last reading with a value was at the level. Frames between without one
            # (an icon over the bar's end) are stood out.
            step = previous is not None and previous[1] > level - DROP and self.below is None
            if not step:
                # Lower, but not as a step from the level. When it stays there the figure's level
                # has changed without a hit that could be seen; read it anew.
                self.below = time if self.below is None else self.below
                if time - self.below >= LEVEL_S:
                    self.reset()
                return None
        self.fall.append((time, health))
        if time - self.fall[0][0] > SETTLE_S:
            self.reset()
            return None
        recent = [h for _, h in self.fall[-CONFIRM:]]
        if len(recent) < CONFIRM or max(recent) - min(recent) > AGREE:
            return None
        after = median(recent)
        if all(abs(h - after) > AGREE for _, h in self.fall[:2]):
            return None  # it slid down to this level: not a step
        hit = Hit(time=time, since=self.fall[0][0], before=level, after=after)
        self.readings = deque(self.fall[-CONFIRM:])
        self.fall = []
        return hit
