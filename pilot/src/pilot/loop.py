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
from .minimap import read
from .motion import map_motion, motion_state

RECORDINGS = Path(__file__).resolve().parents[3] / "recordings"
END_STATES = ("route-gone", "failed-recovery")  # states in which drive.Driver has given the car up


class Pipeline:
    """Shared live/replay interpretation, using frame time for motion and driving."""

    def __init__(self, *, reader=read, motion=map_motion, driver=None, gps_reader=None):
        self.reader = reader
        self.motion = motion
        self.driver = Driver() if driver is None else driver
        cfg = getattr(self.driver, "config", DriveConfig())
        self.gps_reader = GPSReader(cfg.gps_interval) if gps_reader is None else gps_reader
        self.speedometer = Speedometer(
            cfg.gps_window, cfg.gps_stale, cfg.gps_max_speed, cfg.gps_tolerance, cfg.gps_acceleration
        )
        self.history: deque[tuple[float, np.ndarray]] = deque()

    def close(self):
        close = getattr(self.gps_reader, "close", None)
        if close is not None:
            close()

    def step(
        self, crop: np.ndarray, frame_time: float, feedback: bool = True
    ) -> tuple[Reading, bool | None, Command]:
        """With `feedback` off the driver is not told whether the map moves: while a human drives,
        its own commands move nothing, and it would take every red light for being stuck."""
        reading = self.reader(crop)
        moving = None
        if self.history and frame_time <= self.history[-1][0]:
            self.history.clear()
        while self.history and self.history[0][0] < frame_time - 1.2:
            self.history.popleft()
        if self.history and frame_time - self.history[0][0] >= 0.15:
            _previous_time, previous = min(self.history, key=lambda item: abs(frame_time - item[0] - 0.2))
            displacement = self.motion(previous, crop)
            moving = motion_state(displacement)
            if moving is not True and frame_time - self.history[0][0] >= 0.8:
                moving = motion_state(self.motion(self.history[0][1], crop))
        self.history.append((frame_time, crop.copy()))
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


class RuntimeInterruptedError(Exception):
    pass


class ControllerRuntime:
    """The same freshness, lease, conflict and release rules for every local skill."""

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
            elif fresh:
                self.sent_pad = self.requested_pad
                if self.sent_pad is not None and not self.raw:
                    self.sent_pad = self.profile.shape(self.sent_pad)
                status = self.send(self.sent_pad)
                sent = status != 409
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
        try:
            action()
        except Exception as exc:
            errors.append(exc)
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
