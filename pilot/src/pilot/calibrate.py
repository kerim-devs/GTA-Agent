"""Bounded, recorded measurements through the play controller runtime."""

from __future__ import annotations

import json
import math
import statistics
import threading
import time
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

from . import hud
from .conductor import minimap_crop
from .contract import NEUTRAL_PAD, Pad
from .head import HeadRequest
from .loop import ControllerRuntime, cleanup_runtime, interrupt_handlers
from .minimap import read as read_minimap
from .motion import map_motion, motion_state
from .scene import SceneText
from .waypoint import map_shift

CHECKS = ("delay", "camera", "walk", "press", "map", "wheel", "phone", "car", "detector", "head")
RECORDINGS = Path(__file__).resolve().parents[3] / "lab" / "calibrate"
TICK = 1 / 30
LIMIT = 240.0
SETTLE = 1.2
PULSE = 0.6
BUTTONS = {"options", "circle", "cross", "l1", "up", "triangle"}


class CheckAbortedError(Exception):
    """A measurement failed; a subsequent check can still run."""


class SessionStoppedError(Exception):
    """A deadline or controller takeover ends all active checks."""


def selection(only=(), skip=(), *, car=False):
    """Keep the canonical order, including with repeated/comma-separated flags."""
    only = {part for item in only for part in item.split(",") if part}
    skip = {part for item in skip for part in item.split(",") if part}
    unknown = (only | skip) - set(CHECKS)
    if unknown:
        raise ValueError(f"unknown checks: {', '.join(sorted(unknown))}")
    return [
        name for name in CHECKS if (not only or name in only) and name not in skip and (name != "car" or car)
    ]


def picture_shift(before, after):
    """Image pixels, not degrees: a field of view is not known here."""

    def plane(rgb):
        return cv2.resize(cv2.cvtColor(rgb[80:540, 180:1100], cv2.COLOR_RGB2GRAY), (320, 160)).astype(
            np.float32
        )

    shift, quality = cv2.phaseCorrelate(plane(before), plane(after))
    return (float(shift[0] * 920 / 320), float(quality))


class Session:
    def __init__(self, bridge, *, shadow, clock, sleep, detector_factory, head):
        self.bridge, self.clock, self.sleep = bridge, clock, sleep
        self.runtime = ControllerRuntime(bridge, shadow=shadow, clock=clock)
        self.deadline = clock() + LIMIT
        self.started = clock()
        self.shadow = shadow
        self.detector_factory, self.head = detector_factory, head
        self.detector = None
        self.frame = None
        self.screen = "unknown"
        self.series = []
        self.commands = False
        self.last_sample = None
        self.cleanup_pending = []

    def close(self):
        # Reader.close joins its inference thread. Do not let a stuck inference
        # extend the session indefinitely after controller/recording cleanup.
        for name, resource in (("head", self.head), ("detector", self.detector)):
            if resource is not None and hasattr(resource, "close"):
                worker = threading.Thread(target=resource.close, daemon=True)
                worker.start()
                worker.join(timeout=max(0, min(0.1, self.deadline - self.clock())))
                if worker.is_alive():
                    self.cleanup_pending.append(name)

    def sample(self, pad=None, *, screens=None, release_on=None):
        if self.last_sample is not None:
            self.sleep(max(0, self.last_sample + TICK - self.clock()))
        if self.clock() >= self.deadline:
            raise SessionStoppedError("four-minute session deadline")
        frame = self.bridge.frame(None, after=self.runtime.last_id)
        now = self.clock()
        fresh = self.runtime.observe(frame, now)
        self.last_sample = now
        row = {"t": now - self.started, "frame_id": None if frame is None else frame.id, "fresh": fresh}
        self.series.append(row)
        if fresh:
            self.frame = frame
            self.screen = hud.read(frame.rgb, text=SceneText()).screen
        row["screen"] = self.screen
        if self.clock() >= self.deadline:
            raise SessionStoppedError("four-minute session deadline")
        if not fresh:
            if self.commands:
                self.runtime.tick(NEUTRAL_PAD, fresh=False, received=now)
            raise CheckAbortedError("missing or stale picture")
        if screens is not None and self.screen not in screens:
            raise CheckAbortedError(f"unexpected screen: {self.screen}")
        if pad is not None:
            if self.screen == release_on:
                pad = NEUTRAL_PAD
            if set(pad.buttons) - BUTTONS or pad.r2 or pad.l2:
                raise ValueError("calibration input outside the allowlist")
            if "cross" in pad.buttons and self.screen != "pause":
                raise CheckAbortedError("Cross requires a fresh pause screen")
            sent, status = self.runtime.tick(pad, fresh=True, received=now)
            self.commands |= not self.shadow
            row.update(pad=pad.payload(), sent=sent, status=status)
            if status == 409:
                raise SessionStoppedError("person on the controller (409)")
            if status is not None and status != 200:
                raise SessionStoppedError(f"controller returned {status}")
        return row

    def neutral(self):
        if self.commands:
            self.runtime.release()

    def hold(self, pad, seconds, *, screens=("game",)):
        start = None
        for _ in range(math.ceil(seconds / TICK - 1e-8)):
            self.sample(pad, screens=screens)
            if start is None:
                start = self.clock()
        self.sleep(TICK)
        return self.clock() - start

    def wait(self, seconds, *, screens=("game",)):
        self.hold(NEUTRAL_PAD, seconds, screens=screens)

    def transition(self, button, target, *, origin, ticks=4, wait=SETTLE):
        start = self.clock()
        for _ in range(ticks):
            if self.screen == target:
                break
            self.sample(Pad(buttons=(button,)), screens=(origin, target), release_on=target)
        self.sleep(TICK)
        self.neutral()
        end = self.clock() + wait
        while self.clock() < end:
            self.sample(NEUTRAL_PAD, screens=(origin, target))
            if self.screen == target:
                return self.clock() - start
        return None

    def back_out(self):
        # No guesses for death, loading, a wheel or an unknown overlay.
        for _ in range(3):
            if self.screen not in {"pause", "map", "phone"}:
                return
            origin = self.screen
            target = "pause" if origin == "map" else "game"
            try:
                self.transition("circle", target, origin=origin)
            except CheckAbortedError:
                return

    def read_side(self, name):
        start = self.clock()
        before = self.frame.rgb.copy()
        while self.clock() - start < (5 if name == "detector" else PULSE):
            row = self.sample()
            row["minimap"] = asdict(read_minimap(minimap_crop(self.frame.rgb)))
            if name in {"delay", "camera"}:
                row["displacement_px"], row["correlation"] = picture_shift(before, self.frame.rgb)
            elif name == "walk":
                row["displacement_px"] = map_motion(minimap_crop(before), minimap_crop(self.frame.rgb))
            elif name == "map" and self.screen == "map":
                row["shift_px"] = map_shift(before, self.frame.rgb)
        return {"samples": len(self.series), "screen": self.screen}

    def delay(self):
        delays = []
        for direction, duration in ((1, 0.2), (-1, 0.4), (1, 0.2)):
            before = self.frame.rgb.copy()
            start = None
            onset = None
            pulse_end = None
            while start is None or self.clock() < pulse_end + SETTLE:
                active = start is None or self.clock() < pulse_end - TICK / 2
                row = self.sample(
                    Pad(right=(0.65 * direction, 0)) if active else NEUTRAL_PAD, screens=("game",)
                )
                if start is None:
                    start = self.clock()
                    pulse_end = start + duration
                dx, quality = picture_shift(before, self.frame.rgb)
                row.update(displacement_px=dx, correlation=quality)
                if onset is None and abs(dx) > 0.75 and quality > 0.3:
                    onset = self.clock() - start
            delays.append(onset)
        if any(value is None for value in delays):
            raise CheckAbortedError("picture did not move after a camera pulse")
        return {"seconds": statistics.median(delays), "trials_seconds": delays}

    def camera(self):
        values = []
        for index, strength in enumerate((0.1, 0.15, 0.2, 0.3, 0.45, 0.65, 1.0)):
            before = self.frame.rgb.copy()
            direction = 1 if index % 2 == 0 else -1
            duration = self.hold(Pad(right=(strength * direction, 0)), PULSE)
            self.neutral()
            self.wait(SETTLE)
            dx, quality = picture_shift(before, self.frame.rgb)
            value = {
                "stick": strength,
                "pulse_seconds": duration,
                "displacement_px": dx,
                "correlation": quality,
                "pixels_per_second": abs(dx) / duration,
                "moving": abs(dx) > 2 and quality > 0.3,
            }
            values.append(value)
            self.series[-1]["camera"] = value
        moving = [v["stick"] for v in values if v["moving"]]
        if not moving:
            raise CheckAbortedError("camera never moved")
        threshold = min(moving)
        lower = max((v["stick"] for v in values if not v["moving"] and v["stick"] < threshold), default=0)
        return {
            "minimum_stick": threshold,
            "deadzone_interval": [lower, threshold],
            "samples": values,
            "units": "image pixels per second",
        }

    def walk(self):
        values = []
        for strength in (0.2, 0.3, 0.45, 0.65, 1.0):
            start = None
            history = []
            distances = []
            while start is None or self.clock() < start + PULSE + SETTLE:
                active = start is None or self.clock() < start + PULSE - TICK / 2
                row = self.sample(Pad(left=(0, -strength)) if active else NEUTRAL_PAD, screens=("game",))
                now = self.clock()
                if start is None:
                    start = now
                crop = minimap_crop(self.frame.rgb)
                history.append((now, self.frame.id, crop))
                while len(history) > 1 and now - history[1][0] >= 0.3 - 1e-8:
                    history.pop(0)
                if now - history[0][0] >= 0.3 - 1e-8:
                    distance = map_motion(history[0][2], crop)
                    row["motion"] = {
                        "from_frame": history[0][1],
                        "window_seconds": now - history[0][0],
                        "displacement_px": distance,
                    }
                    if distance is not None:
                        distances.append(distance)
            self.neutral()
            distance = max(distances, default=None)
            value = {
                "stick": strength,
                "displacement_px": distance,
                "window_seconds": 0.3,
                "moving": motion_state(distance),
            }
            values.append(value)
            self.series[-1]["walk"] = value
        if any(v["moving"] is None for v in values):
            raise CheckAbortedError("minimap movement unreadable at one or more stick strengths")
        moving = [v["stick"] for v in values if v["moving"]]
        if not moving:
            raise CheckAbortedError("minimap never showed walking")
        return {"minimum_stick": min(moving), "samples": values}

    def press(self):
        values = []
        for trial in range(2):
            for button, origin, target in (("options", "game", "pause"), ("circle", "pause", "game")):
                for ticks in range(1, 5):
                    elapsed = self.transition(button, target, origin=origin, ticks=ticks)
                    value = {
                        "trial": trial + 1,
                        "button": button,
                        "ticks": ticks,
                        "seconds": ticks * TICK,
                        "accepted": elapsed is not None,
                        "response_seconds": elapsed,
                    }
                    values.append(value)
                    self.series[-1]["press"] = value
                    if elapsed is not None:
                        break
                else:
                    raise CheckAbortedError(f"{button} did not open {target} in four ticks")
        return {
            "minimum_ticks": {
                button: max(v["ticks"] for v in values if v["button"] == button and v["accepted"])
                for button in ("options", "circle")
            },
            "tick_seconds": TICK,
            "trials": values,
        }

    def map(self):
        if self.transition("options", "pause", origin="game") is None:
            raise CheckAbortedError("pause did not open")
        if self.transition("cross", "map", origin="pause") is None:
            raise CheckAbortedError("map did not open")
        values = {}
        for name, stick in (("right", (0.65, 0)), ("down", (0, 0.65))):
            before = self.frame.rgb.copy()
            duration = self.hold(Pad(left=stick), PULSE, screens=("map",))
            self.neutral()
            self.wait(SETTLE, screens=("map",))
            shift = map_shift(before, self.frame.rgb)
            if shift is None:
                raise CheckAbortedError(f"map {name} shift unreadable")
            value = {
                "stick": 0.65,
                "pulse_seconds": duration,
                "shift_px": list(shift),
                "pixels_per_second": [v / duration for v in shift],
            }
            self.series[-1]["map"] = value
            values[name] = value
        self.back_out()
        if self.screen != "game":
            raise CheckAbortedError("map did not close")
        return values

    def wheel(self):
        seen = False
        start = self.clock()
        while self.clock() - start < PULSE + SETTLE:
            self.sample(Pad(buttons=("l1",)), screens=("game", "weapon_wheel"))
            seen |= self.screen == "weapon_wheel"
        self.neutral()
        self.wait(SETTLE, screens=("game", "weapon_wheel"))
        if not seen or self.screen != "game":
            raise CheckAbortedError("weapon wheel did not open and close")
        return {"while_held": "weapon_wheel", "after_release": self.screen}

    def phone(self):
        opened = self.transition("up", "phone", origin="game")
        if opened is None:
            raise CheckAbortedError("phone did not open")
        closed = self.transition("circle", "game", origin="phone")
        if closed is None:
            raise CheckAbortedError("phone did not close")
        return {"open_seconds": opened, "close_seconds": closed}

    def car(self):
        values = {}
        for name, target in (("enter", "tilted"), ("exit", "flat")):
            start = self.clock()
            self.hold(Pad(buttons=("triangle",)), 4 * TICK)
            self.neutral()
            stable = None
            first = None
            while self.clock() - start < 12:
                row = self.sample(NEUTRAL_PAD, screens=("game",))
                reading = read_minimap(minimap_crop(self.frame.rgb))
                row["minimap"] = asdict(reading)
                if reading.minimap == target and not reading.corrupt and reading.confidence >= 0.45:
                    if stable is None:
                        stable = self.clock()
                        first = stable - start
                    if self.clock() - stable >= 0.5 - 1e-8:
                        values[name] = {
                            "seconds": first,
                            "confirmed_seconds": self.clock() - start,
                            "stable_seconds": 0.5,
                        }
                        break
                else:
                    stable = None
            else:
                raise CheckAbortedError(f"minimap did not become stably {target}")
        return values

    def detector_check(self):
        self.detector = self.detector_factory()
        start = self.clock()
        stamps = set()
        loops = 0
        while self.clock() - start < 5 - 1e-8:
            row = self.sample()
            result = self.detector.poll(self.frame.rgb, self.clock())
            loops += 1
            if result is not None:
                stamp, detections = result
                stamps.add(stamp)
                row["detection"] = {
                    "frame_time": stamp - self.started,
                    "objects": [asdict(item) for item in detections],
                }
        elapsed = self.clock() - start
        return {
            "seconds": elapsed,
            "results": len(stamps),
            "results_per_second": len(stamps) / elapsed,
            "loop_per_second": loops / elapsed,
        }

    def head_check(self, destination):
        if self.head is None:
            return {"available": False}
        jpeg = destination / "head.jpg"
        cv2.imwrite(str(jpeg), cv2.cvtColor(self.frame.rgb, cv2.COLOR_RGB2BGR))
        request = HeadRequest(
            events=[],
            help="Describe the current picture; this is a passive latency measurement.",
            objective="Observe only",
            subtitle="",
            banner="",
            minimap=asdict(read_minimap(minimap_crop(self.frame.rgb))),
            last_skill=None,
            notebook="",
            jpeg_path=str(jpeg),
            hud={"screen": self.screen},
        )
        outcome = []

        def decide():
            try:
                response = self.head.decide(request)
                outcome.append((True, response, self.clock()))
            except Exception as error:
                outcome.append((False, str(error), self.clock()))

        start = self.clock()
        if hasattr(self.head, "timeout"):
            self.head.timeout = min(self.head.timeout, max(0.01, self.deadline - start))
        threading.Thread(target=decide, name="calibration-head", daemon=True).start()
        while not outcome:
            self.sample()
            if self.clock() - start >= 45:
                raise CheckAbortedError("head request exceeded 45 seconds")
        ok, response, finished = outcome[0]
        self.series.append(
            {
                "t": self.clock() - self.started,
                "head_started": start - self.started,
                "head_finished": finished - self.started,
                "ok": ok,
                "response": str(response),
            }
        )
        if not ok:
            raise CheckAbortedError(f"head failed: {response}")
        return {"seconds": finished - start, "request_count": 1}


def run_calibrate(
    bridge,
    *,
    only=(),
    skip=(),
    car=False,
    yes=False,
    shadow=False,
    record_dir=RECORDINGS,
    clock=time.monotonic,
    sleep=time.sleep,
    detector_factory=None,
    head=None,
    confirm=input,
    output=print,
):
    names = selection(only, skip, car=car)
    output(
        "Kalibrierung: Die Figur muss zu Fuß stillstehen, auf freier Fläche ohne Menschen. "
        "Kamera und Figur bewegen sich kurz; Menüs öffnen und schließen sich. "
        "Mit --car neben einem geparkten Auto stehen. "
        "Dauer meist etwa eine Minute, höchstens vier Minuten."
    )
    if not yes and not shadow and any(name not in {"detector", "head"} for name in names):
        confirm("Enter startet die Eingaben. ")
    if detector_factory is None:
        from .objects import Reader

        detector_factory = Reader
    session = Session(
        bridge, shadow=shadow, clock=clock, sleep=sleep, detector_factory=detector_factory, head=head
    )
    report = {"version": 1, "shadow": shadow, "limit_seconds": LIMIT, "tick_seconds": TICK, "checks": []}
    destination = None
    recording = False
    stop = None
    with interrupt_handlers():
        try:
            destination = bridge.record_start(Path(record_dir), shadow=shadow)
            destination.mkdir(parents=True, exist_ok=True)
            recording = True
            for name in names:
                item = {"name": name, "status": "skipped", "reason": "", "numbers": {}, "raw": []}
                report["checks"].append(item)
                session.series = item["raw"]
                if stop:
                    item["reason"] = stop
                    continue
                active = False
                try:
                    session.sample()
                    if name == "head" and head is None:
                        item["reason"] = "head disabled"
                        continue
                    if shadow:
                        item["numbers"] = (
                            session.detector_check()
                            if name == "detector"
                            else session.head_check(destination)
                            if name == "head"
                            else session.read_side(name)
                        )
                        item.update(status="ran", reason="shadow: readers only")
                        continue
                    if name not in {"detector", "head"}:
                        reading = read_minimap(minimap_crop(session.frame.rgb))
                        session.series[-1]["minimap"] = asdict(reading)
                        if (
                            session.screen != "game"
                            or reading.minimap != "flat"
                            or reading.corrupt
                            or reading.confidence < 0.45
                        ):
                            item["reason"] = (
                                f"requires a clear on-foot game picture; screen={session.screen}, "
                                f"minimap={reading.minimap}"
                            )
                            continue
                        active = True
                    method = (
                        session.detector_check
                        if name == "detector"
                        else session.head_check
                        if name == "head"
                        else getattr(session, name)
                    )
                    item["numbers"] = method(destination) if name == "head" else method()
                    item["status"] = "ran"
                except CheckAbortedError as error:
                    item.update(status="aborted", reason=str(error))
                    if active:
                        session.neutral()
                        session.back_out()
                finally:
                    if active:
                        session.neutral()
        except BaseException as error:
            stop = f"{type(error).__name__}: {error}"
            report["stop_reason"] = stop
            if report["checks"]:
                report["checks"][-1].update(status="aborted", reason=stop)
            done = {item["name"] for item in report["checks"]}
            for name in names:
                if name not in done:
                    report["checks"].append(
                        {"name": name, "status": "skipped", "reason": stop, "numbers": {}, "raw": []}
                    )
        finally:
            # A fully passive run must not write even a neutral controller state.
            session.runtime.shadow |= not session.commands
            cleanup_runtime(session.runtime, recording=recording, pipeline=session)
            report["cleanup_pending"] = session.cleanup_pending
            report["elapsed_seconds"] = clock() - session.started
            if destination is not None:
                (destination / "calibration.json").write_text(
                    json.dumps(report, indent=2, allow_nan=False) + "\n"
                )
            for item in report["checks"]:
                output(f"{item['name']}: {item['status']} {json.dumps(item['numbers'])} {item['reason']}")
    return report
