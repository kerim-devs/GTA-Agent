"""On foot: noticing that the figure gets nowhere, getting free, and finding a road.

The minimap on foot turns with the camera around the player arrow and slides under it as the figure
walks. A camera turn therefore moves the map content as much as a step does, and the plain size of
the map's motion (`motion.map_motion`) cannot tell a figure walking straight from one pressed against
a wall while the camera swings. `map_shift` fits a turn about the arrow and a shift together and
returns the shift alone: the ground passing under the figure.

Measured on the recorded sessions (lab/foot, docs/reports/P44): over half a second the ground moves
0.7 to 1.0 crop pixels under a walking figure and 2 to 3.5 under a sprinting one, and less than 0.15
under a figure pressed against the railing of the pier.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import ClassVar

import cv2
import numpy as np

from .contract import HUD_RECT, Observation, Pad, SkillResult, player_mode
from .minimap import ACX, ACY, _bars, _blocks
from .profile import active

cv2.setNumThreads(1)

# The map rectangle inset by its border, as in motion.py.
_X0, _X1, _Y0, _Y1 = 39, 209, 32, 138
_Y, _X = np.mgrid[_Y0:_Y1, _X0:_X1]
_MASK = np.full((_Y1 - _Y0, _X1 - _X0), 255, np.uint8)
# The arrow stays put whatever the figure does, and the icons on the rim slide along the rim.
_MASK[(_X - ACX) ** 2 + (_Y - ACY) ** 2 < 12**2] = 0
_MASK[:, :12] = _MASK[:, -12:] = 0
_MASK[:12, :] = 0


def hud_crop(frame) -> np.ndarray | None:
    """The minimap corner of a frame, as `conductor.minimap_crop` cuts it."""
    if not isinstance(frame, np.ndarray) or frame.ndim != 3 or frame.shape[2] != 3:
        return None
    x, y, w, h = HUD_RECT
    if frame.shape[:2] == (720, 1280):
        return frame[y : y + h, x : x + w]
    sx, sy = frame.shape[1] / 1280, frame.shape[0] / 720
    crop = frame[round(y * sy) : round((y + h) * sy), round(x * sx) : round((x + w) * sx)]
    return cv2.resize(crop, (w, h)) if crop.size else None


def crop_ok(crop) -> bool:
    return (
        isinstance(crop, np.ndarray)
        and crop.shape == (170, 260, 3)
        and crop.dtype == np.uint8
        and _bars(crop) >= 2
        and _blocks(crop)[0] < 2
    )


def map_shift(prev: np.ndarray, cur: np.ndarray) -> float | None:
    """How far the ground moved under the arrow between two HUD crops, in crop pixels, with the
    camera's turn about the arrow taken out. None when it cannot be told: no minimap, a damaged
    picture, or too little on the map to follow (open water is one even white). Never raises."""
    try:
        if not (crop_ok(prev) and crop_ok(cur)):
            return None
        a = cv2.cvtColor(prev[_Y0:_Y1, _X0:_X1], cv2.COLOR_RGB2GRAY)
        b = cv2.cvtColor(cur[_Y0:_Y1, _X0:_X1], cv2.COLOR_RGB2GRAY)
        points = cv2.goodFeaturesToTrack(a, maxCorners=60, qualityLevel=0.02, minDistance=5, mask=_MASK)
        if points is None or len(points) < 6:
            return None
        forward, status, error = cv2.calcOpticalFlowPyrLK(a, b, points, None, winSize=(15, 15), maxLevel=3)
        if forward is None:
            return None
        back, back_status, _ = cv2.calcOpticalFlowPyrLK(b, a, forward, None, winSize=(15, 15), maxLevel=3)
        if back is None:
            return None
        valid = (status.ravel() > 0) & (back_status.ravel() > 0) & (error.ravel() < 20)
        valid &= np.linalg.norm(points - back, axis=2).ravel() < 0.8
        if valid.sum() < 6:
            return None
        centre = np.array([ACX - _X0, ACY - _Y0], np.float32)
        src = points.reshape(-1, 2)[valid] - centre
        dst = forward.reshape(-1, 2)[valid] - centre
        # A turn about the arrow and a shift; with the arrow at the origin the shift is how far the
        # ground under the arrow went.
        model, inliers = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=1.5)
        if model is None or inliers is None or int(inliers.sum()) < 6:
            return None
        shift = float(math.hypot(model[0, 2], model[1, 2]))
        return shift if math.isfinite(shift) else None
    except Exception:  # degenerate image data must not reach the hands
        return None


# ------------------------------------------------------------------ roads on the minimap
# A road on the minimap is a white band about ten crop pixels wide. Open water around the pier is
# white too, but as a sheet: an opening wider than any road keeps the sheet and drops the bands.

# The north disc stays upright while moving around the radar with the camera.
# Its recorded 11-pixel core excludes the variable translucent surroundings.
_NORTH = np.array(
    [
        [107, 31, 7, 12, 4, 0, 8, 10, 6, 97, 118],
        [41, 8, 14, 8, 8, 7, 7, 8, 8, 19, 113],
        [3, 5, 52, 169, 20, 16, 27, 99, 6, 5, 44],
        [7, 5, 78, 247, 84, 0, 24, 132, 5, 5, 14],
        [14, 4, 71, 120, 154, 18, 19, 119, 7, 6, 12],
        [10, 4, 69, 83, 25, 157, 63, 110, 6, 5, 5],
        [10, 4, 72, 104, 5, 84, 240, 113, 4, 6, 13],
        [15, 1, 67, 86, 2, 3, 207, 118, 0, 7, 53],
        [33, 1, 26, 13, 1, 1, 26, 20, 5, 11, 119],
        [120, 27, 3, 6, 1, 1, 3, 0, 17, 88, 146],
        [150, 112, 36, 6, 0, 2, 15, 35, 121, 153, 148],
    ],
    dtype=np.uint8,
)


def north_bearing(crop) -> float | None:
    """Picture bearing of the radar's N disc, never the player arrow."""
    if not crop_ok(crop):
        return None
    gray = cv2.cvtColor(crop[15:155, 25:235], cv2.COLOR_RGB2GRAY)
    scores = cv2.matchTemplate(gray, _NORTH, cv2.TM_CCOEFF_NORMED)
    _, score, _, point = cv2.minMaxLoc(scores)
    x, y = point[0] + 30, point[1] + 20
    if score < 0.72 or math.hypot(x - ACX, y - ACY) < 20:
        return None
    return math.degrees(math.atan2(x - ACX, ACY - y))


def world_view(frame) -> np.ndarray | None:
    """Small world-only view for guard evidence, excluding HUD and the figure."""
    if not isinstance(frame, np.ndarray) or frame.ndim != 3 or frame.shape[2] != 3:
        return None
    return cv2.cvtColor(cv2.resize(frame, (320, 180)), cv2.COLOR_RGB2GRAY)


_WORLD_MASK = np.zeros((180, 320), np.uint8)
_WORLD_MASK[45:165, 15:305] = 255
_WORLD_MASK[55:, 115:205] = 0
_WORLD_MASK[125:, :75] = 0


def world_shift(prev: np.ndarray, cur: np.ndarray) -> float | None:
    """Median tracked background displacement over half a second, in 320px pixels.

    Forward/backward checks reject occlusion; separated background patches keep
    the player's idle animation and a single moving object out of the vote.
    This is translation evidence during a walking command, not odometry.
    """
    points = cv2.goodFeaturesToTrack(prev, 60, 0.03, 8, mask=_WORLD_MASK)
    if points is None or len(points) < 12:
        return None
    moved, status, error = cv2.calcOpticalFlowPyrLK(prev, cur, points, None, winSize=(15, 15), maxLevel=2)
    if moved is None:
        return None
    back, back_status, _ = cv2.calcOpticalFlowPyrLK(cur, prev, moved, None, winSize=(15, 15), maxLevel=2)
    if back is None:
        return None
    valid = (status.ravel() > 0) & (back_status.ravel() > 0) & (error.ravel() < 20)
    valid &= np.linalg.norm(points - back, axis=2).ravel() < 0.8
    src = points.reshape(-1, 2)[valid]
    dst = moved.reshape(-1, 2)[valid]
    if len(src) < 12 or len({(int(x // 80), int(y // 60)) for x, y in src}) < 3:
        return None
    distance = float(np.median(np.linalg.norm(dst - src, axis=1)))
    # A fast camera swing cannot establish walking progress.
    return distance if distance < 12 else None


_ROAD_OPEN = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (19, 19))
_ARROW_R = 8  # the white arrow itself
_ON_ROAD_R = 11  # a road pixel this close to the arrow puts the figure on the road
_ROAD_MIN_PIXELS = 80  # a piece of band smaller than this is an icon or a letter, not a road
_SHEET_R = 12  # a white sheet this close to the arrow leaves the side unknown


@dataclass(frozen=True)
class Road:
    bearing: float  # map degrees from the arrow to the nearest road pixel, 0 = up = camera forward
    distance: float  # crop pixels to it
    along: float | None  # one direction of the road at that point, map degrees; None if not readable
    clearance: float | None = None  # outside the white band; negative inside it, in crop pixels
    outward: float | None = None  # toward the nearer edge, never toward the road centre
    width: float | None = None

    @property
    def position(self) -> str:
        if self.clearance is None:
            return "unknown"
        return "side" if self.clearance >= 2.0 else "lane"


def _road_edges(band, along):
    """Fit both edges outside the arrow's occlusion. Junctions/curves/wide sheets abstain.

    This measures a map band, not a pavement detector. Four cross sections must
    agree on a 4..18px strip. A transparent radar can still fool it; no confidence
    in real-world kerbs is inferred from the colour alone.
    """
    if along is None:
        return None, None, None
    angle = math.radians(along)
    tx, ty = math.sin(angle), -math.cos(angle)
    nx, ny = -ty, tx
    dx, dy = _X - ACX, _Y - ACY
    longitudinal, lateral = dx * tx + dy * ty, dx * nx + dy * ny
    edges = []
    for distance in (-18, -12, 12, 18):
        values = np.unique(np.rint(lateral[band.astype(bool) & (abs(longitudinal - distance) < 2)]))
        values = values[abs(values) <= 35]
        groups = np.split(values, np.where(np.diff(values) > 1)[0] + 1)
        groups = [g for g in groups if len(g) >= 4]
        if not groups:
            return None, None, None
        group = min(groups, key=lambda g: min(abs(g)))
        low, high = float(group[0]) - 0.5, float(group[-1]) + 0.5
        if not 4 <= high - low <= 18:
            return None, None, None
        edges.append((low, high))
    edges = np.array(edges)
    if np.ptp(edges, axis=0).max() > 3:
        return None, None, None
    low, high = np.mean(edges, axis=0)
    centre = band.astype(bool) & (abs(longitudinal) < 12) & (abs(lateral) < 25)
    if np.count_nonzero(centre & ((lateral < low - 2) | (lateral > high + 2))) > 12:
        # A crossing under the arrow cannot inherit the side of just one arm.
        return None, None, None
    # The arrow is the origin. Choose the closest exit, retaining clearance
    # to the actual band rather than the edge of the arrow's masking circle.
    sign = -1 if abs(low) < abs(high) else 1
    clearance = low if sign < 0 else -high
    outward = math.degrees(math.atan2(sign * nx, -sign * ny))
    return float(clearance), outward, float(high - low)


def road_position(observation) -> Road | None:
    if observation.reading.corrupt or player_mode(observation) != "foot":
        return None
    return find_road(hud_crop(observation.frame))


def find_road(crop) -> Road | None:
    """The nearest road the minimap shows, or None when it shows none or cannot be read."""
    try:
        if not crop_ok(crop):
            return None
        hsv = cv2.cvtColor(crop[_Y0:_Y1, _X0:_X1], cv2.COLOR_RGB2HSV)
        white = ((hsv[:, :, 1] < 45) & (hsv[:, :, 2] > 195)).astype(np.uint8)
        sheet = cv2.dilate(cv2.morphologyEx(white, cv2.MORPH_OPEN, _ROAD_OPEN), np.ones((5, 5), np.uint8))
        band = white & (1 - sheet)
        band[(_X - ACX) ** 2 + (_Y - ACY) ** 2 < _ARROW_R**2] = 0
        count, labels, stats, _ = cv2.connectedComponentsWithStats(band, 8)
        keep = np.zeros(count, bool)
        for label in range(1, count):
            w, h = stats[label, cv2.CC_STAT_WIDTH], stats[label, cv2.CC_STAT_HEIGHT]
            # A road is a stretch of band, longer than it is wide; icons on the rim are small blobs.
            if stats[label, cv2.CC_STAT_AREA] >= _ROAD_MIN_PIXELS and max(w, h) >= 25:
                keep[label] = True
        road = keep[labels]
        ys, xs = np.nonzero(road)
        if len(xs) == 0:
            return None
        dx = xs + _X0 - ACX
        dy = ys + _Y0 - ACY
        distance = np.hypot(dx, dy)
        nearest = int(np.argmin(distance))
        bearing = math.degrees(math.atan2(dx[nearest], -dy[nearest]))
        # The road's direction near that point: the main axis of its pixels within 15 px.
        near = np.hypot(dx - dx[nearest], dy - dy[nearest]) < 15
        along = None
        if near.sum() >= 20:
            px, py = dx[near] - dx[near].mean(), dy[near] - dy[near].mean()
            cov = np.cov(np.vstack([px, py]))
            values, vectors = np.linalg.eigh(cov)
            if values[1] > 2.0 * max(values[0], 1e-6):
                vx, vy = vectors[:, 1]
                along = math.degrees(math.atan2(vx, -vy))
        # At the arrow the occlusion cuts the band into two short stubs. Fit both together for the
        # edges; the walk itself keeps the direction it always took from the nearest stub.
        edge_along = along
        local = distance < 30
        if float(distance[nearest]) < 25 and local.sum() >= 80:
            values, vectors = np.linalg.eigh(np.cov(np.vstack([dx[local], dy[local]])))
            if values[1] > 3 * max(values[0], 1e-6):
                vx, vy = vectors[:, 1]
                edge_along = math.degrees(math.atan2(vx, -vy))
        clearance = outward = width = None
        # A white sheet around the arrow (car park, plaza, wide junction) is no band to stand beside:
        # the map does not say where its edge is, so it does not say a side either.
        if not sheet[(_X - ACX) ** 2 + (_Y - ACY) ** 2 < _SHEET_R**2].any():
            clearance, outward, width = _road_edges(band, edge_along)
        return Road(bearing, float(distance[nearest]), along, clearance, outward, width)
    except Exception:
        return None


def _wrap(angle: float) -> float:
    return (angle + 180.0) % 360.0 - 180.0


def stick_for(bearing: float, magnitude: float) -> tuple[float, float]:
    """The left stick that walks toward a map bearing: the map's up is where the camera looks."""
    rad = math.radians(bearing)
    return (magnitude * math.sin(rad), -magnitude * math.cos(rad))


def _rotate(stick: tuple[float, float], degrees: float) -> tuple[float, float]:
    """Turn a left-stick direction clockwise (to the right) by `degrees`; y is down on the stick."""
    rad = math.radians(degrees)
    x, y = stick
    c, s = math.cos(rad), math.sin(rad)
    return (c * x - s * y, s * x + c * y)


# ------------------------------------------------------------------ the guard
@dataclass(frozen=True)
class Steer:
    left: tuple[float, float]
    right: tuple[float, float] = (0.0, 0.0)
    state: str = "go"  # "go" | "escape" | "look" | "ahead" | "odd" | "idle"; "climb" | "round" in wayround
    failed: str | None = None
    buttons: tuple[str, ...] = ()  # what the guard presses itself; a skill that reads none presses none


class FootGuard:
    """Sits between a walking skill and the pad. The skill says where it wants the stick; the guard
    watches whether the figure gets anywhere and, when it does not, walks somewhere else for a stretch
    and then tries the wanted direction again. It also turns away from what the judge has called
    blocked for a second, before the figure walks into it.

    Stuck is told from the ground under the arrow (`map_shift` over half a second), and where the map
    cannot be followed from the pipeline's stationary band. Neither reads anything into one tick: a
    verdict needs most of the last 1.2 s of a push that has lasted two seconds."""

    PUSH = 0.5  # a stick at least this far out counts as walking
    STILL_SHIFT = 0.3  # crop pixels in half a second: below this the figure stands
    GOING_SHIFT = 0.5  # above this it walks; walking measured 0.7 to 1.0, sprinting 2 to 3.5
    SHIFT_SPAN = (0.4, 0.6)  # the age of the older crop a shift is measured against
    STUCK_AFTER = 2.0  # seconds of pushing before the guard may call it stuck
    WINDOW = 1.8  # seconds of evidence a verdict rests on: "about two seconds" of getting nowhere
    STILL_SHARE = 0.6  # of the ticks in the window that must say still
    # Escapes in order: the side alternates, the angle grows once both sides have been tried.
    ESCAPES: ClassVar = ((1, 70.0), (-1, 70.0), (1, 120.0), (-1, 120.0))
    ESCAPE_SECONDS = 1.6
    ESCAPE_STUCK_AFTER = 1.2  # an escape that stands this long has failed as well
    PROGRESS_SECONDS = 3.0  # a push this long without a verdict clears the count of failures
    # The judge: blocked must be said for a second by judgments in a row, none older than 1.5 s.
    BLOCKED_SPAN = 0.9
    BLOCKED_COUNT = 3
    JUDGE_LAPSE = 1.5
    # The camera turns at 15 deg/s plus 133 times the requested right stick (docs/LOG.md, 11 November):
    # 0.4 turns about 68 deg/s, so the bound of 100 deg takes about 1.5 s.
    LOOK_STICK = 0.4
    LOOK_RATE = 15.0 + 133.0 * LOOK_STICK
    LOOK_BOUND = 100.0
    AHEAD_SECONDS = 1.5
    JUDGE_TURNS = 2  # judge turns in a row without progress before the judge is left to the stuck check

    def __init__(self, *, first_side: int = 1):
        self.crops: deque = deque()
        self.worlds: deque = deque()
        self.evidence: deque = deque()  # (time, "still" | "going" | None)
        self.state = "go"
        self.state_since = None
        self.push_since = None
        self.failures = 0
        self.still_shift, self.going_shift = self.STILL_SHIFT, self.GOING_SHIFT
        self.first_side = 1 if first_side >= 0 else -1
        self.escape = None
        self.wanted = (0.0, 0.0)
        self.judgments: deque = deque()  # (capture, path answer), newest last
        self.judge_side = self.first_side
        self.judge_turns = 0
        self.look_side = 1
        self.events: list[tuple[float, str]] = []  # what the guard decided, for logs and replays

    # -- evidence
    def resume(self, now: float) -> None:
        """Told by a walk before the first step after ticks on which it kept the pad to itself.
        This guard presses nothing and times nothing that such ticks could cut; see `wayround`."""

    def diagnostic(self) -> str:
        motion = self.evidence[-1][1] if self.evidence else None
        attempts = min(self.failures, len(self.ESCAPES))
        return f"foot:state={self.state};attempts={attempts};motion={motion or 'unknown'}"

    def _evidence(self, observation: Observation) -> str | None:
        now = observation.time
        crop = hud_crop(observation.frame)
        world = world_view(observation.frame)
        shift = None
        image_shift = None
        for history, current, measure in ((self.crops, crop, map_shift), (self.worlds, world, world_shift)):
            while history and history[0][0] < now - self.SHIFT_SPAN[1]:
                history.popleft()
            if current is not None:
                if history and now - history[0][0] >= self.SHIFT_SPAN[0]:
                    if history is self.crops:
                        shift = measure(history[0][1], current)
                    elif shift is None and self.state not in {"look", "ahead"}:
                        image_shift = measure(history[0][1], current)
                history.append((now, current.copy()))
        if shift is not None:
            if shift < self.still_shift:
                return "still"
            return "going" if shift >= self.going_shift else None
        if image_shift is not None:
            if image_shift < 0.25:
                return "still"
            if image_shift >= 0.65:
                return "going"
        return "still" if observation.moving is False else None

    def _verdict(self, now: float, since: float, after: float) -> bool:
        """Stuck: pushed for `after` seconds since `since`, and most of the last window says still."""
        if since is None or now - since < after:
            return False
        start = max(now - self.WINDOW, since + after - self.WINDOW)
        window = [kind for t, kind in self.evidence if t >= start]
        if len(window) < 5:
            return False
        still = window.count("still")
        going = window.count("going")
        # A few translated pixels while the figure turns do not establish travel.
        # Keep requiring a still majority, but tolerate short movement spikes.
        return still >= self.STILL_SHARE * len(window) and going <= 0.25 * len(window)

    def _going(self, now: float) -> bool:
        window = [kind for t, kind in self.evidence if t >= now - self.WINDOW]
        return len(window) >= 5 and window.count("going") >= 0.5 * len(window)

    # -- the judge
    def _note_judgment(self, observation: Observation) -> None:
        judgment = observation.judgment
        if judgment is None or (self.judgments and judgment.capture <= self.judgments[-1][0]):
            return
        answer = judgment.answers.get("path")
        self.judgments.append((judgment.capture, None if answer is None else answer.value))
        while len(self.judgments) > 12:
            self.judgments.popleft()

    def _blocked(self, now: float, after: float | None = None) -> bool:
        """The judge has said blocked for a second, in judgments in a row, the newest still fresh."""
        run = []
        for capture, value in reversed(self.judgments):
            if value != "blocked" or (after is not None and capture < after):
                break
            run.append(capture)
        if len(run) < self.BLOCKED_COUNT or now - run[0] > self.JUDGE_LAPSE:
            return False
        return run[0] - run[-1] >= self.BLOCKED_SPAN

    def _free_since(self, since: float, now: float) -> bool:
        return any(
            value == "free" and capture > since and now - capture <= self.JUDGE_LAPSE
            for capture, value in self.judgments
        )

    # -- the step
    def _enter(self, state: str, now: float) -> None:
        self.state, self.state_since = state, now
        self.events.append((now, state))

    def step(
        self,
        observation: Observation,
        want: tuple[float, float],
        *,
        sprint: bool = False,
        fresh: bool = True,
    ) -> Steer:
        # `sprint` and `fresh` are for the guard in wayround, which measures a sprint by a sprint's
        # pace and has to know a direction that is read from one that is kept.
        now = observation.time
        self._note_judgment(observation)
        if player_mode(observation) != "foot":
            # Nothing to guard: the wanted stick passes, and nothing seen here counts.
            self.crops.clear()
            self.worlds.clear()
            self.evidence.clear()
            self.push_since = None
            return Steer(want, state="idle")
        if observation.reading.corrupt:
            # A damaged tick is stood out with a released left stick and decides nothing; the clocks
            # run on, so a run of them cannot stretch a stretch.
            self.crops.clear()
            self.worlds.clear()
            return Steer((0.0, 0.0), state="odd")
        kind = self._evidence(observation)
        self.evidence.append((now, kind))
        while self.evidence and self.evidence[0][0] < now - 3.0:
            self.evidence.popleft()
        magnitude = math.hypot(*want)
        pushing = magnitude >= self.PUSH
        if self.state_since is None:
            self.state_since = now

        if self.state == "escape":
            side, angle = self.escape
            stick = _rotate(self.wanted, side * angle)
            if self._verdict(now, self.state_since, self.ESCAPE_STUCK_AFTER):
                return self._stuck(now)
            if now - self.state_since < self.ESCAPE_SECONDS:
                return Steer(stick, state="escape")
            # Once a stall is established, an expired turn needs evidence of
            # progress. Starting a new two-second push on every uncertain turn
            # lets skill timeouts erase all four attempts indefinitely.
            if not self._going(now):
                return self._stuck(now)
            self._back_to_go(now)
        if self.state == "look":
            turned = (now - self.state_since) * self.LOOK_RATE
            if self._free_since(self.state_since, now) or turned >= self.LOOK_BOUND:
                if turned >= self.LOOK_BOUND:
                    self.judge_turns += 1
                self._enter("ahead", now)
            else:
                return Steer((0.0, 0.0), (self.look_side * self.LOOK_STICK, 0.0), state="look")
        if self.state == "ahead":
            if now - self.state_since < self.AHEAD_SECONDS and not self._verdict(now, self.state_since, 1.2):
                return Steer((0.0, -max(magnitude, self.PUSH)), state="ahead")
            self._back_to_go(now)

        # state "go"
        if not pushing:
            self.push_since = None
            return Steer(want, state="go")
        if self.push_since is None:
            self.push_since = now
        self.wanted = (want[0] / magnitude, want[1] / magnitude)
        if self._verdict(now, self.push_since, self.STUCK_AFTER):
            return self._stuck(now)
        if now - self.push_since >= self.PROGRESS_SECONDS and self._going(now):
            self.failures = 0
            self.judge_turns = 0
        if self.judge_turns < self.JUDGE_TURNS and self._blocked(now, after=self.state_since):
            self.look_side = self.judge_side
            self.judge_side = -self.judge_side
            self._enter("look", now)
            return Steer((0.0, 0.0), (self.look_side * self.LOOK_STICK, 0.0), state="look")
        return Steer(want, state="go")

    def _back_to_go(self, now: float) -> None:
        self._enter("go", now)
        self.push_since = None

    def _stuck(self, now: float) -> Steer:
        self.failures += 1
        if self.failures > len(self.ESCAPES):
            self.state, self.state_since = "failed", now
            self.events.append((now, "stuck"))
            return Steer((0.0, 0.0), state="failed", failed="stuck")
        side, angle = self.ESCAPES[self.failures - 1]
        self.escape = (side * self.first_side, angle)
        self._enter("escape", now)
        return Steer(_rotate(self.wanted, self.escape[0] * angle), state="escape")


# ------------------------------------------------------------------ walking to a road
class WalkRoad:
    """Walk to the nearest road the minimap shows and then along it, getting free on the way."""

    name = "walk_road"
    parameters: ClassVar = {"duration": (2.0, 30.0, 15.0), "sprint": (False, True)}
    prompt = (
        "On foot: walk to the nearest road the minimap shows, then along it the way the figure faces; "
        "leaves the carriageway where the map shows the figure in it; holds a compass heading off-road "
        "and turns away from walls. Ends done at its time limit, saying road-side or side unknown. "
        "Fails stuck when four ways round have failed."
    )

    ROAD_WAIT = 1.0  # seconds of readable map without a road before it says so
    UNREADABLE_WAIT = 1.5  # the reader calls a few frames in a hundred damaged, sixteen ticks at most
    STICK = 0.85
    ON_ROAD_SECONDS = 0.3  # the arrow has to be on the road this long before the skill follows it
    # A lane reading is acted on this long, so that one tick the map cannot read does not turn it back.
    LEAVE_SECONDS = 1.5

    def __init__(self, args: dict):
        if not isinstance(args, dict) or set(args) - self.parameters.keys():
            raise ValueError("walk_road accepts only duration and sprint")
        low, high, default = self.parameters["duration"]
        value = args.get("duration", default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("duration must be a finite number")
        sprint = args.get("sprint", False)
        if not isinstance(sprint, bool):
            raise ValueError("sprint must be true or false")
        self.limit = float(max(low, min(high, value)))
        self.sprint = sprint
        self.profile = active()
        self.guard = FootGuard()
        self.started = None
        self.finished = None
        self.last_time = None
        self.readable = 0.0  # seconds of readable map without a road
        self.unreadable = 0.0  # seconds of a map that could not be read at all
        self.road_seen = False
        self.on_road_since = None
        self.sense = None  # the way along the road, kept once chosen
        self.heading = None  # picture bearing, transported by the north disc
        self.compass_heading = None
        self.north = None
        self.position = "unknown"  # lane | side | unknown, from the last map reading
        self.side_since = None  # since when the edge of the band has been near and the figure outside it
        self.leave_until = None  # a lane was read: keep going outward until then, or until a side is read

    def stop(self, reason: str = "interrupted") -> SkillResult:
        self.finished = SkillResult(status="failed", reason=reason)
        return self.finished

    def step(self, observation: Observation) -> SkillResult:
        if self.finished is not None:
            return self.finished
        now = observation.time
        if self.started is None:
            self.started = now
        if self.last_time is not None and now < self.last_time:
            return self.stop("clock-reversed")
        gap = 0.0 if self.last_time is None else min(now - self.last_time, 0.1)
        self.last_time = now
        elapsed = now - self.started
        foot = player_mode(observation) == "foot" and not observation.reading.corrupt
        crop = hud_crop(observation.frame) if foot else None
        if crop is None:
            self.position, self.side_since = "unknown", None
            if elapsed >= self.limit:
                return self._end(None)
            if not foot:
                # Nothing is read from this tick and nothing is pushed on it.
                self.guard.step(observation, (0.0, 0.0))
                return SkillResult()
            # The road is only in the picture; without one there is nothing to walk by.
            return self.stop("no-frame")
        north = north_bearing(crop)
        if north is not None:
            self.north = north
        road = find_road(crop)
        self._locate(road, now)
        if elapsed >= self.limit:
            return self._end(road)
        if road is not None:
            self.road_seen = True
            self.readable = 0.0
            self.heading = self._bearing(road, observation.reading.arrow, now)
            if self.north is not None:
                self.compass_heading = _wrap(self.heading - self.north)
        elif crop_ok(crop):
            self.readable += gap
            if self.heading is None:
                self.heading = 0.0
            if north is not None:
                if self.compass_heading is None:
                    self.compass_heading = _wrap(self.heading - north)
                self.heading = _wrap(self.compass_heading + north)
        else:
            self.unreadable += gap
        if self.heading is None:
            # The only stand-still the map causes, and it ends: UNREADABLE_WAIT, then map-unreadable.
            self.guard.step(observation, (0.0, 0.0))
            if self.unreadable >= self.UNREADABLE_WAIT:
                return self.stop("map-unreadable")
            return SkillResult(reason="map unreadable")
        steer = self.guard.step(observation, stick_for(self.heading, self.STICK))
        if steer.failed:
            self.finished = SkillResult(status="failed", reason=steer.failed)
            return self.finished
        if (
            road is not None
            and road.outward is not None
            and road.distance <= _ON_ROAD_R
            and steer.state == "escape"
            and sum(a * b for a, b in zip(steer.left, stick_for(road.outward, 1.0), strict=True)) < -0.05
        ):
            # Where the edge is known and near, a way round that turns toward the carriageway is not taken.
            return SkillResult(Pad(left=stick_for(road.outward, self.STICK)), reason="leaving lane")
        buttons = self.profile.sprint_buttons(elapsed) if self.sprint and steer.state == "go" else ()
        pad = Pad(buttons=buttons, left=steer.left, right=steer.right)
        return SkillResult(pad, reason=self._reason(road))

    def _locate(self, road: Road | None, now: float) -> None:
        self.position = road.position if road is not None else "unknown"
        near = road is not None and road.position == "side" and road.distance <= _ON_ROAD_R
        if not near:
            self.side_since = None
        elif self.side_since is None:
            self.side_since = now

    def _reason(self, road: Road | None) -> str | None:
        if road is None:
            return None  # no road on the map: the compass walk, as it always was
        if self.position == "lane":
            return "leaving lane"
        if self.position == "unknown":
            return "side unknown"
        return "at roadside" if road.distance <= _ON_ROAD_R else "walking to the road; side known"

    def _end(self, road: Road | None) -> SkillResult:
        """The time limit. Done at the roadside only on a positive reading with the band's edge near; in a
        lane it says so; with the side unknown it ends as the walk always ended and says that."""
        if self.side_since is not None and self.last_time - self.side_since >= self.ON_ROAD_SECONDS:
            self.finished = SkillResult(status="done", reason="road-side (map band; kerb unverified)")
        elif self.position == "lane":
            self.finished = SkillResult(status="failed", reason="still-in-lane")
        elif road is None and not self.road_seen:
            self.finished = SkillResult(status="done", reason="time-limit")
        elif self.position == "unknown":
            self.finished = SkillResult(status="done", reason="time-limit; side unknown")
        else:
            self.finished = SkillResult(status="done", reason="time-limit; roadside not reached")
        return self.finished

    def _bearing(self, road: Road, arrow: float | None, now: float) -> float:
        # The runner reads this for road_reached, whether or not the edges could be told.
        if road.distance > _ON_ROAD_R:
            self.on_road_since = None
        elif self.on_road_since is None:
            self.on_road_since = now
        # Only a positive lane reading leaves the carriageway. Where the side is unknown the walk goes as
        # it always did, to the road and along it; where it is known and far it still goes to the road.
        if road.position == "lane" or (
            road.position == "side"
            and road.clearance < 4
            and self.leave_until is not None
            and now < self.leave_until
        ):
            self.leave_until = now + self.LEAVE_SECONDS
            return road.outward
        if road.position == "unknown" and self.leave_until is not None and now < self.leave_until:
            if self.compass_heading is not None and self.north is not None:
                return _wrap(self.compass_heading + self.north)
        else:
            self.leave_until = None
        if road.distance > _ON_ROAD_R:
            return road.bearing
        if road.along is None or now - self.on_road_since < self.ON_ROAD_SECONDS:
            return road.bearing if self.sense is None else self.sense
        # Along the road, the way nearer to where the figure faces, and that way kept: the map turns
        # under the camera, so the choice is renewed against the last one, not against the arrow.
        reference = self.sense if self.sense is not None else (arrow if arrow is not None else 0.0)
        forward = road.along if abs(_wrap(road.along - reference)) <= 90 else _wrap(road.along + 180)
        self.sense = forward
        return forward
