"""Road-only vehicle guidance. No GPS route or metric speed is inferred."""

import math
from collections import deque
from dataclasses import dataclass
from typing import ClassVar

import cv2
import numpy as np

from .contract import HUD_RECT, Pad, Reading
from .minimap import ARROW_XY, MX0, MX1, MY0, MY1, H, W, _blocks, read
from .skills import Observation, SkillResult

WISHES = ("any", "straight", "left", "right")
_OPEN = cv2.getStructuringElement(cv2.MORPH_RECT, (35, 35))
_CLOSE = np.ones((3, 3), np.uint8)
_NEIGHBOURS = ((-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1))
_KERNEL = np.array([[128, 1, 2], [64, 0, 4], [32, 16, 8]], np.float32)


def _thinning_tables():
    tables = []
    for second in (False, True):
        table = np.zeros(256, np.uint8)
        for code in range(256):
            p = [(code >> i) & 1 for i in range(8)]
            transitions = sum(not p[i] and p[(i + 1) % 8] for i in range(8))
            triplets = (
                (p[0] * p[2] * p[6], p[0] * p[4] * p[6])
                if second
                else (p[0] * p[2] * p[4], p[2] * p[4] * p[6])
            )
            table[code] = 2 <= sum(p) <= 6 and transitions == 1 and not any(triplets)
        tables.append(table)
    return tables


_THIN = _thinning_tables()


@dataclass(frozen=True)
class Road:
    path: tuple[tuple[float, float], ...]
    width: float
    arrow: float
    dead_end: bool = False


def _skeleton(mask):
    pixels = (mask > 0).astype(np.uint8)
    for _ in range(24):
        removed = 0
        for table in _THIN:
            code = cv2.filter2D(pixels, cv2.CV_8U, _KERNEL, borderType=cv2.BORDER_CONSTANT)
            erase = cv2.bitwise_and(pixels, cv2.LUT(code, table))
            removed += cv2.countNonZero(erase)
            pixels -= erase
        if not removed:
            break
    return pixels


def _trace_road(mask: np.ndarray, arrow: float, wish: str) -> Road | None:
    distance = cv2.distanceTransform(mask, cv2.DIST_L2, 3)
    skeleton = _skeleton(mask)
    yy, xx = np.nonzero(skeleton)
    x, y = xx + MX0 - ARROW_XY[0], ARROW_XY[1] - (yy + MY0)
    angle = math.radians(arrow)
    forward = x * math.sin(angle) + y * math.cos(angle)
    sideways = x * math.cos(angle) - y * math.sin(angle)
    radius = np.hypot(x, y)
    candidates = np.flatnonzero((radius >= 6) & (radius <= 18) & (forward >= 4) & (abs(sideways) <= 11))
    if not len(candidates):
        return None
    i = candidates[np.argmin(radius[candidates] + abs(sideways[candidates]) * 0.7)]
    start = int(yy[i]), int(xx[i])
    if distance[start] > 10:
        return None
    # The arrow hides the pavement. Never connect across that hidden area to another road.
    skeleton[yy[(radius < 6) | (forward < 2)], xx[(radius < 6) | (forward < 2)]] = 0
    queue = deque([start])
    parent = {start: None}
    depth = {start: 0}
    ends = []
    while queue:
        node = queue.popleft()
        row, col = node
        children = []
        if depth[node] < 65:
            for dy, dx in _NEIGHBOURS:
                nxt = row + dy, col + dx
                if 0 <= nxt[0] < mask.shape[0] and 0 <= nxt[1] < mask.shape[1]:
                    if skeleton[nxt] and nxt not in parent:
                        parent[nxt] = node
                        depth[nxt] = depth[node] + 1
                        children.append(nxt)
            queue.extend(children)
        if not children and depth[node] >= 3:
            ends.append(node)
    if not ends:
        return None
    long_ends = [node for node in ends if depth[node] >= 16]
    ends = long_ends or ends
    target = {"any": 0, "straight": 0, "left": -70, "right": 70}[wish]

    def score(node):
        dx, dy = node[1] + MX0 - ARROW_XY[0], ARROW_XY[1] - (node[0] + MY0)
        bearing = (math.degrees(math.atan2(dx, dy)) - arrow + 180) % 360 - 180
        return abs(bearing - target) - min(depth[node], 50) * 0.25

    node = min(ends, key=score)
    dead_end = depth[node] < 16
    nodes = []
    while node is not None:
        nodes.append(node)
        node = parent[node]
    nodes.reverse()
    path = tuple((float(c + MX0 - ARROW_XY[0]), float(ARROW_XY[1] - r - MY0)) for r, c in nodes[::3])
    width = float(np.median([2 * distance[p] for p in nodes[:15]]))
    return Road(path, width, arrow, dead_end)


def read_road(crop: np.ndarray, wish: str = "any", *, reading: Reading | None = None) -> Road | None:
    """Read a 260x170 RGB HUD crop; missing, damaged and off-road pictures abstain."""
    if wish not in WISHES:
        raise ValueError("unknown turn wish")
    if not isinstance(crop, np.ndarray) or crop.shape != (H, W, 3) or crop.dtype != np.uint8:
        return None
    if _blocks(crop)[0] >= 2:
        return None
    if reading is None:
        reading = read(crop)
    if not isinstance(reading, Reading):
        return None
    if reading.corrupt or reading.minimap != "tilted" or reading.arrow is None:
        return None
    if isinstance(reading.arrow, bool) or not isinstance(reading.arrow, (int, float)):
        return None
    if not math.isfinite(reading.arrow):
        return None
    roi = crop[MY0:MY1, MX0:MX1]
    red, green, blue = cv2.split(roi)
    low = cv2.min(cv2.min(red, green), blue)
    spread = cv2.subtract(cv2.max(cv2.max(red, green), blue), low)
    contrast = cv2.morphologyEx(low, cv2.MORPH_TOPHAT, _OPEN)
    mask = ((low >= 135) & (spread <= 80) & (contrast >= 22)).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, _CLOSE)
    return _trace_road(mask, reading.arrow, wish)


class DriveFree:
    name = "drive_free"
    parameters: ClassVar[dict] = {
        "seconds": (1.0, 120.0, 20.0),
        "turn": WISHES,
        "pace": ("normal", "slow", "fast"),
    }
    prompt = (
        "Follow visible roads without GPS while in a vehicle. Choose seconds, turn and pace. "
        "Needs a fresh vehicle HUD and motion observations. Stops when time expires; fails on lost roads, "
        "missing motion or repeated blockage. Pace is conservative throttle, not a measured speed."
    )

    def __init__(self, args: dict):
        if not isinstance(args, dict) or set(args) - self.parameters.keys():
            raise ValueError("drive_free expects seconds, turn and pace")
        seconds = args.get("seconds", 20.0)
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
            raise ValueError("seconds must be finite")
        if isinstance(seconds, float) and not math.isfinite(seconds):
            raise ValueError("seconds must be finite")
        self.seconds = max(1.0, min(120.0, seconds))
        self.turn, self.pace = args.get("turn", "any"), args.get("pace", "normal")
        if self.turn not in WISHES or self.pace not in ("normal", "slow", "fast"):
            raise ValueError("unknown turn or pace")
        self._started = self._last = self._lost = self._still = self._unknown = None
        self._reverse_until = None
        self._reverse_steer = 0.0
        self._escape_until = -math.inf
        self._attempts = 0
        self._terminal = None
        self._steer = 0.0
        self._pushing = False

    def _reverse(self, now, dead_end=False):
        if self._attempts >= 3:
            return self.stop("blocked after three reverse attempts; choose another action")
        self._attempts += 1
        self._reverse_until = now + (3.0 if dead_end else 1.5)
        self._reverse_steer = 0.0 if dead_end else -self._steer
        self._escape_until = now + 9.0
        self._still = None
        return SkillResult(Pad(left=(self._reverse_steer, 0.0), l2=0.6))

    def stop(self, reason) -> SkillResult:
        if self._terminal is None:
            self._terminal = SkillResult(status="failed", reason=str(reason))
        return self._terminal

    def step(self, observation: Observation) -> SkillResult:
        if self._terminal is not None:
            return self._terminal
        if not isinstance(observation, Observation):
            return self.stop("invalid observation; reacquire fresh observations")
        now = observation.time
        if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now):
            return self.stop("invalid observation time")
        if self._started is None:
            self._started = now
        if self._last is not None and now <= self._last:
            return self.stop("stale observation time")
        if now - self._started >= self.seconds:
            self._terminal = SkillResult(status="done", reason="time limit reached")
            return self._terminal
        gap = self._last is not None and now - self._last > 0.5
        elapsed = 0.0 if self._last is None or gap else now - self._last
        self._last = now
        frame = observation.frame
        road = None
        if (
            not gap
            and isinstance(observation.reading, Reading)
            and isinstance(frame, np.ndarray)
            and frame.shape == (720, 1280, 3)
        ):
            x, y, w, h = HUD_RECT
            wish = "left" if now < self._escape_until and self.turn in ("any", "straight") else self.turn
            road = read_road(frame[y : y + h, x : x + w], wish, reading=observation.reading)
        if road is None:
            self._pushing = False
            if gap:
                self._still = None
                self._reverse_until = None
            if self._lost is None:
                self._lost = now
            if now - self._lost >= 2.5:
                return self.stop("road unreadable for 2.5 seconds; reacquire a vehicle road")
            return SkillResult()
        self._lost = None
        if not isinstance(observation.moving, bool):
            self._pushing = False
            if self._unknown is None:
                self._unknown = now
            if now - self._unknown >= 2.5:
                return self.stop("motion unavailable; reacquire fresh observations")
            return SkillResult()
        self._unknown = None
        if self._reverse_until is not None:
            if now < self._reverse_until:
                return SkillResult(Pad(left=(self._reverse_steer, 0.0), l2=0.6))
            self._reverse_until = None
            self._still = None
            self._pushing = False
        if road.dead_end:
            self._pushing = False
            if observation.moving:
                return SkillResult()
            return self._reverse(now, dead_end=True)
        if observation.moving is False and self._pushing:
            self._still = (self._still or 0.0) + elapsed
            if self._still >= 2.0:
                return self._reverse(now)
        elif observation.moving:
            self._still = None
        target = min(road.path, key=lambda p: abs(math.hypot(*p) - 20))
        error = (math.atan2(*target) - math.radians(road.arrow) + math.pi) % (2 * math.pi) - math.pi
        self._steer = max(-1.0, min(1.0, error * 1.7))
        bend = abs(error)
        cap = {"slow": 0.28, "normal": 0.43, "fast": 0.60}[self.pace]
        # Narrow roads can mean either zoom-out or a narrow lane. Both warrant less throttle.
        width_factor = max(0.5, min(1.0, road.width / 7.0))
        throttle = cap * width_factor / (1 + 2.8 * bend)
        self._pushing = throttle > 0.05
        return SkillResult(Pad(left=(self._steer, 0.0), r2=throttle))
