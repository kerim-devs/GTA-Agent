"""Going around what stands in the road: boxes become a push on the stick and a lift of the pedal.

The driver follows the route on the minimap and sees nothing of the road itself. This looks at the picture.
A vehicle or a person whose box lies in the car's own track ahead pushes the stick to the freer side and
lifts the pedal, harder the closer the thing is. How big and how far a thing is comes from the height of
its box, which is the same from behind and from the side.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .contract import Detection

WIDTH, HEIGHT = 1280, 720
# The width of a thing in heights of its box: a car is about 1.8 m wide and 1.45 m tall, a lorry or a
# bus twice as tall, and a person about as tall as a car is wide.
WIDE = {"car": 1.25, "truck": 0.7, "bus": 0.6, "motorcycle": 1.2, "bicycle": 1.0, "person": 1.0}
OWN = 0.24  # the own car's width as a share of the picture's (the detector on Kerim's drive of 11 November)
TRACK = 1.1  # widths between two centres under which the tracks touch, a tenth to spare
BESIDE = 2.3  # widths up to which a thing fills the lane next to the own
FAR, NEAR = 5.0, 1.6  # the camera's distance in own distances: no push beyond FAR, the full push at NEAR
PUSH = 0.45  # the stick at the full push; against the route's pull that is about one lane
LIFT = 0.7  # the share of the pedal taken away at the full push
STALE = 0.6  # seconds after which boxes say nothing about the road
HOLD = 1.0  # seconds a chosen side is kept after the last thing in the way
VEHICLES = ("car", "truck", "bus", "motorcycle")
FOLLOW_FROM = 0.35  # nearness from which the pedal is lifted behind a vehicle that is followed, about 15 m
FOLLOW_LIFT = 0.9  # the share of the pedal taken away at full nearness, so that the car keeps its distance
LANE = 0.7  # widths of the own car between the picture's middle and the centre of a thing that is in its lane
SPAN = 1.0  # seconds of a thing's history that say how fast it comes closer
SPAN_MIN = 0.5  # the shortest history that says it; before that nothing is pushed for, only the pedal lifted
GROW = 0.2  # growth of a box's height per second from which the car closes on it: 10 percent in half a second
LOST = 0.7  # seconds a thing is remembered without a box; the detector drops a thing for a few frames
QUEUE = 0.5  # nearness from which a vehicle ahead is the one the car waits behind, about six metres


@dataclass(frozen=True)
class Around:
    steer: float = 0.0  # added to the route's stick
    pedal: float = 1.0  # factor on the accelerator
    urgent: bool = False  # close and straight ahead: brake, if the speed is known to allow it


CLEAR = Around()


def _seen(item) -> tuple[float, float, float]:
    """Offset of the centre from the picture's middle, width and nearness of a box, in picture widths."""
    x0, y0, x1, y1 = item.box
    offset = ((x0 + x1) / 2 - WIDTH / 2) / WIDTH
    wide = WIDE.get(item.kind, 1.0) * (y1 - y0) / WIDTH
    if abs(offset) < OWN / 2:
        # Straight ahead the own car hides the lower part of a box, and the full width tells more.
        wide = max(wide, (x1 - x0) / WIDTH)
    if wide <= 0:
        return offset, 0.0, 0.0
    near = (FAR - OWN / wide) / (FAR - NEAR)
    return offset, wide, min(1.0, max(0.0, near))


def _minimap(box) -> bool:
    return (box[0] + box[2]) / 2 < 0.22 * WIDTH and (box[1] + box[3]) / 2 > 0.75 * HEIGHT


def waits_behind(objects, objects_time: float | None, now: float) -> bool:
    """A vehicle close ahead in the car's own track: a stop behind it is waiting, not being stuck.

    False without fresh boxes, so that a car with no detector is judged as it was before."""
    if not objects or objects_time is None or not 0 <= now - objects_time <= STALE:
        return False
    for item in objects:
        if item.kind not in VEHICLES or _minimap(item.box):
            continue
        offset, wide, near = _seen(item)
        if near >= QUEUE and abs(offset) < TRACK * wide:
            return True
    return False


def _in_lane(item) -> bool:
    """The thing's centre lies within LANE of the own car's width from the picture's middle.

    The width is the car's width at the thing's depth, so a lorry that is close and beside has a box that
    covers half the picture with its centre far off the middle, while one far ahead has a narrow box close
    to it. The box's edge says nothing: the lorry next door overlaps the car's side in the picture."""
    offset, wide, _ = _seen(item)
    return abs(offset) < LANE * min(wide, OWN)


class _Thing:
    """One thing the detector keeps seeing: the heights of its box over the last second."""

    def __init__(self, item, now: float) -> None:
        self.kind, self.box, self.seen = item.kind, item.box, now
        self.heights: list[tuple[float, float]] = []
        self.kinds: list[str] = []
        self.add(item, now)

    def add(self, item, now: float) -> None:
        self.box, self.seen = item.box, now
        self.heights = [(t, h) for t, h in self.heights if now - t <= SPAN] + [
            (now, item.box[3] - item.box[1])
        ]
        self.kinds = [*self.kinds, item.kind][-8:]
        # The detector calls one lorry a truck in one frame and a bus in the next: the name most often given.
        self.kind = max(set(self.kinds), key=self.kinds.count)

    def same(self, item) -> bool:
        """Whether a new box is this thing: the same sort, about the same place, about the same size."""
        if (item.kind == "person") != (self.kind == "person"):
            return False
        x0, y0, x1, y1 = self.box
        height, new = y1 - y0, item.box[3] - item.box[1]
        if height <= 0 or new <= 0 or not 0.6 <= new / height <= 1.7:
            return False
        dx = (item.box[0] + item.box[2] - x0 - x1) / 2
        dy = (item.box[1] + item.box[3] - y0 - y1) / 2
        return math.hypot(dx, dy) <= 0.6 * max(height, x1 - x0, item.box[2] - item.box[0])

    def closing(self) -> bool | None:
        """Whether the box has grown by GROW a second or more; None while the history is too short to say."""
        if len(self.heights) < 3 or self.heights[-1][0] - self.heights[0][0] < SPAN_MIN:
            return None
        # Two boxes at each end, so that one badly cut box does not decide.
        old = sum(h for _, h in self.heights[:2]) / 2
        new = sum(h for _, h in self.heights[-2:]) / 2
        span = (self.heights[-1][0] + self.heights[-2][0] - self.heights[0][0] - self.heights[1][0]) / 2
        return old > 0 and new > 0 and math.log(new / old) / span >= GROW


class Avoider:
    """Keeps the side it chose while something is in the way, so that the push does not flip mid-swerve."""

    def __init__(self) -> None:
        self.side = 0
        self.seen: float | None = None
        self.things: list[_Thing] = []
        self.tracked: float | None = None
        self.matched: dict[int, _Thing] = {}

    def _track(self, objects, objects_time: float) -> dict[int, _Thing]:
        """Match this detection's boxes to the things followed so far, once per detection."""
        boxes = [item for item in objects if not _minimap(item.box)]
        if objects_time == self.tracked:  # the same detection on the next tick
            return self.matched
        matched: dict[int, _Thing] = {}
        self.tracked = objects_time
        free = [t for t in self.things if 0 <= objects_time - t.seen <= LOST]
        for index, item in enumerate(boxes):
            options = [t for t in free if t.same(item)]
            if options:
                thing = min(options, key=lambda t: math.hypot(t.box[0] - item.box[0], t.box[1] - item.box[1]))
                free.remove(thing)
                thing.add(item, objects_time)
            else:
                thing = _Thing(item, objects_time)
                self.things.append(thing)
            matched[index] = thing
        self.things = [t for t in self.things if 0 <= objects_time - t.seen <= LOST]
        self.matched = matched
        return matched

    def step(self, objects, objects_time: float | None, now: float, *, bypass: bool = False) -> Around:
        if self.seen is not None and not 0 <= now - self.seen <= HOLD:
            self.side, self.seen = 0, None
        if not objects or objects_time is None or not 0 <= now - objects_time <= STALE:
            return CLEAR
        # The detector takes the minimap for a car now and then.
        boxes = [item for item in objects if not _minimap(item.box)]
        things = [_seen(item) for item in boxes]
        if bypass:
            ahead = [
                (near, offset, wide)
                for item, (offset, wide, near) in zip(boxes, things, strict=True)
                if 0 < near and _in_lane(item)
            ]
            return self._around(ahead, things, now, bypass=True) if ahead else CLEAR
        followed = self._track(objects, objects_time)
        ahead, following = [], []
        for index, (item, (offset, wide, near)) in enumerate(zip(boxes, things, strict=True)):
            if not 0 < near or not _in_lane(item):
                continue  # beside the car, or too far to matter
            thing = followed[index]
            closing = thing.closing()
            # The name the detector gave the thing most often, not the one of this frame, sizes it.
            offset, wide, near = _seen(Detection(thing.kind, item.box, item.confidence))
            if closing:
                ahead.append((near, offset, wide))
            else:
                following.append((near, offset, wide, closing is None))
        if ahead:
            return self._around(ahead, things, now, bypass=False)
        if not following:
            return CLEAR
        near, offset, wide, _ = max(following)
        lift = FOLLOW_LIFT * min(1.0, max(0.0, (near - FOLLOW_FROM) / (1 - FOLLOW_FROM)))
        # Close and straight ahead is braked for as before, whether the car closes on it or not: a
        # vehicle that slows a little at a time never grows fast enough to be gone round.
        return Around(0.0, 1 - lift, near >= 0.8 and abs(offset) < wide / 2)

    def _around(self, ahead, things, now: float, *, bypass: bool) -> Around:
        near, offset, wide = max(ahead)
        if self.side == 0:
            self.side = self._free(1 if offset < 0 else -1, things)
        self.seen = now
        urgent = near >= 0.8 and abs(offset) < wide / 2
        if self.side == 0:  # both sides taken: stay behind
            return Around(0.0, 1 - min(1.0, 1.3 * LIFT * near), urgent)
        if bypass:
            # A stopped queue has exhausted its wait. Commit to the observed
            # free side instead of balancing a small nudge against route steering.
            return Around(float(self.side), 1.0, urgent)
        return Around(self.side * PUSH * near, 1 - LIFT * near, urgent)

    @staticmethod
    def _free(side: int, things) -> int:
        """`side` unless something close fills the lane there, then the other; zero when both are taken."""
        taken = {
            1 if offset > 0 else -1
            for offset, wide, near in things
            if near > 0.3 and TRACK * wide <= abs(offset) < BESIDE * wide
        }
        return side if side not in taken else -side if -side not in taken else 0


def passing_side(objects, objects_time, now):
    """A fresh close vehicle and the currently free side, including neither (0)."""
    if not waits_behind(objects, objects_time, now):
        return None
    things = [_seen(item) for item in objects if not _minimap(item.box)]
    ahead = [
        (_seen(item)[2], _seen(item)[0])
        for item in objects
        if item.kind in VEHICLES and not _minimap(item.box) and _seen(item)[2] >= QUEUE and _in_lane(item)
    ]
    if not ahead:
        return None
    _, offset = max(ahead)
    return Avoider._free(1 if offset < 0 else -1, things)
