"""The camera's view read from the player's figure, and the skill that sets the far one.

The touchpad steps through four views, on foot in this order: far, first person, near, middle,
far again. Four presses come back to where they began, so a press costs nothing that the next
presses do not undo. What the skill reads is the figure: how tall its box stands, whether the
lower edge of the frame cuts it, and where its feet are, as fractions of the frame.

Two ways of reading it. The bands name a view from one figure: they are fitted on lab/camera/sample
(140 frames from ten recordings of Kerim's and five sessions of the pilot's, labelled by eye) and on
lab/camera/views, and they are right when the camera is the one they were fitted on and no more.
The camera's pitch, a pavement or a hill under the figure, the night and a cut box move the numbers
(fourteen tries on the console on 12 November reached the far view four times with the bands alone),
so the bands carry only the fast path, a far figure that stands clearly named in the first moments.
The survey needs no band: it steps once round the four views, measures the figure in each, and takes
the view whose whole figure is the smallest.
"""

import math
from collections import Counter
from dataclasses import dataclass
from typing import ClassVar

from .contract import FRAME_SIZE, Detection, Observation, Pad, SkillResult, player_mode
from .objects import is_player

VEHICLES = ("car", "truck", "bus", "motorcycle", "bicycle")
NAMED = ("far", "middle", "near")
RIDDEN = ("motorcycle", "bicycle")  # the detector calls a quad a motorcycle
SEAT_WIDTH = 2.2  # a vehicle this many times as wide as the figure is no seat for it


@dataclass(frozen=True)
class ViewBand:
    view: str
    height: tuple[float, float]  # the figure's box height over the frame's height
    feet: tuple[float, float]  # where the box ends, over the frame's height


# Between the bands lies a gap on purpose: a figure there is on its way from one view to the other,
# or pushed by a wall, and is named nothing. The camera's pitch moves a view's figure: the game's
# own camera shows a far figure 0.25 to 0.33 high with its feet at 0.69 to 0.81, the camera that
# `level_camera` leaves, low and looking slightly up, 0.34 to 0.355 and 0.81 to 0.84. Middle ones
# stand 0.40 to 0.46 high, near ones 0.53 to 0.61 and cut by the lower edge. The one frame in the
# gap, a sprint past a truck at 0.375, is neither far nor middle by eye.
FOOT_BANDS = (
    ViewBand("far", (0.23, 0.365), (0.66, 0.87)),
    ViewBand("middle", (0.385, 0.475), (0.82, 0.975)),
    ViewBand("near", (0.52, 0.65), (0.95, 1.0)),
)
CALIBRATIONS = {"foot": FOOT_BANDS}
MIN_CONFIDENCE = 0.8
CENTER = (0.30, 0.56)  # where the figure's middle may stand across the frame
ASPECT = (0.2, 0.9)  # width over height of its box


@dataclass(frozen=True)
class ViewReading:
    """One look at one detection. `view` is far, middle or near; or none when no figure is in the
    picture, rider when a vehicle carries it, and unknown for anything the bands do not name."""

    view: str = "unknown"
    reason: str = "unread"
    height: float | None = None
    feet: float | None = None


def _frame_size(frame_shape) -> tuple[float, float] | None:
    try:
        height, width = float(frame_shape[0]), float(frame_shape[1])
    except (TypeError, ValueError, IndexError):
        return None
    return (width, height) if min(width, height) >= 64 and math.isfinite(width * height) else None


def _rides(figure: Detection, vehicle: Detection, height: float) -> bool:
    """A vehicle stands under the figure's feet and across its body, a motorcycle or a bicycle
    always and any other no wider than a seat for the figure: a pedestrian in front of a truck
    is not on it."""
    fx0, _, fx1, fy1 = figure.box
    vx0, vy0, vx1, vy1 = vehicle.box
    across = min(fx1, vx1) - max(fx0, vx0)
    if across < 0.5 * (fx1 - fx0) or not vy0 <= fy1 <= vy1 + 0.03 * height:
        return False
    return vehicle.kind in RIDDEN or (vx1 - vx0) <= SEAT_WIDTH * (fx1 - fx0)


def read_view(
    figure: Detection | None,
    frame_shape,
    *,
    vehicles: tuple[Detection, ...] = (),
    others: tuple[Detection, ...] = (),
    mode: str = "foot",
    calibrations: dict[str, tuple[ViewBand, ...]] | None = None,
) -> ViewReading:
    """The view one detection of the figure shows.

    `vehicles` are the vehicle boxes of the same detection and `others` the other people in it. A
    vehicle can be added with its own bands under its own `mode`; a mode without bands reads unknown.
    """
    bands = (CALIBRATIONS if calibrations is None else calibrations).get(mode)
    if bands is None:
        return ViewReading(reason=f"uncalibrated-mode:{mode}")
    size = _frame_size(frame_shape)
    if size is None:
        return ViewReading(reason="invalid-frame")
    if figure is None:
        return ViewReading("none", "no-figure")
    w, h = size
    x0, y0, x1, y1 = figure.box
    if not all(math.isfinite(v) for v in (*figure.box, figure.confidence)):
        return ViewReading(reason="invalid-box")
    if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
        return ViewReading(reason="invalid-box")
    height, feet = (y1 - y0) / h, y1 / h
    if any(_rides(figure, vehicle, h) for vehicle in vehicles if vehicle.kind in VEHICLES):
        return ViewReading("rider", "vehicle-under-figure", height, feet)
    if figure.confidence < MIN_CONFIDENCE:
        return ViewReading(reason="uncertain-figure", height=height, feet=feet)
    # Another person where the figure usually stands may be the one the detector took for it.
    if any(item.kind == "person" and is_player(item) for item in others):
        return ViewReading(reason="second-person", height=height, feet=feet)
    placed = CENTER[0] <= (x0 + x1) / (2 * w) <= CENTER[1] and ASPECT[0] <= (x1 - x0) / (y1 - y0) <= ASPECT[1]
    if not placed:
        return ViewReading(reason="figure-off-place", height=height, feet=feet)
    matches = [
        band.view
        for band in bands
        if band.height[0] <= height <= band.height[1] and band.feet[0] <= feet <= band.feet[1]
    ]
    if len(matches) == 1:
        return ViewReading(matches[0], "in-band", height, feet)
    return ViewReading(reason="between-bands", height=height, feet=feet)


def read_observation(observation: Observation, *, mode: str = "foot") -> ViewReading:
    """The view the detections of an observation show."""
    frame = observation.frame
    shape = frame.shape if hasattr(frame, "shape") else (FRAME_SIZE[1], FRAME_SIZE[0])
    vehicles = tuple(item for item in observation.objects if item.kind in VEHICLES)
    if observation.figure_vehicle is not None:
        vehicles += (observation.figure_vehicle,)
    others = tuple(item for item in observation.objects if item.kind == "person")
    return read_view(observation.figure, shape, vehicles=vehicles, others=others, mode=mode)


class Watch:
    """Readings over time: a view is named once the readings of half a second agree on it."""

    SPAN = 0.5  # seconds a reading has to hold
    MINIMUM = 3  # readings from three different detections
    HORIZON = 1.0  # how far back the decision looks
    AGREE = 2 / 3

    def __init__(self):
        self.samples: list[tuple[float, ViewReading]] = []

    def reset(self):
        self.samples.clear()

    def add(self, stamp: float, reading: ViewReading):
        self.samples.append((stamp, reading))

    def view(self) -> str | None:
        """far, middle or near when the readings of the last half second and more agree, else None."""
        if not self.samples:
            return None
        recent = [item for item in self.samples if item[0] >= self.samples[-1][0] - self.HORIZON]
        if len(recent) < self.MINIMUM or recent[-1][0] - recent[0][0] < self.SPAN:
            return None
        named = Counter(r.view for _, r in recent if r.view in NAMED)
        if len(named) != 1:
            return None
        view, count = next(iter(named.items()))
        return view if count >= self.AGREE * len(recent) else None


# ------------------------------------------------------------------ the survey
READABLE = ("in-band", "between-bands")  # a figure that stands where the player's does, whatever its size
CUT = 0.975  # a box that reaches this far down is cut by the lower edge: a near figure, not a whole one
WINDOW = 1.0  # seconds of detections that make one measurement
WINDOW_MOST = 3.0  # and the longest a window waits for a figure it can read
RECENT = 1.5  # a window is read over its last seconds: the picture may still be moving at its start
MIN_READINGS = 4
AGREE = 0.6  # of the readings of a window must show a figure, or none, for it to be called so
FAR_RATIO = 0.85  # the far figure is at most this much of the next larger one
SAME = 0.12  # two windows of a figure within this much of each other show one view
ARRIVED = 0.15  # and the figure of the far view, found again, within this much of the one surveyed


@dataclass(frozen=True)
class Look:
    """What a window of detections shows: a whole figure of some height, one cut by the lower edge,
    no figure at all (first person, or a figure hidden), or something no measurement can use."""

    kind: str  # figure, none, unclear
    height: float = 0.0
    cut: bool = False

    def text(self) -> str:
        if self.kind == "figure":
            return f"{self.height:.2f}" + ("cut" if self.cut else "")
        return "none" if self.kind == "none" else "?"


def look_at(readings: list[ViewReading]) -> Look:
    """The measurement of a window: the median height of the figures that can be read, if most
    of the readings are such figures, none if most show no figure, else unclear."""
    figures = [r for r in readings if r.reason in READABLE and r.height is not None and r.feet is not None]
    if readings and sum(1 for r in readings if r.view == "none") >= AGREE * len(readings):
        return Look("none")
    if not readings or len(figures) < AGREE * len(readings):
        return Look("unclear")
    heights = sorted(r.height for r in figures)
    feet = sorted(r.feet for r in figures)
    return Look("figure", heights[len(heights) // 2], feet[len(feet) // 2] >= CUT)


def alike(a: Look, b: Look) -> bool:
    """The same view twice: a press that was lost shows as two equal neighbours."""
    if a.kind != b.kind or a.kind == "unclear":
        return False
    return a.kind == "none" or (
        a.cut == b.cut and abs(a.height - b.height) <= SAME * max(a.height, b.height) + 0.01
    )


def far_of(looks: list[Look]) -> tuple[int | None, str]:
    """The index of the far view among the looks of one round, in the order the presses went, or why
    there is none. The far view is the one whose whole figure is the smallest, well below the next
    larger one. First person is the one without a figure: it comes right after far, which is checked
    when only one view shows none."""
    if any(look.kind == "unclear" for look in looks):
        return None, "views-unread"
    shown = [(i, look) for i, look in enumerate(looks) if look.kind == "figure"]
    if not shown:
        return None, "no-figure"
    whole = [(i, look) for i, look in shown if not look.cut]
    if not whole:
        return None, "no-whole-figure"
    index, far = min(whole, key=lambda item: item[1].height)
    larger = [look.height for i, look in shown if i != index]
    if not larger:
        return None, "one-view-only"
    if far.height > FAR_RATIO * min(larger):
        return None, "views-alike"
    firsts = [i for i, look in enumerate(looks) if look.kind == "none"]
    if len(firsts) == 1 and firsts[0] != (index + 1) % len(looks):
        return None, "views-disagree"
    return index, "far"


TOUCHPAD = Pad(buttons=("touchpad",))
FORWARD = Pad(left=(0.0, -1.0))


class SetFarView:
    """Set the camera to the far view behind the figure.

    Fast path: a far figure that the bands name clearly within the first two seconds on foot is
    done at once, with no press. Else the survey: press, settle, measure the figure for a second,
    four times, which is one round of the views and ends where it began. The far view is the one of
    them whose whole figure is the smallest, well below the next larger one (far_of). The skill then
    presses on to it, measuring after every press and not counting them, so that a press that was
    lost costs one more and nothing else, and ends done when the figure there is as small as the one
    it surveyed. A round that shows no figure, or two views it cannot tell apart, fails with the
    four measurements in the reason.

    A window whose figure no measurement can use (seen from the front, another person by it) gets
    one short step forward, which swings the camera behind the figure, and is measured again.
    The skill presses only on the game's screen, only after the mode has read foot for a second, and
    never with a vehicle under the figure.

    The game's idle camera, which takes over when nobody has touched the pad for a while, shows the
    figure from the side and off the middle, where no person is taken for it. The first press ends it
    and the round goes on from there; it ends in the far view like any other (20261112-141056).
    """

    name = "set_far_view"
    # A survey from first person takes seven presses of 2.8 s each (a press, 1.5 s for the picture to
    # settle, a second of detections) and two seconds before it, about 22 s; a camera that shows the
    # figure from the front after every press adds a step and a second to each, about 38 s, and every
    # lost press 3 s to 5 s more.
    parameters: ClassVar = {"duration": (10.0, 60.0, 50.0)}
    prompt = (
        "Sets the camera to the far view behind the figure, on foot only: at once when it stands in it, "
        "else by stepping through the four views and taking the one with the smallest whole figure. "
        "Fails when no view shows a figure, the views cannot be told apart, the screen is not the game, "
        "or the figure rides a vehicle."
    )
    # An opening that was cut in half would leave the camera in some other view.
    uninterruptible: ClassVar = True

    PULSE = 0.1  # a press, as a person's is
    SETTLE = 1.5  # the picture after a press; the camera took more than a second in the recordings
    STEP = 0.4  # left stick forward, as a person takes a step
    AFTER_STEP = 1.0
    FAST = 2.0  # seconds on foot in which the bands may name the far view; then the survey
    FOOT_FOR = 1.0  # the minimap reader holds a wrong class for up to 0.83 s
    UNSAFE_LIMIT = 4.0
    MAX_AGE = 0.6  # of the detections, against the tick that reads them
    STALL_LIMIT = 2.0  # no new detection this long: nothing to read
    LATE = 0.3  # a tick later than this has not held the pad for all that time
    ROUND = 4  # presses that make a round of the views
    SURVEY_PRESSES = 6  # a round and two lost presses
    LOST = 2  # presses on the way to the far view that may show nothing new
    MAX_PRESSES = 11

    def __init__(self, args: dict):
        if not isinstance(args, dict) or set(args) - self.parameters.keys():
            raise ValueError("set_far_view accepts only duration")
        low, high, default = self.parameters["duration"]
        duration = args.get("duration", default)
        if (
            isinstance(duration, bool)
            or not isinstance(duration, (int, float))
            or not math.isfinite(duration)
        ):
            raise ValueError("duration must be a finite number")
        self.limit = float(max(low, min(high, duration)))
        self.started = None
        self.previous = None
        self.terminal = None
        self.presses = 0
        self.steps = 0
        self.step_allowed = True
        self.pulse_until = None
        self.step_until = None
        self.settle_until = -math.inf
        self.foot_since = None
        self.unsafe_since = None
        self.fresh_at = None
        self.last_stamp = None
        self.watch = Watch()
        self.last_view = "unknown"
        self.phase = "fast"  # fast, survey, goto, verify
        self.window: list[tuple[float, ViewReading]] = []
        self.window_from = -math.inf
        self.looks: list[Look] = []  # the survey, in the order the presses went
        self.target: Look | None = None
        self.owed = 0  # presses the far view is still away, by the survey
        self.last_look: Look | None = None
        self.goto_presses = 0
        self.shown = False  # some window of the survey showed a figure

    def _survey_text(self) -> str:
        return "/".join(look.text() for look in self.looks)

    def _finish(self, status, reason):
        self.terminal = SkillResult(status=status, reason=reason)
        return self.terminal

    def _fail(self, why):
        survey = f"; survey={self._survey_text()}" if self.looks else ""
        return self._finish("failed", f"{why}; last={self.last_view}; presses={self.presses}{survey}")

    def stop(self, reason) -> SkillResult:
        return self._finish("failed", str(reason))

    def _unsafe(self, observation: Observation) -> str | None:
        if observation.hud is None:
            return "hud-unread"
        if observation.hud.screen != "game":
            return f"screen-{observation.hud.screen}"
        if observation.reading.corrupt and observation.mode is None:
            return None  # the minimap is damaged on this tick and says nothing either way
        if player_mode(observation) != "foot":
            return "not-on-foot"
        if read_observation(observation).view == "rider":
            return "rider"
        return None

    def _release(self, now):
        """The pad goes neutral. What the press did to the view is read again after a settle."""
        if self.pulse_until is not None:
            self.settle_until = now + self.SETTLE
        elif self.step_until is not None:
            self.settle_until = now + self.AFTER_STEP
        if self.pulse_until is not None or self.step_until is not None:
            self.window, self.window_from = [], self.settle_until
        self.pulse_until = self.step_until = None
        self.watch.reset()

    def step(self, observation: Observation) -> SkillResult:
        if self.terminal is not None:
            return self.terminal
        now = observation.time
        if not math.isfinite(now) or (self.previous is not None and now < self.previous):
            return self._finish("failed", "invalid-clock")
        if self.started is None:
            self.started = now
        if now - self.started >= self.limit:
            return self._fail("time-limit")
        late = self.previous is not None and now - self.previous > self.LATE
        self.previous = now
        unsafe = self._unsafe(observation)
        if unsafe:
            self._release(now)
            self.foot_since = None
            if self.unsafe_since is None:
                self.unsafe_since = now
            if now - self.unsafe_since >= self.UNSAFE_LIMIT:
                return self._fail(unsafe)
            return SkillResult()
        self.unsafe_since = None
        if late:
            self._release(now)
            return SkillResult()
        if observation.reading.corrupt and observation.mode is None:
            # A damaged tick decides nothing; a press or a step already begun goes on by the clock.
            return SkillResult(pad=self._held(now))
        if self.foot_since is None:
            self.foot_since = now
        if self.pulse_until is not None or self.step_until is not None:
            held = self._held(now)
            if held != Pad():
                return SkillResult(pad=held)
            return SkillResult()

        stamp = observation.objects_time
        fresh = stamp is not None and math.isfinite(stamp) and 0 <= now - stamp <= self.MAX_AGE
        if fresh:
            self.fresh_at = now
        if now - (self.started if self.fresh_at is None else self.fresh_at) >= self.STALL_LIMIT:
            return self._fail("no-detections")
        if now < self.settle_until or not fresh or stamp <= self.settle_until or stamp == self.last_stamp:
            return SkillResult()
        self.last_stamp = stamp
        reading = read_observation(observation)
        self.last_view = reading.view if reading.view in NAMED or reading.view == "none" else "unknown"
        if self.phase == "fast":
            self.watch.add(stamp, reading)
            if self.watch.view() == "far":
                return self._finish("done", f"far; presses={self.presses}")
            if now - self.foot_since >= self.FAST:
                self.phase = "survey"
                return self._press(now)
            return SkillResult()
        if stamp <= self.window_from:
            return SkillResult()
        self.window.append((stamp, reading))
        return self._measure(now)

    def _held(self, now) -> Pad:
        """The pad of a press or a step that is under way, released when its time is up."""
        if self.pulse_until is not None:
            if now < self.pulse_until:
                return TOUCHPAD
            self._release(now)
        elif self.step_until is not None:
            if now < self.step_until:
                return FORWARD
            self._release(now)
        return Pad()

    def _measure(self, now) -> SkillResult:
        """The window closes once it has a second of detections and they show something: a figure,
        or none. A figure that no measurement can use is given one step, then a few seconds."""
        stamps = [t for t, _ in self.window]
        span = stamps[-1] - stamps[0]
        recent = [r for t, r in self.window if t >= stamps[-1] - RECENT]
        if span < WINDOW or len(recent) < MIN_READINGS:
            return SkillResult()
        look = look_at(recent)
        if look.kind == "unclear":
            if self.step_allowed and self.presses:
                return self._step(now)
            if span < WINDOW_MOST:
                return SkillResult()
            if self.phase == "survey":
                self.looks.append(look)  # the round cannot be read: the reason shows which window
                return self._fail("views-unread")
        return self._closed(now, look)

    def _closed(self, now, look: Look) -> SkillResult:
        previous, self.last_look = self.last_look, look
        if self.phase == "survey":
            if previous is not None and alike(previous, look):
                self.looks[-1] = previous  # a press that was lost: the same view twice
            else:
                self.looks.append(look)
            self.shown |= look.kind != "none"
            if not self.shown and self.presses >= self.ROUND:
                return self._fail("no-figure")  # a round and no view showed one
            if len(self.looks) < self.ROUND:
                return self._press(now) if self.presses < self.SURVEY_PRESSES else self._fail("views-alike")
            index, why = far_of(self.looks)
            if index is None:
                return self._fail(why)
            self.target = self.looks[index]
            self.owed = (index - (len(self.looks) - 1)) % len(self.looks)
            if self.owed == 0:
                self.phase = "verify"
                self.window, self.window_from = [], now
                return SkillResult()
            self.phase = "goto"
            return self._press(now)
        # goto and verify: the figure there is measured after every press and not counted
        moved = previous is None or not alike(previous, look)
        if moved:
            self.owed -= 1
        if look.kind == "figure" and not look.cut and self.owed <= 0 and self._as_small(look):
            return self._finish("done", f"far; presses={self.presses}; survey={self._survey_text()}")
        if self.phase == "verify" or self.goto_presses >= (self.ROUND - 1) + self.LOST:
            return self._fail("far-lost")
        return self._press(now)

    def _as_small(self, look: Look) -> bool:
        return abs(look.height - self.target.height) <= ARRIVED * self.target.height + 0.01

    def _press(self, now) -> SkillResult:
        if self.presses >= self.MAX_PRESSES:
            return self._fail("too-many-presses")
        self.presses += 1
        if self.phase == "goto":
            self.goto_presses += 1
        self.step_allowed = True
        self.pulse_until = now + self.PULSE
        self.window = []
        self.watch.reset()
        return SkillResult(pad=TOUCHPAD)

    def _step(self, now) -> SkillResult:
        self.steps += 1
        self.step_allowed = False
        self.step_until = now + self.STEP
        self.window = []
        return SkillResult(pad=FORWARD)
