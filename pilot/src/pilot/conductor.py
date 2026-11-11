"""Event-driven strategy around a local, frame-driven skill runner."""

from __future__ import annotations

import json
import math
import threading
import time
from concurrent.futures import Future
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

import cv2

from .contract import FRAME_SIZE, HUD_RECT, Pad
from .flow import MENUS
from .head import HeadRequest, ScriptedHead, build_prompt, parse_response, response_data
from .loop import ControllerRuntime, Pipeline, RuntimeInterruptedError, cleanup_runtime, interrupt_handlers
from .scene import EventDetector, SceneText, TextReader
from .skills import Observation, SkillResult, SkillRunner

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
        flow=None,
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
        self.head_latency = 9.0
        self.carry_started = None
        self.carry_logged = None
        self.carry_allowed = False
        self.last_hud = None
        self.wanted_candidate = None
        self.wanted_since = None
        self.wanted_seen = None
        self.wanted_level = None
        self.low_health_since = None
        self.low_health_reported = False
        self.flow = flow
        self.flow_result = None
        self.flow_started = None
        self.flow_screen = None
        self.flow_events = []
        self.flow_actions = []
        self.expected_skill = None
        self.text_time = None
        self.ocr_capture_time = None

    def write(self, row):
        self.log.write(json.dumps(row, ensure_ascii=False) + "\n")
        self.log.flush()

    def _read_text(self, rgb):
        if self.reader is None:
            self.reader = TextReader()
        return self.reader.read(rgb)

    def _text(self, rgb, t, injected, capture_time=None):
        captured = t if capture_time is None else capture_time
        if injected is not None:
            self.text, self.text_time = injected, captured
        if not self.ocr:
            return
        if self.ocr_future is not None:
            if self.ocr_future.done():
                try:
                    result = self.ocr_future.result()
                    if self.text_time is None or self.ocr_capture_time >= self.text_time:
                        self.text, self.text_time = result, self.ocr_capture_time
                except Exception as exc:
                    self.write({"type": "ocr_error", "t": t, "error": str(exc)})
                    raise RuntimeError("scene OCR failed") from exc
                self.ocr_future = None
            elif self.clock() - self.ocr_started >= self.ocr_timeout:
                self.write({"type": "ocr_error", "t": t, "error": "timeout"})
                raise TimeoutError("scene OCR exceeded its time limit")
        if self.ocr_future is None and t >= self.next_ocr:
            self.ocr_started = self.clock()
            self.ocr_capture_time = captured
            self.ocr_future = self.submit(self._read_text, rgb.copy())
            self.next_ocr = t + self.ocr_interval

    def _finish_head(self, t, *, discard=False):
        if self.future is None or not self.future.done():
            return
        request = self.inflight
        duration = max(0.0, self.clock() - request["started"])
        self.head_latency = 0.5 * self.head_latency + 0.5 * duration
        row = {
            **request["row"],
            "type": "response",
            "t": t,
            "duration": duration,
            "overtaken": discard or request["epoch"] != self.epoch,
            "disposition": "discarded",
        }
        try:
            decision = parse_response(response_data(self.future.result()))
            row.update(response_data(decision))
            if not row["overtaken"]:
                if request["append"]:
                    self.runner.append(decision.plan)
                    row["disposition"] = "appended"
                else:
                    self.runner.replace(decision.plan)
                    row["disposition"] = "replaced"
                if self.carry_allowed and self.carry_started is not None:
                    self.runner.release_pending = True
                row["applied"] = True
                self.carry_started = None
                self.carry_allowed = False
                if decision.lesson:
                    self.notebook.parent.mkdir(parents=True, exist_ok=True)
                    with self.notebook.open("a") as notebook:
                        notebook.write(f"{datetime.now(UTC).isoformat()} {decision.lesson.strip()}\n")
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
            self.pending.append({"kind": "head_failed", "error": row["error"]})
        finally:
            self.write(row)
            self.future = self.inflight = None

    def _request(self, observation, rgb, *, append=False):
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
            hud=self._hud_for_head(observation),
            objects=[asdict(item) for item in observation.objects[:12]],
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
        self.inflight = {"row": row, "epoch": self.epoch, "started": self.clock(), "append": append}
        self.future = self.submit(self.head.decide, request)
        self.pending.clear()
        self.last_request_time = observation.time
        self.request_times.append(observation.time)

    def tick(self, observation: Observation, rgb, *, text=None, text_time=None, frame_time=None, events=()):
        observation = replace(observation, frame=rgb)
        t = observation.time
        self._text(rgb, t, text, text_time if text is not None else frame_time)
        detected = self.detector.update(observation.reading, t, text=self.text)
        new_events = [asdict(event) for event in detected] + list(events)
        new_events.extend(self._hud_events(observation))
        recovered = self.flow_started is not None
        flow_result = self._flow_tick(observation, rgb)
        # A stuck screen is where the reflex has done what it knows. From there the head's
        # answer is run like any plan, and the reflex takes over again when the screen changes.
        if flow_result is not None and flow_result.action != "stuck":
            return SkillResult(flow_result.pad, reason="flow")
        if recovered:
            new_events = []
        if new_events:
            self.epoch += 1
            self.pending.extend(new_events)
            self.carry_allowed = False
            self.carry_started = None
        self._finish_head(t)
        result = self.runner.tick(observation)
        self._expect_skill()
        if self.runner.completed:
            last = self.runner.describe()
            failed = result.status == "failed"
            self.carry_allowed = (
                not failed
                and last.get("name") in ("walk", "walk_to")
                and observation.reading.minimap == "flat"
                and not observation.reading.corrupt
                and not new_events
                and (observation.hud is None or observation.hud.screen == "game")
            )
            self.carry_started = t if self.carry_allowed else None
            if failed:
                self.epoch += 1
                self.pending.append({"kind": "skill_failed", "skill": last})
            elif self.future is None:
                self.pending.append({"kind": "skill_ended", "skill": last})
        quiet = self.last_request_time is None or t - self.last_request_time >= self.quiet_seconds
        remaining = self.runner.remaining(t)
        if self.future is None:
            if self.pending or quiet:
                self._request(observation, rgb)
            elif self.runner.has_plan and remaining < self.head_latency:
                self.pending.append(
                    {
                        "kind": "plan_ending",
                        "remaining_seconds": remaining,
                        "steps": self.runner.remaining_steps(t),
                    }
                )
                self._request(observation, rgb, append=True)
        if (
            not self.runner.has_plan
            and self.future is not None
            and self.carry_allowed
            and self.carry_started is not None
            and 0 <= t - self.carry_started < 4
            and observation.reading.minimap == "flat"
            and not observation.reading.corrupt
            and (observation.hud is None or observation.hud.screen == "game")
        ):
            result = SkillResult(Pad(left=(0.0, -0.45)), reason="carry-on")
            if self.carry_logged != self.carry_started:
                # One row per carry, not one per tick: the play log has the ticks.
                self.write({"type": "carry_on", "t": t, "name": "carry_on"})
                self.carry_logged = self.carry_started
        elif not self.runner.has_plan and not observation.reading.corrupt:
            # A damaged tick is stood out and decides nothing: the minimap reader calls a clean
            # cable picture damaged about once a second, and the carry would never last.
            self.carry_allowed = False
        return result

    def _hud_for_head(self, observation):
        if observation.hud is None:
            return None
        hud = asdict(observation.hud)
        # The one tick the head is asked on may be one the reader stood out; the level the stars
        # held a moment ago says more than nothing.
        fresh = self.wanted_seen is not None and observation.time - self.wanted_seen <= 5.0
        if hud["wanted"] is None and fresh:
            hud["wanted"] = self.wanted_level
        return hud

    def _hud_events(self, observation):
        hud, t = observation.hud, observation.time
        if hud is None:
            self.low_health_since = None
            self.low_health_reported = False
            return []
        events = []
        if hud.wanted is not None:
            # A tick without a number is stood out and decides nothing: the reader abstains on one
            # clean frame in six and for seconds at a time. A number counts once it has been read
            # again half a second later with no other number in between and no gap over a second.
            if hud.wanted != self.wanted_candidate or t - self.wanted_seen > 1.0:
                self.wanted_candidate, self.wanted_since = hud.wanted, t
            self.wanted_seen = t
            if hud.wanted != self.wanted_level and t - self.wanted_since >= 0.5:
                # A session that begins without stars has nothing to tell; one that begins with
                # stars does.
                if self.wanted_level is not None or hud.wanted:
                    events.append({"kind": "wanted_changed", "wanted": hud.wanted})
                self.wanted_level = hud.wanted
        if hud.health is not None and hud.health < 0.3:
            if self.low_health_since is None:
                self.low_health_since = t
            if not self.low_health_reported and t - self.low_health_since >= 0.5:
                events.append({"kind": "low_health", "health": hud.health})
                self.low_health_reported = True
        else:
            self.low_health_since = None
            self.low_health_reported = False
        previous = self.last_hud
        if self.flow is None and previous is not None and hud.screen != previous.screen:
            events.append({"kind": "screen_changed", "screen": hud.screen})
        self.last_hud = hud
        return events

    def _expect_skill(self):
        if self.flow is None:
            return
        active = self.runner.active
        if active is self.expected_skill:
            return
        self.flow.end_expectation()
        self.expected_skill = active
        if active is not None and getattr(active, "opens", ()):
            self.flow.expect(*active.opens, until=self.runner.active_started + active.limit)

    def _abandon_head(self, t):
        if self.future is None:
            return
        self.future.cancel()
        self.write(
            {
                **self.inflight["row"],
                "type": "response",
                "t": t,
                "duration": max(0, self.clock() - self.inflight["started"]),
                "overtaken": True,
                "disposition": "discarded",
                "applied": False,
            }
        )
        self.future = self.inflight = None

    def _flow_tick(self, observation, rgb):
        if self.flow is None:
            return None
        self._expect_skill()
        t = observation.time
        fresh_text = self.text if self.text_time is not None and 0 <= t - self.text_time <= 1.5 else None
        result = self.flow.tick(observation, fresh_text)
        self.flow_result = result
        if result is not None:
            if self.flow_started is None and result.action in ("confirm", "await_hud", "await_fresh_read"):
                # One odd reading is not a screen yet: this tick is neutral and the plan is kept.
                return result
            screen = observation.hud.screen if observation.hud is not None else self.flow_screen
            if result.action != "stuck" and self.runner.has_plan:
                # Also what the head planned for a stuck screen, once that screen has changed.
                self.runner.stop("flow")
                self._expect_skill()
            if self.flow_started is None:
                self.epoch += 1
                self.pending.clear()
                self.carry_allowed, self.carry_started = False, None
                self.flow_started, self.flow_screen = t, screen
                self.flow_events, self.flow_actions = [], []
                self.write(
                    {
                        "type": "flow_enter",
                        "t": t,
                        "screen": screen,
                        "action": result.action,
                        "buttons": list(result.pad.buttons),
                        "seconds": 0,
                    }
                )
            action = {"screen": screen, "action": result.action, "buttons": list(result.pad.buttons)}
            previous = self.flow_actions[-1] if self.flow_actions else None
            if previous is None or any(previous[key] != value for key, value in action.items()):
                self.flow_actions.append({**action, "seconds": t - self.flow_started})
            if result.action != "stuck":
                self._finish_head(t, discard=True)
            for event in result.events:
                if event["kind"] == "stuck":
                    # The rest of this tick asks the head, and from here its answer is run.
                    self._abandon_head(t)
                    self.pending = [{**event, "seconds": t - self.flow_started}]
                else:
                    self.flow_events.append(event)
            return result
        if self.flow_started is not None:
            seconds = t - self.flow_started
            self.epoch += 1
            self._abandon_head(t)
            self.pending = [
                {"screen": self.flow_screen, **event, "seconds": seconds} for event in self.flow_events
            ] or [
                {
                    "kind": "menu_closed" if self.flow_screen in MENUS else "screen_cleared",
                    "screen": self.flow_screen,
                    "seconds": seconds,
                }
            ]
            self.write(
                {
                    "type": "flow_exit",
                    "t": t,
                    "screen": self.flow_screen,
                    "action": "recovered",
                    "seconds": seconds,
                    "actions": self.flow_actions,
                }
            )
            self.flow_started = None
        return None

    def describe(self, result=None):
        if self.flow_result is not None and not (self.flow_result.action == "stuck" and self.runner.has_plan):
            return {
                "name": "flow",
                "action": self.flow_result.action,
                "status": "running",
                "screen": self.flow_screen,
            }
        if result is not None and result.reason == "carry-on":
            return {"name": "carry_on", "status": "running", "reason": "head-pending"}
        return self.runner.describe()

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
        close = getattr(self.head, "close", None)
        if close is not None:
            close()
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
    objects=None,
    hud=None,
    flow=None,
):
    pipeline = Pipeline() if pipeline is None else pipeline
    runtime = ControllerRuntime(bridge, shadow=shadow, clock=clock)
    recording = False
    conductor = log = None
    started = clock()
    ticks = 0
    detections, capture_time = (), None
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
                **({"flow": flow} if flow is not None else {}),
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
                    if objects is not None:
                        newest = objects.poll(frame.rgb, received - frame.age)
                        if newest is not None:
                            capture_time, detections = newest
                            detections = tuple(detections)
                    result = conductor.tick(
                        Observation(
                            reading,
                            moving if not shadow else None,
                            received,
                            frame=frame.rgb,
                            objects=detections,
                            objects_time=capture_time,
                            hud=None
                            if hud is None
                            else hud.read(frame.rgb, text=getattr(conductor, "text", None)),
                        ),
                        frame.rgb,
                        frame_time=received - frame.age,
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
                            "skill": conductor.describe(result)
                            if hasattr(conductor, "describe")
                            else (
                                {"name": "carry_on", "status": "running", "reason": "head-pending"}
                                if result is not None and result.reason == "carry-on"
                                else conductor.runner.describe()
                            ),
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
                try:
                    if objects is not None:
                        objects.close()
                finally:
                    if conductor is not None:
                        conductor.close()
    return {
        "ticks": ticks,
        "elapsed": clock() - started,
        "conflicts": runtime.conflicts,
        "requests": 0 if conductor is None else conductor.request_count,
    }
