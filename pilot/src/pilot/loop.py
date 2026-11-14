"""Frame-driven runtime with bounded controller leases and explicit cleanup."""

from __future__ import annotations

import json
import signal
import sys
import time
from collections import Counter, deque
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

import numpy as np

from .bridge import Bridge
from .contract import HUD_RECT, Command, Pad, Reading
from .drive import DriveConfig, Driver
from .gps import Reader as GPSReader
from .gps import Speedometer
from .minimap import block_lines, read
from .motion import map_motion, motion_state

RECORDINGS = Path(__file__).resolve().parents[3] / "recordings"
# States in which drive.Driver has given the car up.
END_STATES = ("route-gone", "failed-recovery", "dead-or-held", "map-unreadable")


class Pipeline:
    """Shared live/replay interpretation, using frame time for motion and driving."""

    PAINTED_SECONDS = 1.5
    PAINTED_FORGET = 3.0

    def __init__(self, *, reader=read, motion=map_motion, driver=None, gps_reader=None):
        self.reader = reader
        self.motion = motion
        self.driver = Driver() if driver is None else driver
        cfg = getattr(self.driver, "config", DriveConfig())
        self.gps_reader = GPSReader(cfg.gps_interval) if gps_reader is None else gps_reader
        self.speedometer = Speedometer(
            cfg.gps_window, cfg.gps_stale, cfg.gps_max_speed, cfg.gps_tolerance, cfg.gps_acceleration
        )
        self.history: deque[tuple[float, np.ndarray, bool]] = deque()
        self.steps: tuple[frozenset, float, float] | None = None  # block borders with a step, since, last

    def close(self):
        close = getattr(self.gps_reader, "close", None)
        if close is not None:
            close()

    def _painted(self, crop: np.ndarray, frame_time: float) -> bool:
        """Whether the block steps of a map called damaged are the edges of its painted roads.

        A car that stands, or drives along a straight street, keeps the edge of a broad road on a block
        border of the codec, and the reader calls the clean map damaged for as long: on 14 November the
        car stood for a minute behind another with nobody driving (20261114-021738 from 352 s), and
        forty seconds of 20261114-015901. Damage of the codec comes and goes with the pictures. Steps
        that stay on the same borders for a second and a half of fresh pictures are taken as painted.
        """
        lines = block_lines(crop)
        held = self.steps
        if held is None or not lines <= held[0] or not 0 <= frame_time - held[2] <= self.PAINTED_FORGET:
            self.steps = (lines, frame_time, frame_time)
            return False
        self.steps = (held[0], held[1], frame_time)
        return frame_time - held[1] >= self.PAINTED_SECONDS

    def _motion(self, previous: np.ndarray, crop: np.ndarray, clean: bool) -> float | None:
        if clean and self.motion is map_motion:
            return map_motion(previous, crop, painted=True)
        return self.motion(previous, crop)

    def step(
        self, crop: np.ndarray, frame_time: float, feedback: bool = True
    ) -> tuple[Reading, bool | None, Command]:
        """With `feedback` off the driver is not told whether the map moves: while a human drives,
        its own commands move nothing, and it would take every red light for being stuck."""
        reading = self.reader(crop)
        if reading.corrupt and self.reader is read and self._painted(crop, frame_time):
            reading = read(crop, painted=True)
        # The measure of motion has the block detector's first word only, which takes a broad road's
        # edge for damage where the reader, looking further, does not: on 14 November, 03:05, the car
        # pushed against a lorry for 23 s with a clean map and no word on whether it moved
        # (20261114-030418). Two pictures the reader called clean are measured without that check.
        clean = self.reader is read and not reading.corrupt
        moving = None
        if self.history and frame_time <= self.history[-1][0]:
            self.history.clear()
        while self.history and self.history[0][0] < frame_time - 1.2:
            self.history.popleft()
        if self.history and frame_time - self.history[0][0] >= 0.15:
            _previous_time, previous, was_clean = min(
                self.history, key=lambda item: abs(frame_time - item[0] - 0.2)
            )
            moving = motion_state(self._motion(previous, crop, clean and was_clean))
            if moving is not True and frame_time - self.history[0][0] >= 0.8:
                moving = motion_state(self._motion(self.history[0][1], crop, clean and self.history[0][2]))
        self.history.append((frame_time, crop.copy(), clean))
        result = self.gps_reader.poll(crop, frame_time)
        sample_time, fix = result if result is not None else (frame_time, None)
        if reading.minimap != "tilted":
            self.speedometer.reset()
            fix = None
        speed = self.speedometer.update(frame_time, fix, sampled_at=sample_time)
        fresh = (
            self.speedometer.time is not None
            and 0 <= frame_time - self.speedometer.time <= self.speedometer.stale
        )
        current = self.speedometer.fix if fresh else None
        reading = replace(
            reading,
            gps_distance=None if current is None else current.distance,
            gps_arrow=None if current is None else current.arrow,
            gps_speed=speed,
            gps_time=self.speedometer.time if fresh else None,
        )
        return (
            reading,
            moving,
            self.driver.step(reading, frame_time, moving if feedback else None, speed=speed),
        )


def log_row(
    t,
    frame_id,
    frame_age,
    frame_time,
    reading,
    moving,
    command,
    sent=False,
    status=None,
    *,
    requested_pad=None,
    sent_pad=None,
):
    return {
        "t": t,
        "frame_id": frame_id,
        "frame_age": frame_age,
        "time": frame_time,
        "reading": None if reading is None else asdict(reading),
        "moving": moving,
        "gps_distance": None if reading is None else reading.gps_distance,
        "gps_arrow": None if reading is None else reading.gps_arrow,
        "gps_speed": None if reading is None else reading.gps_speed,
        "gps_time": None if reading is None else reading.gps_time,
        "command": None if command is None else asdict(command),
        "requested_pad": None if requested_pad is None else asdict(requested_pad),
        "sent_pad": None if sent_pad is None else asdict(sent_pad),
        "sent": sent,
        "status": status,
    }


@dataclass
class Summary:
    ticks: int = 0
    elapsed: float = 0.0
    states: Counter = field(default_factory=Counter)
    corrupt: int = 0
    conflicts: int = 0
    ended: str | None = None  # the driver state that ended the run, None when time or a signal did

    def add(self, reading, command):
        self.ticks += 1
        if reading is not None:
            self.corrupt += int(reading.corrupt)
        if command is not None:
            self.states[command.state] += 1

    def __str__(self):
        rate = self.ticks / self.elapsed if self.elapsed > 0 else 0
        return (
            f"ticks={self.ticks} rate={rate:.1f}/s states={dict(self.states)} "
            f"corrupt={self.corrupt} 409={self.conflicts} ended={self.ended}"
        )


class RuntimeInterruptedError(BaseException):
    """A signal to stop. Not an Exception: the readers and skills on a tick's way catch Exception,
    since a damaged picture may throw anything, and a signal raised while one of them ran was caught
    there. On 13 November, 00:36, a session asked to stop played on until it was asked again."""


class ControllerRuntime:
    """The same freshness, lease, conflict and release rules for every local skill."""

    # The bridge lets a pad go 250 ms after it was sent (contract.Pad.payload). A tick that takes
    # longer than that, with a text reading in it or a late frame before it, used to turn one press
    # into two at the console: the button came up by itself and went down again with the next pad.
    # On 13 November that took a waypoint away that had just been set (the cross in the legend) and
    # made two jumps of one (Square in the walk's guard). So a button that was down in the last pad
    # and has been let go by the bridge since is not pressed again until the skill itself has let
    # go of it once: a press that was asked for once reaches the console once, cut short at worst.
    # Sticks and triggers are states and not presses, and are sent as asked. The gap that counts as
    # a lapse is under the bridge's own 250 ms, since a press cut short costs nothing and a second
    # press does.
    LAPSE = 0.2

    def __init__(self, bridge, *, shadow=False, clock=time.monotonic, raw=False):
        from .profile import active

        self.profile = active()
        # The calibration measures the console itself, dead zones included: its pads leave as asked.
        self.raw = raw
        self.requested_pad = None
        self.sent_pad = None
        self.bridge, self.shadow, self.clock = bridge, shadow, clock
        self.last_fresh = clock()
        self.last_id = None
        self.frozen = False
        self.blocked_until = None
        self.conflicts = 0
        self.sent_at = None
        self.down = frozenset()
        self.withheld = frozenset()
        self.cut = 0  # presses that were cut short instead of being pressed twice

    def _once(self, pad):
        """The pad with every button taken out that the bridge has let go of in the middle of its press."""
        now = self.clock()
        asked = frozenset(pad.buttons)
        if self.profile.sprint_held:
            asked -= {self.profile.sprint}  # held for as long as the figure runs: a state, not a press
        withheld = self.withheld & asked  # let go of by the skill: free again
        if self.sent_at is not None and now - self.sent_at > self.LAPSE:
            lapsed = self.down & asked
            self.cut += len(lapsed - withheld)
            withheld |= lapsed
        self.withheld = withheld
        if withheld:
            pad = replace(pad, buttons=tuple(button for button in pad.buttons if button not in withheld))
        self.sent_at, self.down = now, asked - withheld
        return pad

    def observe(self, frame, received):
        fresh = frame is not None and frame.id != self.last_id and 0 <= frame.age < 0.3
        if frame is not None:
            self.last_id = frame.id
        if fresh:
            self.last_fresh = received
            self.frozen = False
        return fresh

    def send(self, command=None):
        status = self.bridge.pad(command)
        self.conflicts += int(status == 409)
        return status

    def tick(self, command: Command | Pad | None, *, fresh: bool, received: float):
        self.requested_pad = Pad.from_command(command) if isinstance(command, Command) else command
        self.sent_pad = None
        sent, status = False, None
        if not self.shadow:
            if self.blocked_until is not None:
                if received >= self.blocked_until:
                    status = self.send()
                    self.blocked_until = self.clock() + 1 if status == 409 else None
                    self.frozen = not fresh
            elif received - self.last_fresh >= 0.3 and not self.frozen:
                status = self.send()
                self.frozen = True
                # Let go of in the middle of its press, as after a lapse: not pressed again until the
                # skill has let go of it once.
                self.withheld = self.withheld | self.down
                self.down = frozenset()
            elif fresh:
                self.sent_pad = self.requested_pad
                if self.sent_pad is not None and not self.raw:
                    self.sent_pad = self._once(self.profile.shape(self.sent_pad))
                elif self.sent_pad is None:
                    self.down = self.withheld = frozenset()
                status = self.send(self.sent_pad)
                sent = status != 409
                if not sent:
                    # The bridge refused the pad: nothing of it is down.
                    self.down = frozenset()
            if status == 409:
                self.blocked_until = self.clock() + 1
        return sent, status

    def release(self):
        self.requested_pad = self.sent_pad = None
        if not self.shadow:
            self.send()


def cleanup_runtime(runtime, *, recording, pipeline, logs=()):
    """Release before stopping our recorder, even when another cleanup step fails."""
    active_error = sys.exception()
    errors = []
    actions = [runtime.release]
    if recording:
        actions.append(runtime.bridge.record_stop)
    actions.extend(log.close for log in logs if log is not None)
    if getattr(pipeline, "close", None) is not None:
        actions.append(pipeline.close)
    for action in actions:
        for _ in range(2):
            try:
                action()
            except RuntimeInterruptedError as exc:
                # A second signal cut the step short, the release of the pad it may be: once more.
                errors.append(exc)
                continue
            except Exception as exc:
                errors.append(exc)
            break
    if errors:
        if active_error is None:
            raise errors[0]
        for error in errors:
            print(f"Cleanup failed: {error}", file=sys.stderr)


@contextmanager
def interrupt_handlers():
    def stop(signum, frame):
        raise RuntimeInterruptedError(signal.Signals(signum).name)

    previous = {}
    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous[signum] = signal.signal(signum, stop)
        yield
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def run_drive(
    bridge: Bridge,
    *,
    seconds: float | None = None,
    shadow: bool = False,
    record: bool = True,
    record_dir: Path = RECORDINGS,
    pipeline: Pipeline | None = None,
    config: dict | None = None,
    clock=time.monotonic,
    sleep=time.sleep,
) -> Summary:
    pipeline = Pipeline() if pipeline is None else pipeline
    summary = Summary()
    log = None
    started = clock()
    first_tick = None
    recording = False
    runtime = ControllerRuntime(bridge, shadow=shadow, clock=clock)

    with interrupt_handlers():
        try:
            if record:
                destination = bridge.record_start(record_dir, shadow=shadow)
                recording = True
                log = (destination / "pilot.jsonl").open("x")
                if config is not None:
                    (destination / "pilot-config.json").write_text(json.dumps(config, indent=2) + "\n")
            started = runtime.last_fresh = clock()
            while seconds is None or clock() - started < seconds:
                tick = clock()
                if first_tick is None:
                    first_tick = tick
                frame = bridge.frame(HUD_RECT, after=runtime.last_id)
                received = clock()
                reading = moving = command = frame_time = None
                sent, status = False, None
                fresh = runtime.observe(frame, received)
                if frame is not None:
                    frame_time = received - frame.age
                if fresh:
                    reading, moving, command = pipeline.step(frame.rgb, frame_time, feedback=not shadow)
                sent, status = runtime.tick(command, fresh=fresh, received=received)
                summary.conflicts = runtime.conflicts

                summary.add(reading, command)
                if log is not None:
                    row = log_row(
                        tick - first_tick,
                        None if frame is None else frame.id,
                        None if frame is None else frame.age,
                        frame_time,
                        reading,
                        moving,
                        command,
                        sent,
                        status,
                        requested_pad=runtime.requested_pad,
                        sent_pad=runtime.sent_pad,
                    )
                    log.write(json.dumps(row) + "\n")
                    log.flush()
                # the driver has given up and let go of the pedals: what comes next is the head's call
                if not shadow and command is not None and command.state in END_STATES:
                    if command.throttle == command.brake == 0:
                        summary.ended = command.state
                        break
                sleep(max(0, tick + 1 / 30 - clock()))
        except RuntimeInterruptedError:
            pass
        finally:
            try:
                cleanup_runtime(runtime, recording=recording, pipeline=pipeline, logs=(log,))
            finally:
                summary.conflicts = runtime.conflicts
                summary.elapsed = clock() - started
                print(summary)
    return summary
