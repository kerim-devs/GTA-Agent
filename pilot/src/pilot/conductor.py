"""Event-driven strategy around a local, frame-driven skill runner."""

from __future__ import annotations

import json
import math
import threading
import time
from concurrent.futures import Future
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import cv2

from .contract import FRAME_SIZE, HUD_RECT
from .head import HeadRequest, ScriptedHead, build_prompt, parse_response, response_data
from .loop import ControllerRuntime, Pipeline, RuntimeInterruptedError, cleanup_runtime, interrupt_handlers
from .scene import EventDetector, SceneText, TextReader
from .skills import Observation, SkillRunner

PLAY_RECORDINGS = Path.home() / "recordings" / "pilot"


def background(function, *args):
    """One daemon thread per bounded job; shutdown never waits for OCR or a head."""
    future = Future()

    def work():
        if not future.set_running_or_notify_cancel():
            return
        try:
            future.set_result(function(*args))
        except BaseException as exc:
            future.set_exception(exc)

    threading.Thread(target=work, daemon=True).start()
    return future


def minimap_crop(rgb):
    height, width = rgb.shape[:2]
    x, y, w, h = HUD_RECT
    sx, sy = width / FRAME_SIZE[0], height / FRAME_SIZE[1]
    crop = rgb[round(y * sy) : round((y + h) * sy), round(x * sx) : round((x + w) * sx)]
    return cv2.resize(crop, (w, h))


class Conductor:
    def __init__(
        self,
        directory: Path,
        *,
        head=None,
        notebook: Path | None = None,
        runner=None,
        detector=None,
        ocr=False,
        text_reader=None,
        quiet_seconds=60.0,
        ocr_interval=0.5,
        ocr_timeout=3.0,
        submit=background,
        clock=time.monotonic,
    ):
        for value in (quiet_seconds, ocr_interval, ocr_timeout):
            if not math.isfinite(value) or value <= 0:
                raise ValueError("conductor intervals must be positive and finite")
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.log = (self.directory / "head.jsonl").open("x")
        self.head = ScriptedHead() if head is None else head
        self.notebook = PLAY_RECORDINGS / "notebook.txt" if notebook is None else Path(notebook)
        self.runner = SkillRunner() if runner is None else runner
        self.detector = EventDetector() if detector is None else detector
        self.ocr, self.reader = ocr, text_reader
        self.quiet_seconds, self.ocr_interval, self.ocr_timeout = quiet_seconds, ocr_interval, ocr_timeout
        self.submit, self.clock = submit, clock
        self.text = SceneText()
        self.ocr_future = None
        self.ocr_started = None
        self.next_ocr = float("-inf")
        self.pending = [{"kind": "startup"}]
        self.epoch = 0
        self.future = None
        self.inflight = None
        self.request_count = 0
        self.last_request_time = None
        self.request_times = []
        self.closed = False

    def write(self, row):
        self.log.write(json.dumps(row, ensure_ascii=False) + "\n")
        self.log.flush()

    def _read_text(self, rgb):
        if self.reader is None:
            self.reader = TextReader()
        return self.reader.read(rgb)

    def _text(self, rgb, t, injected):
        if injected is not None:
            self.text = injected
        if not self.ocr:
            return
        if self.ocr_future is not None:
            if self.ocr_future.done():
                try:
                    self.text = self.ocr_future.result()
                except Exception as exc:
                    self.write({"type": "ocr_error", "t": t, "error": str(exc)})
                    raise RuntimeError("scene OCR failed") from exc
                self.ocr_future = None
            elif self.clock() - self.ocr_started >= self.ocr_timeout:
                self.write({"type": "ocr_error", "t": t, "error": "timeout"})
                raise TimeoutError("scene OCR exceeded its time limit")
        if self.ocr_future is None and t >= self.next_ocr:
            self.ocr_started = self.clock()
            self.ocr_future = self.submit(self._read_text, rgb.copy())
            self.next_ocr = t + self.ocr_interval

    def _finish_head(self, t):
        if self.future is None or not self.future.done():
            return
        request = self.inflight
        row = {
            **request["row"],
            "type": "response",
            "t": t,
            "duration": self.clock() - request["started"],
            "overtaken": request["epoch"] != self.epoch,
        }
        try:
            response = self.future.result()
            # Validate even third-party Head implementations before touching the runner.
            decision = parse_response(response_data(response))
            row.update(response_data(decision))
            if not row["overtaken"]:
                self.runner.replace(decision.plan)
                row["applied"] = True
                if decision.lesson:
                    self.notebook.parent.mkdir(parents=True, exist_ok=True)
                    with self.notebook.open("a") as notebook:
                        notebook.write(f"{datetime.now(UTC).isoformat()} {decision.lesson.strip()}\n")
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            self.write(row)
            self.future = self.inflight = None

    def _request(self, observation, rgb):
        self.request_count += 1
        stem = f"head-{self.request_count:04d}"
        jpeg = (self.directory / f"{stem}.jpg").resolve()
        if not cv2.imwrite(str(jpeg), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)):
            raise OSError("could not save head frame")
        notebook = self.notebook.read_text() if self.notebook.exists() else ""
        request = HeadRequest(
            list(self.pending),
            self.text.help,
            self.text.objective,
            self.text.subtitle,
            self.text.banner,
            asdict(observation.reading),
            self.runner.describe(),
            notebook,
            str(jpeg),
        )
        prompt_file = self.directory / f"{stem}.prompt.txt"
        prompt_file.write_text(build_prompt(request))
        row = {
            "type": "request",
            "id": self.request_count,
            "t": observation.time,
            "request": asdict(request),
            "frame_file": jpeg.name,
            "prompt_file": prompt_file.name,
            "plan": [],
            "sentence": None,
            "lesson": None,
            "duration": 0.0,
            "applied": False,
            "overtaken": False,
        }
        self.write(row)
        self.inflight = {"row": row, "epoch": self.epoch, "started": self.clock()}
        self.future = self.submit(self.head.decide, request)
        self.pending.clear()
        self.last_request_time = observation.time
        self.request_times.append(observation.time)

    def tick(self, observation: Observation, rgb, *, text=None, events=()):
        self._text(rgb, observation.time, text)
        detected = self.detector.update(observation.reading, observation.time, text=self.text)
        new_events = [asdict(event) for event in detected] + list(events)
        if new_events:
            self.epoch += 1
            self.pending.extend(new_events)
        self._finish_head(observation.time)
        result = self.runner.tick(observation)
        if self.runner.completed:
            self.epoch += 1
            self.pending.append({"kind": "skill_ended", "skill": self.runner.describe()})
        quiet = (
            self.last_request_time is None or observation.time - self.last_request_time >= self.quiet_seconds
        )
        if self.future is None and (self.pending or quiet):
            self._request(observation, rgb)
        return result

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.runner.stop()
        if self.future is not None:
            self.future.cancel()
            self.write(
                {
                    **self.inflight["row"],
                    "type": "response",
                    "duration": self.clock() - self.inflight["started"],
                    "overtaken": self.inflight["epoch"] != self.epoch,
                    "error": "runtime stopped before applying response",
                }
            )
        if self.ocr_future is not None:
            self.ocr_future.cancel()
        self.log.close()


def run_play(
    bridge,
    *,
    seconds=None,
    shadow=False,
    record=True,
    record_dir=PLAY_RECORDINGS,
    pipeline=None,
    head=None,
    notebook=None,
    ocr=True,
    quiet_seconds=60,
    clock=time.monotonic,
    sleep=time.sleep,
    conductor_factory=Conductor,
    driver_factory=None,
):
    pipeline = Pipeline() if pipeline is None else pipeline
    runtime = ControllerRuntime(bridge, shadow=shadow, clock=clock)
    recording = False
    conductor = log = None
    started = clock()
    ticks = 0
    with interrupt_handlers():
        try:
            if record:
                destination = bridge.record_start(Path(record_dir), shadow=shadow)
                recording = True
            else:
                destination = Path(record_dir) / datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
                destination.mkdir(parents=True)
            conductor = conductor_factory(
                destination,
                head=head,
                notebook=notebook,
                ocr=ocr,
                quiet_seconds=quiet_seconds,
                clock=clock,
                runner=None if driver_factory is None else SkillRunner(driver_factory=driver_factory),
            )
            log = (destination / "play.jsonl").open("x")
            started = runtime.last_fresh = clock()
            while seconds is None or clock() - started < seconds:
                tick = clock()
                frame = bridge.frame(None, after=runtime.last_id)
                received = clock()
                fresh = runtime.observe(frame, received)
                result = reading = None
                if fresh:
                    reading, moving, _command = pipeline.step(
                        minimap_crop(frame.rgb), received - frame.age, feedback=not shadow
                    )
                    result = conductor.tick(
                        Observation(reading, moving if not shadow else None, received), frame.rgb
                    )
                sent, status = runtime.tick(
                    None if result is None else result.pad, fresh=fresh, received=received
                )
                log.write(
                    json.dumps(
                        {
                            "t": received - started,
                            "frame_id": None if frame is None else frame.id,
                            "fresh": fresh,
                            "reading": None if reading is None else asdict(reading),
                            "skill": conductor.runner.describe(),
                            "result": None if result is None else asdict(result),
                            "sent": sent,
                            "status": status,
                        }
                    )
                    + "\n"
                )
                log.flush()
                ticks += 1
                sleep(max(0, tick + 1 / 30 - clock()))
        except RuntimeInterruptedError:
            pass
        finally:
            try:
                cleanup_runtime(runtime, recording=recording, pipeline=pipeline, logs=(log,))
            finally:
                if conductor is not None:
                    conductor.close()
    return {
        "ticks": ticks,
        "elapsed": clock() - started,
        "conflicts": runtime.conflicts,
        "requests": 0 if conductor is None else conductor.request_count,
    }
