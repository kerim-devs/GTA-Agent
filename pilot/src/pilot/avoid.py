"""Going around what stands in the road: boxes become a push on the stick and a lift of the pedal.

The driver follows the route on the minimap and sees nothing of the road itself. This looks at the picture.
A vehicle or a person whose box lies in the car's own track ahead pushes the stick to the freer side and
lifts the pedal, harder the closer the thing is. How big and how far a thing is comes from the height of
its box, which is the same from behind and from the side.
"""

from __future__ import annotations

from dataclasses import dataclass

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


class Avoider:
    """Keeps the side it chose while something is in the way, so that the push does not flip mid-swerve."""

    def __init__(self) -> None:
        self.side = 0
        self.seen: float | None = None

    def step(self, objects, objects_time: float | None, now: float, *, bypass: bool = False) -> Around:
        if self.seen is not None and not 0 <= now - self.seen <= HOLD:
            self.side, self.seen = 0, None
        if not objects or objects_time is None or not 0 <= now - objects_time <= STALE:
            return CLEAR
        # The detector takes the minimap for a car now and then.
        things = [_seen(item) for item in objects if not _minimap(item.box)]
        ahead = [
            (near, offset, wide) for offset, wide, near in things if 0 < near and abs(offset) < TRACK * wide
        ]
        if not ahead:
            return CLEAR
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
    ahead = [(near, offset) for offset, wide, near in things if near >= QUEUE and abs(offset) < TRACK * wide]
    if not ahead:
        return None
    _, offset = max(ahead)
    return Avoider._free(1 if offset < 0 else -1, things)
