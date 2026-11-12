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
_ROAD_OPEN = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (19, 19))
_ARROW_R = 8  # the white arrow itself
_ON_ROAD_R = 11  # a road pixel this close to the arrow puts the figure on the road
_ROAD_MIN_PIXELS = 80  # a piece of band smaller than this is an icon or a letter, not a road


@dataclass(frozen=True)
class Road:
    bearing: float  # map degrees from the arrow to the nearest road pixel, 0 = up = camera forward
    distance: float  # crop pixels to it
    along: float | None  # one direction of the road at that point, map degrees; None if not readable


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
        return Road(bearing, float(distance[nearest]), along)
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
    state: str = "go"  # "go" | "escape" | "look" | "ahead" | "odd" | "idle"
    failed: str | None = None


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
        self.evidence: deque = deque()  # (time, "still" | "going" | None)
        self.state = "go"
        self.state_since = None
        self.push_since = None
        self.failures = 0
        self.first_side = 1 if first_side >= 0 else -1
        self.escape = None
        self.wanted = (0.0, 0.0)
        self.judgments: deque = deque()  # (capture, path answer), newest last
        self.judge_side = self.first_side
        self.judge_turns = 0
        self.look_side = 1
        self.events: list[tuple[float, str]] = []  # what the guard decided, for logs and replays

    # -- evidence
    def diagnostic(self) -> str:
        motion = self.evidence[-1][1] if self.evidence else None
        attempts = min(self.failures, len(self.ESCAPES))
        return f"foot:state={self.state};attempts={attempts};motion={motion or 'unknown'}"

    def _evidence(self, observation: Observation) -> str | None:
        now = observation.time
        crop = hud_crop(observation.frame)
        shift = None
        if crop is not None:
            while self.crops and self.crops[0][0] < now - self.SHIFT_SPAN[1]:
                self.crops.popleft()
            if self.crops and now - self.crops[0][0] >= self.SHIFT_SPAN[0]:
                shift = map_shift(self.crops[0][1], crop)
            self.crops.append((now, crop.copy()))
        if shift is not None:
            if shift < self.STILL_SHIFT:
                return "still"
            return "going" if shift >= self.GOING_SHIFT else None
        # Without a followable map: the pipeline's stationary band, which a camera turn cannot fake.
        # Its "moving" can be the camera turning the map and says nothing about the figure.
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

    def step(self, observation: Observation, want: tuple[float, float]) -> Steer:
        now = observation.time
        self._note_judgment(observation)
        if player_mode(observation) != "foot":
            # Nothing to guard: the wanted stick passes, and nothing seen here counts.
            self.crops.clear()
            self.evidence.clear()
            self.push_since = None
            return Steer(want, state="idle")
        if observation.reading.corrupt:
            # A damaged tick is stood out with a released left stick and decides nothing; the clocks
            # run on, so a run of them cannot stretch a stretch.
            self.crops.clear()
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
        "turns away from walls by itself. Fails no-road when the map shows no road, stuck when "
        "four ways round have failed. Cars pass on roads. duration is the time limit."
    )

    ROAD_WAIT = 1.0  # seconds of readable map without a road before it says so
    UNREADABLE_WAIT = 2.0  # the reader calls a few frames in a hundred damaged, sixteen ticks at most
    STICK = 0.85
    ON_ROAD_SECONDS = 0.3  # the arrow has to be on the road this long before the skill follows it

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
        self.heading = None  # the last bearing walked, kept through ticks without a reading

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
        if elapsed >= self.limit:
            self.finished = SkillResult(status="done", reason="time-limit")
            return self.finished
        if player_mode(observation) != "foot" or observation.reading.corrupt:
            # Nothing is read from this tick and nothing is pushed on it.
            self.guard.step(observation, (0.0, 0.0))
            return SkillResult()
        crop = hud_crop(observation.frame)
        if crop is None:
            # The road is only in the picture; without one there is nothing to walk by.
            return self.stop("no-frame")
        road = find_road(crop)
        if road is None:
            if crop_ok(crop):
                self.readable += gap
            else:
                self.unreadable += gap
            if not self.road_seen and self.readable >= self.ROAD_WAIT:
                self.finished = SkillResult(status="failed", reason="no-road")
                return self.finished
            if self.heading is None and self.unreadable >= self.UNREADABLE_WAIT:
                return self.stop("map-unreadable")
        else:
            self.road_seen = True
            self.readable = 0.0
            self.heading = self._bearing(road, observation.reading.arrow, now)
        if self.heading is None:
            self.guard.step(observation, (0.0, 0.0))
            return SkillResult()
        steer = self.guard.step(observation, stick_for(self.heading, self.STICK))
        if steer.failed:
            self.finished = SkillResult(status="failed", reason=steer.failed)
            return self.finished
        buttons = self.profile.sprint_buttons(elapsed) if self.sprint and steer.state == "go" else ()
        return SkillResult(Pad(buttons=buttons, left=steer.left, right=steer.right))

    def _bearing(self, road: Road, arrow: float | None, now: float) -> float:
        if road.distance > _ON_ROAD_R:
            self.on_road_since = None
            return road.bearing
        if self.on_road_since is None:
            self.on_road_since = now
        if road.along is None or now - self.on_road_since < self.ON_ROAD_SECONDS:
            return road.bearing if self.sense is None else self.sense
        # Along the road, the way nearer to where the figure faces, and that way kept: the map turns
        # under the camera, so the choice is renewed against the last one, not against the arrow.
        reference = self.sense if self.sense is not None else (arrow if arrow is not None else 0.0)
        forward = road.along if abs(_wrap(road.along - reference)) <= 90 else _wrap(road.along + 180)
        self.sense = forward
        return forward
