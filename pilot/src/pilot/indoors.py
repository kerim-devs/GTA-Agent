"""A small radar reading and session memory, with no service or hardware access."""

from dataclasses import dataclass

import numpy as np

# Frozen before the separate recordings in lab/indoors are evaluated.
COLOR_LIMIT = 0.30
# Only a held-out result of at least 90% in both classes permits independent decisions.
INDEPENDENT = False


def read(frame):
    """Return indoors, outdoors, or unknown from the radar's coloured area.

    A room's enlarged, mostly grey outline replaces the coloured outdoor map. The caller
    must also require a readable flat map; a missing map is never evidence of a room.
    """
    if not isinstance(frame, np.ndarray) or frame.shape != (720, 1280, 3):
        return None
    if frame.dtype != np.uint8:
        return None
    radar = frame[550:663, 69:239].astype(np.int16)
    high, low = radar.max(axis=2), radar.min(axis=2)
    if float(high.std()) < 5 or np.mean(high < 10) > 0.8:
        return None
    return bool(np.mean(high - low > 25) < COLOR_LIMIT)


def resolve(local, model):
    """The recorded model wins disagreements; unqualified picture readings only confirm."""
    if model is not None:
        return model
    return local if INDEPENDENT else None


@dataclass(frozen=True)
class Entrance:
    heading: float | None
    side: tuple[float, float] | None
    name: str | None = None
    absolute: bool = False


_entrances: dict[str | None, Entrance] = {}
_latest: Entrance | None = None


def remember(heading, side, name=None, *, absolute=False):
    global _latest
    _latest = Entrance(heading, side, name, absolute)
    _entrances[name] = _latest


def entrance(name=None):
    return _latest if name is None else _entrances.get(name)


def forget():
    global _latest
    _entrances.clear()
    _latest = None


class Confirm:
    """Require separate, consecutive readable samples, never one answer twice."""

    def __init__(self):
        self.value = self.since = self.last = None

    def reset(self):
        self.value = self.since = self.last = None

    def see(self, value, now):
        if value is None or (self.last is not None and now <= self.last):
            self.reset()
            return None
        if value != self.value or self.last is None or now - self.last > 2.0:
            self.value, self.since = value, now
        self.last = now
        return value if now - self.since >= 1 / 3 else None


class Place:
    """Consume each model answer once, falling back only to a qualified picture reading."""

    def __init__(self, model=None):
        self.model = model
        self.asked = None
        self.at = -float("inf")
        self.confirm = Confirm()

    def sample(self, observation):
        now = observation.time
        local = read(observation.frame)
        value = None
        sampled = False
        if self.asked is not None:
            view = self.model.answer(self.asked)
            age = now - self.asked
            if view is not None or age >= 2:
                model = None
                if view is not None and age < 2 and view.error is None:
                    share = view.indoors
                    if share is not None and (share >= 0.9 or share < 0.5):
                        model = share >= 0.9
                value = resolve(local, model)
                self.asked, self.at, sampled = None, now, True
        elif self.model is None and now - self.at >= 1 / 3:
            value = resolve(local, None)
            self.at, sampled = now, True
        if self.model is not None and self.asked is None and now - self.at >= 1 / 3:
            if self.model.ask(observation.frame, now, ahead=False, exit=False):
                self.asked = now
            else:
                value = resolve(local, None)
                self.at, sampled = now, True
        return self.confirm.see(value, now) if sampled else None

    def reset(self):
        self.confirm.reset()
        self.asked = None
