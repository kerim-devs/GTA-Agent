"""Frame-driven runtime with bounded controller leases and explicit cleanup."""

from __future__ import annotations

import json
import signal
import sys
import time
from collections import Counter, deque
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from .bridge import Bridge
from .contract import HUD_RECT, Command, Reading
from .drive import Driver
from .minimap import read
from .motion import MOVING_PX, map_motion

RECORDINGS = Path(__file__).resolve().parents[3] / "recordings"
END_STATES = ("route-gone", "failed-recovery")  # states in which drive.Driver has given the car up


class Pipeline:
    """Shared live/replay interpretation, using frame time for motion and driving."""

    def __init__(self, *, reader=read, motion=map_motion, driver=None):
        self.reader = reader
        self.motion = motion
        self.driver = Driver() if driver is None else driver
        self.history: deque[tuple[float, np.ndarray]] = deque()

    def step(
        self, crop: np.ndarray, frame_time: float, feedback: bool = True
    ) -> tuple[Reading, bool | None, Command]:
        """With `feedback` off the driver is not told whether the map moves: while a human drives,
        its own commands move nothing, and it would take every red light for being stuck."""
        reading = self.reader(crop)
        moving = None
        if self.history and frame_time <= self.history[-1][0]:
            self.history.clear()
        while self.history and self.history[0][0] < frame_time - 0.4:
            self.history.popleft()
        if self.history and frame_time - self.history[0][0] >= 0.15:
            _, previous = min(self.history, key=lambda item: abs(frame_time - item[0] - 0.2))
            displacement = self.motion(previous, crop)
            moving = None if displacement is None else bool(displacement > MOVING_PX)
        self.history.append((frame_time, crop.copy()))
        return reading, moving, self.driver.step(reading, frame_time, moving if feedback else None)


def log_row(t, frame_id, frame_age, frame_time, reading, moving, command, sent=False, status=None):
    return {
        "t": t,
        "frame_id": frame_id,
        "frame_age": frame_age,
        "time": frame_time,
        "reading": None if reading is None else asdict(reading),
        "moving": moving,
        "command": None if command is None else asdict(command),
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
    last_fresh = started
    last_id = None
    frozen = False
    blocked_until = None
    recording = False

    def send(command=None):
        status = bridge.pad(command)
        summary.conflicts += int(status == 409)
        return status

    with interrupt_handlers():
        try:
            if record:
                destination = bridge.record_start(record_dir, shadow=shadow)
                recording = True
                log = (destination / "pilot.jsonl").open("x")
                if config is not None:
                    (destination / "pilot-config.json").write_text(json.dumps(config, indent=2) + "\n")
            started = last_fresh = clock()
            while seconds is None or clock() - started < seconds:
                tick = clock()
                if first_tick is None:
                    first_tick = tick
                frame = bridge.frame(HUD_RECT, after=last_id)
                received = clock()
                reading = moving = command = frame_time = None
                sent, status = False, None
                fresh = frame is not None and frame.id != last_id and frame.age < 0.3
                if frame is not None:
                    frame_time = received - frame.age
                    last_id = frame.id
                if fresh:
                    last_fresh = received
                    frozen = False
                    reading, moving, command = pipeline.step(frame.rgb, frame_time, feedback=not shadow)

                if not shadow:
                    if blocked_until is not None:
                        if received >= blocked_until:
                            status = send()
                            blocked_until = clock() + 1 if status == 409 else None
                            frozen = not fresh
                    elif received - last_fresh >= 0.3 and not frozen:
                        status = send()
                        frozen = True
                    elif fresh:
                        status = send(command)
                        sent = status != 409
                    if status == 409:
                        blocked_until = clock() + 1

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
            active_error = sys.exception()
            cleanup_errors = []
            try:
                if not shadow:
                    send()
            except Exception as exc:
                cleanup_errors.append(exc)
            try:
                if recording:  # a recording someone else started is not ours to stop
                    bridge.record_stop()
            except Exception as exc:
                cleanup_errors.append(exc)
            finally:
                if log is not None:
                    log.close()
                summary.elapsed = clock() - started
                print(summary)
            if cleanup_errors:
                if active_error is None:
                    raise cleanup_errors[0]
                for error in cleanup_errors:
                    print(f"Cleanup failed: {error}", file=sys.stderr)
    return summary
