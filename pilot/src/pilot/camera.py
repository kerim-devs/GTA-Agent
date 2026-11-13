"""The camera's view read from the player's figure, and the skill that sets the far one.

The touchpad steps through four views, on foot in this order: far, first person, near, middle,
far again. Four presses come back to where they began, so a press costs nothing that the next
presses do not undo, and the skill does not have to know which view it is in when no figure shows.
What it does read is the figure: how tall its box stands and where its feet are, as fractions of
the frame. The bands are fitted on lab/camera/sample (90 frames from ten of Kerim's recordings,
labelled by eye) and on lab/camera/views.
"""

import math
from collections import Counter
from dataclasses import dataclass
from typing import ClassVar

import cv2

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
# or pushed by a wall, and is named nothing. Far figures stand 0.25 to 0.33 high in the sample,
# middle ones 0.40 to 0.46, near ones 0.54 to 0.61 and cut by the lower edge.
FOOT_BANDS = (
    ViewBand("far", (0.23, 0.345), (0.66, 0.86)),
    ViewBand("middle", (0.38, 0.475), (0.82, 0.96)),
    ViewBand("near", (0.53, 0.65), (0.965, 1.0)),
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

    @property
    def span(self) -> float:
        return self.samples[-1][0] - self.samples[0][0] if self.samples else 0.0

    def lasted(self, seconds: float) -> bool:
        """Readings of at least this long, from at least three detections, are in."""
        return len(self.samples) >= self.MINIMUM and self.span >= seconds

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

    def hidden(self) -> float:
        """How long no figure has shown, up to the last reading."""
        if not self.samples or self.samples[-1][1].view != "none":
            return 0.0
        start = self.samples[-1][0]
        for stamp, reading in reversed(self.samples):
            if reading.view != "none":
                break
            start = stamp
        return self.samples[-1][0] - start

    def figure_seen(self) -> bool:
        return any(r.view != "none" for _, r in self.samples)


TOUCHPAD = Pad(buttons=("touchpad",))
FORWARD = Pad(left=(0.0, -1.0))


def read_tilt(observation: Observation) -> str:
    """Read tilt from a confident, unobstructed figure, without moving the camera.

    A low figure with a smooth upper picture indicates a view into the sky. Size
    alone cannot distinguish that from a normal close view. A figure high in the
    frame is seen from above. Missing and riding figures remain unknown.
    """
    reading = read_observation(observation)
    if reading.view not in NAMED and reading.reason != "between-bands":
        return "unknown"
    frame = observation.frame
    if hasattr(frame, "shape") and len(frame.shape) == 3 and frame.shape[2] == 3:
        h = frame.shape[0]
        if reading.feet >= 0.85 and 0.23 <= reading.height <= 0.56:
            gray = cv2.cvtColor(frame[: int(h * 0.65)], cv2.COLOR_RGB2GRAY)
            edges = cv2.Canny(gray, 30, 80) > 0
            if edges[: int(h * 0.50)].mean() < 0.008 and edges.mean() < 0.018:
                return "sky"
    if reading.view in NAMED:
        return "level"
    if 0.23 <= reading.height <= 0.65 and reading.feet < 0.66:
        return "ground"
    return "unknown"


def startup_plan(observation: Observation, *, view: bool = True):
    """Only schedule corrections supported by the current picture."""
    from .head import SkillCall

    tilt = read_tilt(observation)
    # Level first: view bands are calibrated on a level picture, not on the sky.
    if tilt in {"sky", "ground"}:
        return (SkillCall("level_camera", {}),)
    reading = read_observation(observation)
    if view and reading.view in {"near", "middle"}:
        return (SkillCall("set_far_view", {}),)
    return ()


class StartupCamera:
    """Observe the opening, then run only the camera corrections it needs."""

    name = "start_camera"
    parameters: ClassVar = {"view": ("on", "off")}
    prompt = "Read the opening camera before choosing a correction. Used at session startup."
    uninterruptible: ClassVar = True
    LIMIT = 42.0
    READ_LIMIT = 2.0

    def __init__(self, args: dict):
        if not isinstance(args, dict) or set(args) - self.parameters.keys():
            raise ValueError("start_camera accepts only view")
        if args.get("view", "on") not in self.parameters["view"]:
            raise ValueError("view must be on or off")
        self.view = args.get("view", "on") == "on"
        self.started = self.previous = self.read_started = self.last_stamp = None
        self.samples = []
        self.child = None
        self.planned = []
        self.finished = None

    def stop(self, reason="interrupted") -> SkillResult:
        if self.child is not None:
            self.child.stop(reason)
        self.finished = SkillResult(status="failed", reason=reason)
        return self.finished

    def step(self, observation: Observation) -> SkillResult:
        if self.finished is not None:
            return self.finished
        now = observation.time
        if not math.isfinite(now) or (self.previous is not None and now < self.previous):
            return self.stop("invalid-clock")
        self.previous = now
        if self.started is None:
            self.started = self.read_started = now
        if now - self.started >= self.LIMIT:
            return self.stop("time-limit")
        if self.child is not None:
            if observation.hud is None or observation.hud.screen != "game":
                return self.stop(
                    "hud-unread" if observation.hud is None else f"screen-{observation.hud.screen}"
                )
            if player_mode(observation) != "foot" and not observation.reading.corrupt:
                return self.stop("not-on-foot")
            result = self.child.step(observation)
            if result.status == "failed":
                return self.stop(f"{self.child.name}: {result.reason}")
            if result.status == "running":
                return result
            self.child = None
            self.samples.clear()
            self.read_started = now
            self.last_stamp = observation.objects_time
            return SkillResult()
        safe = (
            observation.hud is not None
            and observation.hud.screen == "game"
            and not observation.reading.corrupt
            and player_mode(observation) == "foot"
        )
        stamp = observation.objects_time
        fresh = stamp is not None and math.isfinite(stamp) and 0 <= now - stamp <= 0.6
        if safe and fresh and stamp != self.last_stamp:
            self.last_stamp = stamp
            plan = startup_plan(observation, view=self.view)
            signal = (read_tilt(observation), read_observation(observation).view, plan)
            self.samples.append((stamp, signal))
            self.samples = [sample for sample in self.samples if sample[0] >= stamp - 1.0]
            if len(self.samples) >= 3 and stamp - self.samples[0][0] >= 0.5:
                agreed = all(sample[1] == signal for sample in self.samples)
                if agreed and signal[0] != "unknown":
                    if not plan or plan[0].name in self.planned:
                        self.finished = SkillResult(status="done")
                        return self.finished
                    call = plan[0]
                    from .level import LevelCamera

                    self.child = LevelCamera({}) if call.name == "level_camera" else SetFarView({})
                    self.planned.append(call.name)
                    return SkillResult()
        if now - self.read_started >= self.READ_LIMIT:
            self.finished = SkillResult(status="done", reason="view-unknown")
            return self.finished
        return SkillResult()


class SetFarView:
    """Press the touchpad until the figure stands in the far view, steady.

    Far and steady for half a second: done. A named view that is not the far one: a press. No
    figure for a second and a half: a press as well, because that is first person or a hidden
    figure and the skill cannot tell them apart and need not. After each press the picture settles
    for 1.5 s; if no figure is then seen in a readable size, one short step forward swings the
    camera behind it before the skill reads again. It presses only on the game's screen, only
    after the mode has read foot for a second, and never with a vehicle under the figure.
    """

    name = "set_far_view"
    parameters: ClassVar = {"duration": (8.0, 40.0, 30.0)}
    prompt = (
        "Press the touchpad until the camera is in the far view behind the figure, on foot only. "
        "Fails when no view shows a figure, the screen is not the game, or the figure rides a vehicle."
    )
    # An opening that was cut in half would leave the camera in some other view.
    uninterruptible: ClassVar = True

    PULSE = 0.1  # a press, as a person's is
    SETTLE = 1.5  # the picture after a press; the camera took more than a second in the recordings
    STEP = 0.4  # left stick forward, as a person takes a step
    AFTER_STEP = 1.0
    STEP_AFTER = 1.0  # readings that name nothing this long: one step
    HIDDEN = 1.5  # no figure this long: first person, or a figure hidden
    UNREADABLE = 3.0  # a figure seen but never read this long: given up
    FOOT_FOR = 1.0  # the minimap reader holds a wrong class for up to 0.83 s
    UNSAFE_LIMIT = 4.0
    MAX_AGE = 0.6  # of the detections, against the tick that reads them
    STALL_LIMIT = 2.0  # no new detection this long: nothing to read
    LATE = 0.3  # a tick later than this has not held the pad for all that time
    MAX_PRESSES = 5
    BLIND_PRESSES = 4  # presses that showed no figure at all end the skill

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
        self.seen_figure = False
        self.last_view = "unknown"

    def _finish(self, status, reason):
        self.terminal = SkillResult(status=status, reason=reason)
        return self.terminal

    def _fail(self, why):
        return self._finish("failed", f"{why}; last={self.last_view}; presses={self.presses}")

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
        self.watch.add(stamp, reading)
        self.seen_figure |= reading.view != "none"
        self.last_view = reading.view if reading.view in NAMED or reading.view == "none" else "unknown"
        return self._decide(now)

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

    def _decide(self, now) -> SkillResult:
        view = self.watch.view()
        if view == "far":
            return self._finish("done", f"far; presses={self.presses}")
        settled = now - self.foot_since >= self.FOOT_FOR
        if view is not None:
            return self._press(now, settled)
        # Nothing named. After a press, or with a figure in the picture that no band reads, one
        # step forward swings the camera behind it; at the start, no figure means first person.
        if (
            self.watch.lasted(self.STEP_AFTER)
            and self.step_allowed
            and (self.presses or self.watch.figure_seen())
        ):
            return self._step(now, settled)
        if self.watch.hidden() >= self.HIDDEN:
            if self.presses >= self.BLIND_PRESSES and not self.seen_figure:
                return self._fail("no-figure")
            return self._press(now, settled)
        if self.watch.span >= self.UNREADABLE:
            return self._fail("view-unknown")
        return SkillResult()

    def _press(self, now, settled) -> SkillResult:
        if self.presses >= self.MAX_PRESSES:
            return self._fail("five-presses")
        if not settled:
            return SkillResult()
        self.presses += 1
        self.step_allowed = True
        self.pulse_until = now + self.PULSE
        self.watch.reset()
        return SkillResult(pad=TOUCHPAD)

    def _step(self, now, settled) -> SkillResult:
        if not settled:
            return SkillResult()
        self.steps += 1
        self.step_allowed = False
        self.step_until = now + self.STEP
        self.watch.reset()
        return SkillResult(pad=FORWARD)
