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

from . import ahead
from .contract import FRAME_SIZE, HUD_RECT, NEUTRAL_PAD, Pad, player_mode
from .flow import MENUS
from .goals import interruption
from .head import HeadRequest, ScriptedHead, SkillCall, build_prompt, parse_response, response_data
from .judge import ModeFilter
from .loop import ControllerRuntime, Pipeline, RuntimeInterruptedError, cleanup_runtime, interrupt_handlers
from .notes import intent
from .profile import active
from .scene import EventDetector, SceneText, TextReader
from .skills import Observation, SkillResult, SkillRunner
from .where import Sense

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
    OCR_SLOW_SECONDS = 3.0
    # After the 13 November dropout, the second vehicle answer arrived at +0.934 s.
    PICTURE_SETTLE_SECONDS = 1.0

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
        ocr_timeout=20.0,
        submit=background,
        clock=time.monotonic,
        opening=(),
        judge=None,
        awake=None,
        guard=None,
        standing=None,
    ):
        for value in (quiet_seconds, ocr_interval, ocr_timeout):
            if not math.isfinite(value) or value <= 0:
                raise ValueError("conductor intervals must be positive and finite")
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.log = (self.directory / "head.jsonl").open("x")
        self.head = ScriptedHead() if head is None else head
        self.trip = getattr(self.head, "trip", None)
        self.notebook = PLAY_RECORDINGS / "notebook.txt" if notebook is None else Path(notebook)
        self.runner = SkillRunner() if runner is None else runner
        # What the session does before the head has said anything, such as setting the view and
        # levelling the camera. An opening skill that fails costs the head's first plan nothing.
        if opening and self.trip is None:
            self.runner.replace(tuple(opening), opening=True)
        self.detector = EventDetector() if detector is None else detector
        self.ocr, self.reader = ocr, text_reader
        self.quiet_seconds, self.ocr_interval, self.ocr_timeout = quiet_seconds, ocr_interval, ocr_timeout
        self.submit, self.clock = submit, clock
        self.text = SceneText()
        self.ocr_future = None
        self.ocr_started = None
        self.ocr_slow = False
        self.next_ocr = float("-inf")
        self.pending = [{"kind": "startup"}]
        self.epoch = 0
        self.future = None
        self.inflight = None
        self.goal = None
        self.request_count = 0
        self.last_request_time = None
        self.request_times = []
        self.closed = False
        self.head_latency = 9.0
        self.carry_started = None
        self.carry_logged = None
        self.carry_allowed = False
        self.last_hud = None
        self.answering = False
        self.buttons_down: frozenset[str] = frozenset()
        self.last_pad = NEUTRAL_PAD
        self.ocr_failures = 0
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
        self.judge = judge
        self.judgment = None
        self.mode_filter = ModeFilter()
        self.judged_mode = None
        self.judge_events = []
        self.judge_log = (self.directory / "judge.jsonl").open("x") if judge is not None else None
        self.awake = awake
        self.nudge = active().right_for(self.NUDGE_STICK)
        self.last_input = None
        self.nudge_until = None
        self.own_screen_until = -math.inf
        # Off unless given one: `pilot play --guard`. Without it the conductor is what it was.
        self.guard = guard
        self.guard_verdict = None
        self.guard_events = []
        self.applied_at = None
        # Seconds without movement on the game's own screen after which the head is told the figure
        # stands; None leaves it out (`pilot play --no-standing`, and every test run of one skill).
        self.standing = standing
        self.still = self.moved = self.moved_since = 0.0
        self.standing_count = 0
        self.still_time = None
        # The bridge refuses the pad while a hand is on the controller: the plan is put down and
        # nothing is planned until the pad is taken again.
        self.refused_since = None
        self.picture_missing_since = None
        self.picture_back_since = None
        self.exit_pressed_until = -math.inf
        self.menu_seen = -math.inf
        self.routed = False
        self.where = Sense(ahead.where())
        self.known_place: str | None = None

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
                    self.ocr_failures = 0
                except Exception as exc:
                    # One reading that failed is one picture unread; the reader failing time after
                    # time is a pilot that cannot read, and that ends the session.
                    self.ocr_failures += 1
                    self.write({"type": "ocr_error", "t": t, "error": str(exc), "row": self.ocr_failures})
                    if self.ocr_failures >= self.OCR_FAILURES:
                        raise RuntimeError("scene OCR failed") from exc
                self.ocr_future = None
            elif self.clock() - self.ocr_started >= self.ocr_timeout:
                self.write({"type": "ocr_error", "t": t, "error": "timeout"})
                raise TimeoutError("scene OCR exceeded its time limit")
            elif not self.ocr_slow and self.clock() - self.ocr_started >= self.OCR_SLOW_SECONDS:
                # On 12 November a reading took over three seconds while the Mac classified
                # recordings beside the pilot, and that ended the session. A late reading only
                # leaves the pilot without fresh text, which it treats as no text; a reader that
                # stays away for ocr_timeout still ends it.
                self.ocr_slow = True
                self.write({"type": "ocr_slow", "t": t, "seconds": self.clock() - self.ocr_started})
        if self.ocr_future is None and t >= self.next_ocr:
            self.ocr_slow = False
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
        discarded = getattr(self.head, "discard", None)
        try:
            decision = parse_response(response_data(self.future.result()))
            # A goal is the rules' own; whatever else answers brings a plan and no goal.
            if not getattr(self.head, "owns_goals", False) and decision.goal is not None:
                decision = replace(decision, goal=None)
            row.update(response_data(decision))
            if row["overtaken"]:
                if discarded is not None:
                    discarded()
            else:
                if decision.action == "go_on":
                    if self.runner.has_plan:
                        row["disposition"] = "kept"
                    elif decision.goal is not None:
                        # The skill ended while the answer was on its way: ask for the next step now.
                        row["disposition"] = "kept"
                        self.pending.append({"kind": "plan_finished"})
                    else:
                        # Nothing runs for it to go on with, and asking again at once would only
                        # bring the same answer: a short wait, and the end of it asks.
                        row["disposition"] = "refused"
                        row["error"] = "go_on without a running plan"
                        self.runner.append((SkillCall("wait", {"duration": 3}),))
                elif getattr(self.runner, "uninterruptible", False) or (
                    decision.goal is None and request["append"]
                ):
                    self.runner.append(decision.plan)
                    row["disposition"] = "appended"
                else:
                    self.runner.replace(decision.plan)
                    row["disposition"] = "replaced"
                if row["disposition"] in ("appended", "replaced"):
                    self.applied_at = t
                self.goal = decision.goal
                if decision.action != "go_on" and self.carry_allowed and self.carry_started is not None:
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
            if discarded is not None:
                discarded()
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
            time=observation.time,
            place=self.where.place,
            hud=self._hud_for_head(observation),
            objects=[asdict(item) for item in observation.objects[:12]],
            judgment=(
                {
                    **asdict(observation.judgment),
                    "age": observation.time - observation.judgment.capture,
                    "mode": observation.mode,
                }
                if observation.judgment is not None
                else None
            ),
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
        if self.trip is None:
            self.future = self.submit(self.head.decide, request)
        else:
            # This fixed policy does no I/O or inference. Apply it on this tick, so a receipt
            # cannot be consumed by an answer that another event then discards.
            self.future = Future()
            self.future.set_result(self.head.decide(request))
        self.pending.clear()
        self.last_request_time = observation.time
        self.request_times.append(observation.time)

    # When the controller has rested for half a minute the game leaves the figure and shows scenery,
    # and from that picture the judge and the object reader tell nothing true: live on 11 November
    # the judge said "vehicle" to a car park, the skills waited for a figure on foot, and because
    # they waited the scenery stayed. A touch of the camera brings the figure back.
    OWN_SCREEN_SECONDS = 2.0  # the minimap is read as back about a second after a map has closed
    # Behind an open map the judge sees the paused scene and may take the car from outside for a
    # figure on foot; it said so and took it back within two seconds (session 20261111-131628).
    OWN_SCREEN_NEWS = ("hud_absent", "hud_present", "vehicle_enter", "vehicle_exit")
    AWAKE_SECONDS = 15.0
    NUDGE_SECONDS = 0.1  # one tick is easy for the console to miss
    NUDGE_STICK = 0.5  # as it reaches the console

    # Skills during which a standing figure is what was asked for: a fight from one spot, a menu the
    # skill itself opened, a move of the camera that has the figure stand. Their seconds do not count.
    OCR_FAILURES = 5  # readings of the text that fail in a row before the session ends
    STILL_SKILLS = frozenset(
        {
            "fight",
            "melee",
            "shoot",
            "punch",
            "press",
            "set_waypoint",
            "level_camera",
            "set_far_view",
            "use_place",
            "do_prompt",
            "switch_character",
        }
    )
    # PLAN.md: the pilot frees itself within about ten seconds and never stands. Every skill's own
    # guard acts within two to five; this is the bound behind them.
    STANDING_SECONDS = 12.0
    STILL_TICK = 0.2  # a tick that comes late has not shown the figure standing for all that time
    # A touch of the camera (the nudge that keeps the game's own view, a look) moves the map for a
    # moment: only this much movement in a row says the figure is under way again.
    MOVED_SECONDS = 1.5
    STANDING_RESET = 3.0  # movement after which the next standing is counted as the first again

    def _standing(self, observation, *, busy):
        """The event for a figure that has not moved for `standing` seconds, or None.

        The plan's own rule is that the pilot never stands (PLAN.md): each skill has its guard, and this
        is the one behind them all, for what no skill notices: a plan of waits, a head that keeps
        answering with what does nothing, a screen no reader has a name for.
        """
        t = observation.time
        previous, self.still_time = self.still_time, t
        if self.standing is None or previous is None or not 0 < t - previous:
            return None
        step = min(t - previous, self.STILL_TICK)
        reading, hud = observation.reading, observation.hud
        active = self.runner.active
        waiting = self.text.objective.strip() and intent(self.text.objective)["class"] == "wait"
        if (
            busy
            or reading.corrupt
            or reading.minimap == "none"
            or observation.moving is None
            or observation.mode == "none"
            or (hud is not None and hud.screen != "game")
            or t < self.own_screen_until
            or waiting
            or (active is not None and (active.name in self.STILL_SKILLS or getattr(active, "opens", ())))
        ):
            return None
        if observation.moving:
            self.moved += step
            self.moved_since += step
            if self.moved >= self.MOVED_SECONDS:
                self.still = 0.0
            if self.moved_since >= self.STANDING_RESET:
                self.standing_count = 0
            return None
        self.moved = 0.0
        self.still += step
        if self.still < self.standing:
            return None
        self.standing_count += 1
        event = {"kind": "standing", "seconds": round(self.still, 1), "count": self.standing_count}
        self.still = self.moved_since = 0.0
        return event

    def refuse(self, t, refused):
        """The bridge refuses the pad, or takes it again (`run_play` says which on every tick).

        A hand on the controller is Kerim taking over. Until 13 November the skills ran on against a
        pad that went nowhere and ended on what they had not done. Now the plan is put down once, no
        skill is stepped and the head is not asked while the pad is refused, and when it is taken again
        the head hears of it and plans afresh from the picture as it then is.
        """
        if refused and self.refused_since is None:
            self.refused_since = t
            self.runner.stop("pad_refused")
            if self.trip is not None:
                self.trip.suspend("human", t)
                self._trip_log(t)
            self._expect_skill()
            self._flow_put_down(t)
            self.epoch += 1
            self._abandon_head(t)
            self.pending.clear()
            self.carry_allowed, self.carry_started = False, None
            self.goal = None
            self.write({"type": "pad_refused", "t": t})
        elif not refused and self.refused_since is not None:
            seconds = t - self.refused_since
            self.refused_since = None
            self.epoch += 1
            self.pending.append({"kind": "pad_returned", "seconds": seconds})
            self._flow_put_down(t)
            self.still = self.moved = 0.0
            self.write({"type": "pad_returned", "t": t, "seconds": seconds})

    def _flow_put_down(self, t):
        """The reflex forgets the screen in hand: nothing it pressed into a refused pad arrived."""
        if self.flow is None:
            return
        if self.flow_started is not None:
            self.write(
                {
                    "type": "flow_exit",
                    "t": t,
                    "screen": self.flow_screen,
                    "action": "pad_refused",
                    "seconds": t - self.flow_started,
                    "actions": self.flow_actions,
                }
            )
            self.flow_started = None
        self.flow_result = None
        if hasattr(self.flow, "reset"):
            self.flow.reset()

    def sent(self, pad, t):
        pressed = active().enter_vehicle in pad.buttons
        if pressed and not getattr(self, "exit_button_down", False):
            if (
                self.judged_mode == "vehicle"
                or self.mode_filter.mode == "vehicle"
                or getattr(self, "vehicle_map", False)
            ):
                # The longest Triangle-to-flat interval in the 12/13 November logs is 2.937 s.
                self.exit_pressed_until = t + 3.0
        self.exit_button_down = pressed

    def missing(self, t, *, lost=True):
        """No picture is evidence for no change, and never justifies holding an input."""
        self.guard_events = []
        self.judge_events.clear()
        self.buttons_down = frozenset()
        self.last_pad = NEUTRAL_PAD
        self.nudge_until = None
        if hasattr(self.detector, "pause"):
            self.detector.pause()
        if lost:
            self.picture_back_since = None
            if self.picture_missing_since is None:
                self.picture_missing_since = t
                self.runner.stop("interrupted")
                if self.trip is not None:
                    self.trip.suspend("picture", t)
                    self._trip_log(t)
                self._expect_skill()
                self._flow_put_down(t)
                self.epoch += 1
                self._abandon_head(t)
                self.pending.clear()
                self.judge_events.clear()
                self.carry_allowed, self.carry_started = False, None
                self.goal = None
                self.mode_filter = ModeFilter()
                self.judgment = self.judged_mode = None
                self.exit_pressed_until = -math.inf
                self.still = self.moved = 0.0
                self.wanted_candidate = self.wanted_since = self.wanted_seen = None
                self.low_health_since = None
                self.write({"type": "picture_lost", "t": t})
        return SkillResult()

    def tick(self, observation: Observation, rgb, **reads):
        t = observation.time
        # Only a picture that is not there is missing. A map read as damaged is no sign of it: on
        # 13 November the reader called the map damaged for 15 and for 45 s on end with a fresh picture
        # in every tick, on the landing and on the street, and through the 20 s without a picture it
        # had said so not once.
        if rgb is None:
            return self.missing(t)
        self.vehicle_map = observation.reading.minimap == "tilted" and not observation.reading.corrupt
        if self.picture_missing_since is not None:
            if self.picture_back_since is None:
                self.picture_back_since = t
            if t - self.picture_back_since < self.PICTURE_SETTLE_SECONDS:
                self._judge_observation(observation, rgb, reads.get("frame_time"))
                return self.missing(t, lost=False)
            seconds = self.picture_back_since - self.picture_missing_since
            self.pending.append({"kind": "picture_returned", "seconds": seconds})
            self.write({"type": "picture_returned", "t": t, "seconds": seconds})
            self.picture_missing_since = self.picture_back_since = None
        result = self._tick(observation, rgb, **reads)
        # Nothing new is pressed on a damaged picture: a button that was down stays down, so that a
        # press is not cut in two, and one that would go down on this tick waits for a picture.
        buttons = result.pad.buttons
        if observation.reading.corrupt and buttons:
            menu_back = (
                observation.hud is not None
                and observation.hud.screen in MENUS
                and (reads.get("frame_time") is None or 0 <= t - reads["frame_time"] <= 0.3)
            )
            kept = tuple(
                button
                for button in buttons
                if button in self.buttons_down
                or (menu_back and button == active().back)
                or (
                    menu_back
                    and self.trip is not None
                    and self.runner.active is not None
                    and self.runner.active.name == "set_waypoint"
                    and observation.hud.screen in self.runner.active.opens
                )
            )
            if kept != buttons:
                result = replace(result, pad=replace(result.pad, buttons=kept))
        self.buttons_down = frozenset(result.pad.buttons)
        self.last_pad = result.pad
        if self.awake is None or (
            self.trip is not None
            and (
                self.trip.verdict is not None
                or self.trip.suspended is not None
                or self.refused_since is not None
            )
        ):
            return result
        t = observation.time
        if result.pad != NEUTRAL_PAD:
            self.last_input, self.nudge_until = t, None
            return result
        if observation.hud is not None and observation.hud.screen != "game":
            self.nudge_until = None
            return result
        # A session does not know how long the controller rested before it began.
        if self.nudge_until is None and (self.last_input is None or t - self.last_input >= self.awake):
            self.nudge_until = t + self.NUDGE_SECONDS
        if self.nudge_until is not None:
            if t < self.nudge_until:
                return replace(result, pad=Pad(right=(self.nudge, 0.0)))
            self.last_input, self.nudge_until = t, None
            self.nudge = -self.nudge  # the next one turns back
        return result

    def _judge_observation(self, observation, rgb, frame_time):
        t = observation.time
        if self.judge is not None:
            judgment = self.judge.poll(rgb, t if frame_time is None else frame_time)
            flat = observation.reading.minimap == "flat" and not observation.reading.corrupt
            if observation.hud is not None and observation.hud.screen in {"map", "pause"}:
                self.menu_seen = t
            tilted = observation.reading.minimap == "tilted" and not observation.reading.corrupt
            self.routed = (
                tilted
                and observation.reading.confidence >= 0.45
                and observation.reading.route in {"yellow", "purple"}
            )
            mode = self.mode_filter.update(
                judgment,
                t,
                flat=flat,
                vehicle=tilted,
                routed=self.routed,
                # An answer arrives a third of a second after its picture: one taken on the map can
                # come in over the game.
                game=judgment is None or judgment.capture > self.menu_seen,
            )
            if judgment is not None:
                self.judgment = judgment
            observation = replace(observation, judgment=self.judgment, mode=mode)
            # A judge that falls silent is no news for the head, and neither is its first word:
            # an event is a change between two modes it has named. Each event ends the running
            # plan's claim on the head, so a server that stutters must not make one.
            if mode is not None and mode != self.judged_mode:
                if self.judged_mode is not None and "none" in {self.judged_mode, mode}:
                    self.judge_events.append({"kind": "mode_changed", "old": self.judged_mode, "new": mode})
                self.judged_mode = mode
            rows = self.judge.drain_failures()
            if judgment is not None:
                rows.append(asdict(judgment))
            for row in rows:
                self.judge_log.write(json.dumps({"t": t, **row, "mode": mode}) + "\n")
            if rows:
                self.judge_log.flush()
        return observation

    def _tick(self, observation: Observation, rgb, *, text=None, text_time=None, frame_time=None, events=()):
        observation = replace(observation, frame=rgb)
        t = observation.time
        self.guard_events = []
        observation = self._judge_observation(observation, rgb, frame_time)
        self._text(rgb, t, text, text_time if text is not None else frame_time)
        self.where.step(observation, walked=any(self.last_pad.left))
        place = self.where.place
        observation = replace(observation, place=place)
        if place in ahead.PLACES and place != self.known_place:
            # A room or a landing the figure has come into is news for the head: the skill that
            # runs was planned for another place. On 13 November leave_building came out on the
            # landing, was not told, and went round along the wall back into the apartment. The
            # street is where the skills end by themselves, and a verdict forgotten is no place.
            if place != "street":
                self.judge_events.append({"kind": "place_changed", "old": self.known_place, "new": place})
            self.known_place = place
        # The reflex is shown the screen as the reader named it. For the skills, the guard and the
        # head a phone with a call on it is the game: the figure walks and drives on while it talks.
        seen = observation
        if (
            observation.hud is not None
            and observation.hud.screen == "phone"
            and getattr(self.flow, "calls", False)
            and self.flow.on_call(observation, self._fresh_text(t))
        ):
            observation = replace(observation, hud=replace(observation.hud, screen="game"))
        detected = self.detector.update(
            observation.reading,
            t,
            text=self.text,
            mode=observation.mode,
            exit_confirmed=self.mode_filter.exit_confirmed and not self.routed,
            exit_pressed=t <= self.exit_pressed_until,
        )
        # A skill that opens the map hides the minimap, and that is its own doing and no news. Told
        # of it live on 11 November, the head planned a wait for the screen, the wait replaced the
        # skill, and the reflex closed the map the skill had just opened.
        if getattr(self.runner.active, "opens", ()):
            self.own_screen_until = t + self.OWN_SCREEN_SECONDS
        if t < self.own_screen_until:
            detected = [event for event in detected if event.kind not in self.OWN_SCREEN_NEWS]
        new_events = [asdict(event) for event in detected] + list(events)
        new_events.extend(self._hud_events(observation))
        if self.trip is not None:
            return self._trip_tick(observation, seen, rgb, new_events)
        if self.goal is not None:
            reason = interruption(
                HeadRequest(
                    new_events,
                    self.text.help,
                    self.text.objective,
                    self.text.subtitle,
                    self.text.banner,
                    asdict(observation.reading),
                    self.runner.describe(),
                    "",
                    "",
                    hud=asdict(observation.hud) if observation.hud is not None else None,
                    time=t,
                    place=self.where.place,
                ),
                self.goal,
            )
            if reason:
                self.runner.stop("goal_" + reason)
                self.write({"type": "goal_end", "t": t, "goal": self.goal, "reason": reason})
                self.goal = None
                # Flow can return early. Invalidate the pending answer before it gets that chance.
                # The event goes to pending here and nowhere else: new_events reaches it below.
                self.epoch += 1
                self.pending.append({"kind": "goal_interrupted", "reason": reason})
                self.carry_allowed = False
                self.carry_started = None
        if self.refused_since is not None:
            # The readers have read; neither the reflex nor a skill is run against a pad that goes
            # nowhere, and what happened meanwhile is not news once the pad is back: the head then
            # plans from the picture as it is.
            return SkillResult(reason="pad-refused")
        recovered = self.flow_started is not None
        episode = self.flow_started is not None
        flow_result = self._flow_tick(seen, rgb)
        if flow_result is not None and flow_result.action == "confirm" and not episode:
            # One odd reading is not a screen yet. Sticks and triggers rest for this tick; a button
            # that is down stays down, since letting go of it for one tick would make two presses of one.
            return SkillResult(Pad(buttons=self.last_pad.buttons), reason="flow")
        # A stuck screen is where the reflex has done what it knows. From there the head's
        # answer is run like any plan, and the reflex takes over again when the screen changes.
        if flow_result is not None and flow_result.action != "stuck":
            if self.guard is not None and flow_result.action != "answer":
                # The screen is the reflex's: whatever the guard held it lets go of.
                self._guard_tick(observation, [], flow=True)
            return SkillResult(flow_result.pad, reason="flow")
        if recovered:
            new_events = []
        # The judge names no mode for a map. While a skill has its own map open that turn of its
        # word is the skill's doing as well: on 12 November fourteen of them each replaced
        # set_waypoint with a wait, and the reflex closed the map it had left open.
        if t < self.own_screen_until:
            self.judge_events.clear()
        new_events.extend(self.judge_events)
        self.judge_events.clear()
        # The guard answers before the head's answer is taken and the plan is run, so that its pad is on
        # this tick whatever the head is doing.
        guarded = self.guard is not None and self._guard_tick(observation, new_events).pad is not None
        stands = self._standing(observation, busy=guarded)
        if stands is not None:
            new_events.append(stands)
        if new_events:
            self.epoch += 1
            self.pending.extend(new_events)
            self.carry_allowed = False
            self.carry_started = None
        self._finish_head(t)
        if guarded:
            # The plan waits while the guard holds the pad; what the head answers meanwhile is queued.
            result = SkillResult(self.guard_verdict.pad, reason="guard")
        else:
            result = self._plan_tick(observation, new_events, t)
        quiet = self.last_request_time is None or t - self.last_request_time >= self.quiet_seconds
        remaining = self.runner.remaining(t)
        if self.future is None:
            if self.pending or quiet:
                self._request(observation, rgb)
            elif not guarded and self.runner.has_plan and remaining < self.head_latency:
                self.pending.append(
                    {
                        "kind": "plan_ending",
                        "remaining_seconds": remaining,
                        "steps": self.runner.remaining_steps(t),
                    }
                )
                self._request(observation, rgb, append=True)
        if guarded:
            return result
        if (
            not self.runner.has_plan
            and self.future is not None
            and self.carry_allowed
            and self.carry_started is not None
            and 0 <= t - self.carry_started < 4
            and player_mode(observation) == "foot"
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

    def _trip_log(self, t):
        while self.runner.ended:
            self.trip.accept(self.runner.ended.popleft(), t)
        while self.trip.events:
            self.write(self.trip.events.pop(0))

    def end_trip(self, reason, t):
        if self.trip is not None:
            self.trip.start(t)
            self.trip.finish("failed", reason, t)
            self.runner.stop("goal_trip_verdict")
            self._trip_log(t)

    def _trip_tick(self, observation, seen, rgb, events):
        t, trip = observation.time, self.trip
        self.judge_events.clear()
        trip.observe(observation)
        self._trip_log(t)
        if t - trip.started >= trip.seconds:
            self.end_trip("trip time budget exhausted", t)
        if (
            (trip.step == "car" or trip.seat_check)
            and trip.suspended is None
            and t - trip.car_started >= trip.CAR_SECONDS
        ):
            self.end_trip("car acquisition exceeded ninety seconds", t)
        if trip.verdict is not None:
            self.runner.stop("goal_trip_verdict")
            self._trip_log(t)
            return SkillResult(reason="goal_trip_" + trip.verdict["status"])
        if self.refused_since is not None:
            return SkillResult(reason="pad-refused")
        # Death is remembered before the reflex consumes its screen; it resets the car step only
        # after gameplay returns. Neither an objective nor a threat gets another owner of the trip.
        screen = observation.hud.screen if observation.hud is not None else None
        if screen in {"wasted", "busted"} and t - trip.screen_since >= 0.1:
            self.runner.stop("flow")
            trip.suspend("death_or_arrest", t)
        episode = self.flow_started is not None
        flow_result = self._flow_tick(seen, rgb)
        if flow_result is not None and flow_result.action == "confirm" and not episode:
            # As without a trip: one odd reading is not a screen yet, and a button that is down
            # stays down, or the one press into the car would become two and the figure get out.
            return SkillResult(Pad(buttons=self.last_pad.buttons), reason="flow")
        if flow_result is not None:
            if flow_result.action not in {
                "confirm",
                "await_frame",
                "await_hud",
                "await_fresh_read",
                "answer",
            }:
                if trip.suspended != "death_or_arrest":
                    trip.suspend("screen", t)
            self._trip_log(t)
            # A screen the reflex cannot close is an explicit failed trip, never another map attempt.
            if (
                flow_result.action == "stuck"
                and trip.suspended_at is not None
                and t - trip.suspended_at >= trip.SCREEN_SECONDS
            ):
                self.end_trip("gameplay not restored after screen recovery", t)
                return SkillResult(reason="goal_trip_failed")
            return SkillResult(flow_result.pad, reason="flow")
        owns_menu = self.runner.active is not None and screen in getattr(self.runner.active, "opens", ())
        if screen != "game" and not owns_menu:
            self._trip_log(t)
            return SkillResult(reason="goal_trip_await_game")
        if trip.suspended is not None:
            if trip.game_since is None or t - trip.game_since < 0.3:
                return SkillResult(reason="goal_trip_suspended")
            trip.resume(t)
            events = [*events, {"kind": "trip_resumed"}]
        if (
            trip.step == "drive"
            and trip.method == "route"
            and not trip.seat_check
            and trip.waypoint_id is not None
            and self.runner.active is not None
            and self.runner.active.name == "drive_route"
            and trip.progress_at is not None
            and t - trip.progress_at >= trip.PROGRESS_SECONDS
        ):
            self.runner.stop("goal_trip_recovery")
            self._trip_log(t)
            trip.recover(t, "no closer destination within twenty-five seconds")
        if trip.verdict is not None:
            self._trip_log(t)
            return SkillResult(reason="goal_trip_" + trip.verdict["status"])
        result = self._plan_tick(observation, events, t)
        self._trip_log(t)
        if trip.verdict is not None:
            self.runner.stop("goal_trip_verdict")
            self._trip_log(t)
            return SkillResult(reason="goal_trip_" + trip.verdict["status"])
        quiet = self.last_request_time is None or t - self.last_request_time >= self.quiet_seconds
        # While idle, a confirmed screen or receipt can enable the next step. No artificial wait
        # is issued just to get another request; the same two wait receipts remain distinguishable.
        # An idle trip is asked again at most twice a second: every request saves a frame.
        ready = (
            not self.runner.has_plan
            and trip.game_since is not None
            and t - trip.game_since >= 0.3
            and (self.last_request_time is None or t - self.last_request_time >= 0.5)
        )
        if events or quiet or self.runner.completed or ready:
            self.pending.extend(events)
            self._request(observation, rgb)
            self._finish_head(t)
            self._trip_log(t)
        if trip.verdict is not None:
            self.runner.stop("goal_trip_verdict")
            return SkillResult(reason="goal_trip_" + trip.verdict["status"])
        return result

    def _plan_tick(self, observation, new_events, t):
        result = self.runner.tick(observation)
        failures = getattr(self.runner, "opening_failures", None)
        while failures:
            self.write({"type": "opening_failed", "t": t, **failures.pop(0)})
        self._expect_skill()
        if self.runner.completed:
            last = self.runner.describe()
            failed = result.status == "failed"
            self.carry_allowed = (
                not failed
                and last.get("name") in ("walk", "walk_to")
                and (last.get("name") != "walk_to" or last.get("reason") == "arrived")
                and player_mode(observation) == "foot"
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
        return result

    def _guard_tick(self, observation, new_events, *, flow=False):
        """Ask the guard, and carry out what it starts and ends (docs/tasks/P65-the-guard.md)."""
        t = observation.time
        verdict = self.guard.tick(
            observation,
            objective=self.text.objective,
            moving=self._moving(),
            plan_since=self.applied_at,
            flow=flow,
        )
        self.guard_verdict = verdict
        self.guard_events = list(verdict.events)
        for event in verdict.events:
            if event["kind"] == "guard_start":
                # As the flow reflex does with a screen: the plan stops, the answer on its way is void,
                # and the head is asked afresh with the guard's event.
                self.runner.stop("guard_" + event["rule"])
                self._expect_skill()
                self.epoch += 1
                self._abandon_head(t)
                self.pending.append(event)
                self.carry_allowed, self.carry_started = False, None
            elif event["kind"] == "guard_end":
                # Heard with the next request. An answer on its way was asked while the guard held the
                # pad, with its start in view, and stands: a model head needs eight seconds for another.
                (self.flow_events if self.flow_started is not None else self.pending).append(event)
            else:
                if verdict.abandon:
                    # In a vehicle the head's rules answer a threat; a model's answer is not waited for.
                    self._abandon_head(t)
                new_events.append(event)
        return verdict

    def _moving(self):
        """A skill of the plan has the figure, or is next to: anything but a wait."""
        skill = self.runner.active
        if skill is None:
            queue = getattr(self.runner, "queue", ())
            skill = queue[0] if queue else None
        return skill is not None and skill.name != "wait"

    def _hud_for_head(self, observation):
        if observation.hud is None:
            return None
        hud = asdict(observation.hud)
        if self.guard is not None and not self.guard.settled(observation.time):
            # A health bar the guard does not trust yet is not the head's either: fading in after a
            # black screen it reads empty, and the head fled from a full bar (P64, enemy-13).
            hud["health"] = None
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
        settled = self.guard is None or self.guard.settled(t)
        if hud.health is not None and hud.health < 0.3 and settled:
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

    def _fresh_text(self, t):
        return self.text if self.text_time is not None and 0 <= t - self.text_time <= 1.5 else None

    def _flow_tick(self, observation, rgb):
        if self.flow is None:
            return None
        self._expect_skill()
        t = observation.time
        fresh_text = self._fresh_text(t)
        result = self.flow.tick(observation, fresh_text, None if fresh_text is None else self.text_time)
        if result is not None and result.action == "answer":
            # One press into a ringing phone. It is no screen of the reflex's: the plan is kept and
            # has the pad back on the next tick.
            if not self.answering:
                self.write({"type": "flow_answer", "t": t, "buttons": list(result.pad.buttons)})
            self.answering = True
            self.flow_result = None
            return result
        self.answering = False
        self.flow_result = result
        if result is not None:
            if self.flow_started is None and result.action in (
                "confirm",
                "await_hud",
                "await_fresh_read",
                "await_frame",
            ):
                # One odd reading is not a screen yet: this tick is neutral and the plan is kept.
                return result
            screen = observation.hud.screen if observation.hud is not None else self.flow_screen
            if screen == "game":
                # What the reflex tells apart on the game's own screen: an alert, a shop's menu.
                screen = getattr(self.flow, "screen", None) or screen
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
                "ended": self.runner.last,
            }
        if result is not None and result.reason == "carry-on":
            return {
                "name": "carry_on",
                "status": "running",
                "reason": "head-pending",
                "ended": self.runner.describe(),
            }
        if result is not None and result.reason == "guard" and self.guard_verdict is not None:
            return {
                "name": "guard",
                "rule": self.guard_verdict.rule,
                "status": "running",
                "reason": self.guard_verdict.why,
                "ended": self.runner.describe(),
            }
        return self.runner.describe()

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.trip is not None:
            self.end_trip("runtime stopped before arrival", self.clock())
        if self.judge is not None:
            self.judge.close()
            self.judge_log.close()
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


def guard_row(event, t, origin):
    """The play log's row for one of the guard's events, with times on the play log's clock."""
    kind = event["kind"]
    row = {"type": kind, "t": t, "rule": event["rule"]}
    if kind == "guard_end":
        row["reason"] = event["reason"]
    else:
        seen = event.get("seen")
        row["seen"] = None if seen is None else seen - origin
        row["bearing"] = event.get("bearing")
        if kind == "guard_news":
            row["where"] = event.get("where")
        else:
            row["answer"] = event.get("answer")
            if event.get("after"):
                row["after"] = event["after"]  # the rule it took over from, which writes no end row
    return row


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
    opening=(),
    judge=None,
    awake=None,
    guard=None,
    standing=None,
):
    pipeline = Pipeline() if pipeline is None else pipeline
    if seconds is None and getattr(head, "trip", None) is not None:
        seconds = head.trip.seconds
    runtime = ControllerRuntime(bridge, shadow=shadow, clock=clock)
    recording = False
    conductor = log = None
    started = clock()
    ticks = 0
    detections, capture_time = (), None
    figure = figure_vehicle = None
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
                **({"opening": opening} if opening else {}),
                **({"judge": judge} if judge is not None else {}),
                **({"awake": awake} if awake is not None else {}),
                **({"guard": guard} if guard is not None else {}),
                **({"standing": standing} if standing is not None else {}),
                runner=None if driver_factory is None else SkillRunner(driver_factory=driver_factory),
            )
            log = (destination / "play.jsonl").open("x")
            started = runtime.last_fresh = clock()
            if getattr(conductor, "trip", None) is not None:
                conductor.trip.start(started)
                conductor._trip_log(started)
            while seconds is None or clock() - started < seconds:
                tick = clock()
                undecodable = False
                try:
                    frame = bridge.frame(None, after=runtime.last_id)
                except ValueError:
                    # A malformed frame body cannot be reshaped into an RGB picture.
                    frame = None
                    undecodable = True
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
                            # The person and the vehicle the reader cut out belong to these detections.
                            figure = getattr(objects, "figure", None)
                            figure_vehicle = getattr(objects, "figure_vehicle", None)
                    refuse = getattr(conductor, "refuse", None)
                    if refuse is not None and not shadow:
                        refuse(received, runtime.blocked_until is not None)
                    result = conductor.tick(
                        Observation(
                            reading,
                            moving if not shadow else None,
                            received,
                            frame=frame.rgb,
                            objects=detections,
                            objects_time=capture_time,
                            figure=figure,
                            figure_vehicle=figure_vehicle,
                            hud=None
                            if hud is None
                            else hud.read(frame.rgb, text=getattr(conductor, "text", None)),
                        ),
                        frame.rgb,
                        frame_time=received - frame.age,
                    )
                if not fresh:
                    missing = getattr(conductor, "missing", None)
                    if missing is not None:
                        result = missing(received, lost=undecodable or received - runtime.last_fresh >= 0.3)
                sent, status = runtime.tick(
                    None if result is None else result.pad,
                    fresh=fresh or result is not None,
                    received=received,
                )
                if sent and runtime.sent_pad is not None and hasattr(conductor, "sent"):
                    conductor.sent(runtime.sent_pad, received)
                if result is not None:
                    # Rows of their own, written before the tick's row and on its clock, so that a live
                    # run is timed from play.jsonl alone: from the first reading to the pad and back.
                    for event in getattr(conductor, "guard_events", None) or ():
                        log.write(json.dumps(guard_row(event, received - started, started)) + "\n")
                log.write(
                    json.dumps(
                        {
                            "t": received - started,
                            "frame_id": None if frame is None else frame.id,
                            "fresh": fresh,
                            "place": conductor.where.place,
                            "reading": None if reading is None else asdict(reading),
                            "skill": conductor.describe(result)
                            if hasattr(conductor, "describe")
                            else (
                                {"name": "carry_on", "status": "running", "reason": "head-pending"}
                                if result is not None and result.reason == "carry-on"
                                else conductor.runner.describe()
                            ),
                            "result": None if result is None else asdict(result),
                            # What left for the console: the request with the dead zones lifted.
                            "sent_pad": None if runtime.sent_pad is None else asdict(runtime.sent_pad),
                            "sent": sent,
                            "status": status,
                        }
                    )
                    + "\n"
                )
                log.flush()
                ticks += 1
                if getattr(conductor, "trip", None) is not None and conductor.trip.verdict is not None:
                    break
                sleep(max(0, tick + 1 / 30 - clock()))
        except RuntimeInterruptedError:
            pass
        finally:
            if conductor is not None and getattr(conductor, "trip", None) is not None:
                conductor.end_trip(
                    "trip time budget exhausted"
                    if seconds is not None and clock() - started >= seconds
                    else "runtime stopped before arrival",
                    clock(),
                )
            try:
                cleanup_runtime(runtime, recording=recording, pipeline=pipeline, logs=(log,))
            finally:
                try:
                    if objects is not None:
                        objects.close()
                finally:
                    if conductor is not None:
                        conductor.close()
                    elif judge is not None:
                        judge.close()
    return {
        "ticks": ticks,
        "elapsed": clock() - started,
        "conflicts": runtime.conflicts,
        "requests": 0 if conductor is None else conductor.request_count,
        **(
            {"trip": conductor.trip.verdict}
            if conductor is not None and getattr(conductor, "trip", None)
            else {}
        ),
    }
