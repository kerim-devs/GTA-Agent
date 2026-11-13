"""Reaction approaches: step(RGB frame, capture time, now) -> Decision; close()."""

from __future__ import annotations

import base64
import bisect
import json
import math
import shutil
import tempfile
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path

import cv2
import httpx

from pilot import judge as judge_questions
from pilot.contract import Pad
from pilot.reaction import Decision

REACTION_PROMPT = (
    "Inspect this GTA V frame. Choose the immediate defensive controller action. "
    'Return only JSON: {"action":"neutral|fight|flee|cover","why":"short visible evidence"}. '
    "fight requires a visible hostile person, red hostile minimap blip, or being shot; "
    "flee requires active wanted stars or immediate danger; cover requires incoming gunfire. "
    "Choose neutral when evidence is absent. Never infer enemies outside the image."
)
# The same question in the form judge.py asks its own, under its system prompt: fixed answers and one
# letter back. The JSON question above also asks for a sentence of reasons, which costs tokens and so
# time, and the bench was to time what the pilot would ask.
THREAT_QUESTION = (
    "Is the player character in danger right now?\n"
    "A: no: nobody attacks, no red enemy marker on the minimap, no wanted stars are lit\n"
    "B: enemies: an armed hostile person is in sight or red enemy markers are on the minimap\n"
    "C: police: white wanted stars are lit in the top right corner\n"
    "D: under fire: the character is being shot at or hit right now"
)
THREAT_LETTERS = {"A": "neutral", "B": "fight", "C": "flee", "D": "cover"}
# One letter, with the slack that judge.ask_joint gives each of its answers (two tokens and two over).
LETTER_TOKENS = 4
# The width at which the pilot's judge sends a frame (docs/LOG.md, "The judge, measured").
JUDGE_WIDTH = 640


@dataclass
class Config:
    output: Path = Path("../lab/reaction")
    endpoint: str = "http://127.0.0.1:18762"
    model: str = "delayed-stub"
    timeout: float = 10
    second: bool = False
    codex: bool = False
    modelled_delay: float | None = None
    recording: str | None = None
    question: str = "json"  # "json" (P62's question with reasons) or "letter" (THREAT_QUESTION)
    # A modelled head: the readers' answer, held back this long. Codex had no quota on 12 November,
    # so its delay is taken from what real sessions logged and the row says so.
    head_delay: float | None = None
    # The conductor is given a guard (P65): rules that answer a threat on the same tick.
    guard: bool = False


def action_pad(action: str) -> Pad:
    if action == "fight":
        return Pad(l2=1, r2=1)
    if action == "flee":
        return Pad(buttons=("cross",), left=(0, -1))
    if action == "cover":
        return Pad(buttons=("r1",))
    return Pad()


def image64(frame) -> str:
    height, width = frame.shape[:2]
    small = cv2.resize(frame, (640, round(height * 640 / width)))
    ok, encoded = cv2.imencode(".jpg", cv2.cvtColor(small, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 65])
    if not ok:
        raise ValueError("Cannot encode replay frame")
    return base64.b64encode(encoded).decode()


def letter_answer(choice: dict) -> dict:
    """One letter of THREAT_LETTERS and its probability; anything else is a failed answer."""
    content = choice.get("message", {}).get("content", "")
    letter = content.strip().rstrip(".").upper() if isinstance(content, str) else ""
    if letter not in THREAT_LETTERS:
        raise ValueError(f"judge reply is not one answer letter: {content!r}")
    found = judge_questions.letters(choice)
    top = found[0][1] if len(found) == 1 and found[0][0] == letter else {}
    return {
        "action": THREAT_LETTERS[letter],
        "why": f"answer {letter}",
        "letter": letter,
        "p": judge_questions.probability(letter, top, THREAT_LETTERS),
    }


def request(config: Config, frame, capture: float, *, policy=False) -> dict:
    """Only explicit HTTP endpoints; never connects to a console transport."""
    if not policy:
        # Both questions see the frame as the pilot's judge sends it, so that they differ in the
        # question and the reply only.
        image = judge_questions.encode(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR), JUDGE_WIDTH)
        if config.question == "letter":
            choice, _ = judge_questions.post(
                config.endpoint.rstrip("/"),
                config.model,
                image,
                THREAT_QUESTION,
                LETTER_TOKENS,
                timeout=config.timeout,
            )
            return letter_answer(choice)
    encoded = image64(frame) if policy else image
    if policy:
        payload = {"version": 1, "capture": capture, "image_jpeg_base64": encoded}
        route = "/policy"
    else:
        payload = {
            "model": config.model,
            "temperature": 0,
            "max_tokens": 96,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": REACTION_PROMPT},
                        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + encoded}},
                    ],
                }
            ],
        }
        route = "/v1/chat/completions"
    response = httpx.post(
        config.endpoint.rstrip("/") + route, json=payload, timeout=config.timeout, trust_env=False
    )
    response.raise_for_status()
    data = response.json()
    if policy:
        if data.get("version") != 1 or data.get("capture") != capture:
            raise ValueError("Policy response version/capture does not match the request")
        return data
    content = data["choices"][0]["message"]["content"].strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(content)


def answer_decision(answer: dict, capture: float) -> Decision:
    if "pad" in answer:
        data = answer["pad"]
        pad = Pad(
            buttons=tuple(data.get("buttons", [])),
            left=tuple(data.get("left", (0, 0))),
            right=tuple(data.get("right", (0, 0))),
            l2=float(data.get("l2", 0)),
            r2=float(data.get("r2", 0)),
        )
        if (
            len(pad.left) != 2
            or len(pad.right) != 2
            or any(not math.isfinite(v) or abs(v) > 1 for v in (*pad.left, *pad.right))
            or not 0 <= pad.l2 <= 1
            or not 0 <= pad.r2 <= 1
        ):
            raise ValueError("Policy pad is outside its controller range")
    else:
        action = answer["action"]
        if action not in ("neutral", "fight", "flee", "cover"):
            raise ValueError(f"Unknown model action: {action}")
        pad = action_pad(action)
    return Decision(pad, answer.get("why", "model answer"), judgment_capture=capture, source_capture=capture)


class Judge:
    """One in-flight image request; second variant needs two agreeing replies."""

    def __init__(self, config: Config, transport=None, *, policy=False):
        self.config = config
        self.transport = transport or (lambda frame, capture: request(config, frame, capture, policy=policy))
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.pending = None
        self.latest = Decision()
        self.previous = None
        self.answers = 0
        self.errors = []
        self.submitted_capture = None
        # A policy answers with pads only and says nothing about what it saw.
        self.reports_notice = not policy
        self.named = None
        # Every reply with its frame and how long it took, so that the board can say per answer how
        # fast the model was and whether it was right.
        self.answer_log = []

    def accept(self, answer, capture):
        decision = answer_decision(answer, capture)
        signature = decision.pad
        self.answers += 1
        # Noticed at the first answer that names a threat, whether or not it is believed yet.
        action = answer.get("action")
        self.named = action if action not in (None, "neutral") else None
        if not self.config.second or signature == self.previous:
            self.latest = decision
        else:
            self.latest.judgment_capture = capture
            self.latest.why = "waiting for second agreeing answer"
        self.previous = signature

    def _ask(self, frame, capture, sent):
        started = time.perf_counter()
        try:
            return self.transport(frame, capture), capture, sent, time.perf_counter() - started, None
        except Exception as error:
            return None, capture, sent, time.perf_counter() - started, error

    def step(self, frame, capture, now):
        started = time.perf_counter()
        if self.pending is not None:
            modelled = self.config.modelled_delay is not None
            ready = now >= self.pending[0] if modelled else self.pending.done()
            if ready:
                answer, source, sent, duration, error = (
                    self.pending[1:] if modelled else self.pending.result()
                )
                row = {"capture": source, "sent": sent, "received": now, "duration_s": round(duration, 4)}
                try:
                    if error is not None:
                        raise error
                    self.accept(answer, source)
                    pad_only = "action" not in answer
                    row.update(
                        action=("neutral" if self.latest.pad == Pad() else "pad")
                        if pad_only
                        else answer["action"],
                        letter=answer.get("letter"),
                        p=answer.get("p"),
                    )
                except Exception as failure:
                    self.errors.append(str(failure))
                    self.latest = Decision(why=f"request failed: {type(failure).__name__}")
                    self.named = None
                    row["error"] = f"{type(failure).__name__}: {failure}"[:200]
                self.answer_log.append(row)
                self.pending = None
        if self.pending is None and capture != self.submitted_capture:
            self.submitted_capture = capture
            frozen = frame.copy()
            if self.config.modelled_delay is not None:
                # Explicit simulation uses the same delayed-stub decision, never a claimed model inference.
                answer = stub_answer(frozen)
                delay = self.config.modelled_delay
                self.pending = (now + delay, answer, capture, now, delay, None)
            else:
                self.pending = self.pool.submit(self._ask, frozen, capture, now)
        return replace(
            self.latest,
            stages_ms={"model_poll": (time.perf_counter() - started) * 1000},
            noticed=f"model named {self.named}" if self.named else None,
        )

    def close(self):
        self.pool.shutdown(wait=True, cancel_futures=True)


def stub_answer(frame) -> dict:
    """Deterministic visible-pixel stub, not a model quality claim."""
    from pilot.hud import read

    hud = read(frame)
    from pilot.conductor import minimap_crop
    from pilot.minimap import read as read_map

    reading = read_map(minimap_crop(frame))
    red = any(blip.color == "red" and not blip.border for blip in reading.blips)
    action = "fight" if red else "flee" if hud.wanted else "neutral"
    return {"action": action, "why": "delayed pixel-reader stub"}


class Reflex:
    def __init__(self, config=None):
        from pilot.loop import Pipeline

        self.pipeline = Pipeline()
        self.last_health = None
        self.active = None

    def observe(self, frame, capture, now, text=None):
        from pilot.conductor import minimap_crop
        from pilot.contract import Observation
        from pilot.hud import read

        start = time.perf_counter()
        reading, moving, _ = self.pipeline.step(minimap_crop(frame), capture, feedback=False)
        hud = read(frame, text)
        observation = Observation(time=now, reading=reading, moving=moving, frame=frame, hud=hud)
        return observation, {"readers": (time.perf_counter() - start) * 1000}

    def step(self, frame, capture, now):
        observation, stages = self.observe(frame, capture, now)
        hud = observation.hud
        health = getattr(hud, "health", None)
        hit = health is not None and self.last_health is not None and health < self.last_health - 0.03
        if health is not None:
            self.last_health = health
        red = any(blip.color == "red" and not blip.border for blip in observation.reading.blips)
        start = time.perf_counter()
        if red or hit:
            from pilot.combat import Fight

            if self.active is None:
                self.active = Fight({})
            result = self.active.step(observation)
            pad, why = result.pad, result.reason or "immediate Fight"
            noticed = "red blip" if red else "health fell"
        elif hud.wanted:
            pad, why, noticed = action_pad("flee"), "wanted stars", "wanted stars"
        else:
            self.active = None
            pad, why, noticed = Pad(), "no immediate threat", None
        stages["reflex"] = (time.perf_counter() - start) * 1000
        return Decision(pad, why, stages_ms=stages, noticed=noticed)

    def close(self):
        self.pipeline.close()


class Pilot(Reflex):
    def __init__(self, config: Config, head=None):
        super().__init__(config)
        from pilot.conductor import Conductor
        from pilot.head import ScriptedHead
        from pilot.mission import MissionHead

        config.output.mkdir(parents=True, exist_ok=True)
        self.directory = Path(tempfile.mkdtemp(prefix="scratch-", dir=config.output))
        self.now = 0
        self.trace = []
        self.errors = []
        self.stage_costs = {}
        self.origin = None
        self.modelled = config.modelled_delay is not None
        self.ocr_rows = []
        if config.recording:
            cache = (
                Path("/Users/kerim/recordings/derived/kerim") / Path(config.recording).name / "readings.jsonl"
            )
            if cache.exists():
                self.ocr_rows = [json.loads(line) for line in cache.read_text().splitlines() if line.strip()]
        self.ocr_times = [r["t"] + r["text"].get("elapsed_ms", 0) / 1000 for r in self.ocr_rows]
        # OCR results are external replay inputs, released after their recorded compute cost.
        pairs = sorted(zip(self.ocr_times, self.ocr_rows, strict=True), key=lambda pair: pair[0])
        self.ocr_times = [pair[0] for pair in pairs]
        self.ocr_rows = [pair[1] for pair in pairs]

        def immediate(function, *args):
            def clock():
                return self.now

            class DelayedFuture(Future):
                def done(self):
                    return super().done() and clock() >= self.ready

            future = DelayedFuture() if head is not None else Future()
            if head is not None:
                future.ready = self.now + config.modelled_delay
            try:
                future.set_result(function(*args))
            except Exception as error:
                future.set_exception(error)
            return future

        kwargs = {"submit": immediate} if config.modelled_delay is not None else {}
        self.guard = None
        if config.guard:
            from pilot.guard import Guard

            self.guard = Guard()
        self.conductor = Conductor(
            self.directory,
            head=head or MissionHead(fallback=ScriptedHead()),
            ocr=False,
            clock=lambda: self.now,
            guard=self.guard,
            **kwargs,
        )
        self._timed(self.conductor.detector, "update", "events", trace_if=lambda result: bool(result))
        self._timed(self.conductor, "_hud_events", "hud_events", trace_if=lambda result: bool(result))
        self._timed(self.conductor.head, "decide", "head", trace_if=lambda result: True)
        self._timed(self.conductor.runner, "replace", "plan", trace_if=lambda result: True)
        self._timed(self.conductor.runner, "append", "plan", trace_if=lambda result: True)
        self._timed(self.conductor.runner, "tick", "skill", trace_if=lambda result: False)
        # The pilot notices a threat where its own chain decides because of one: the conductor
        # raises stars or low health as news for the head, or the head picks a rule about a threat.
        # Nothing in it reads a red blip as news; the take-out rule sees one only when asked.
        self.notices = []
        self.notice_lock = threading.Lock()
        self._watch(self.conductor, "_hud_events", threat_event)
        self._watch(self.conductor.head, "decide", lambda result: threat_rule(self.conductor.head))
        original_submit = self.conductor.submit

        def submitted(function, *args):
            self.trace.append(
                {
                    "stage": "request",
                    "t": self.timestamp(),
                    "duration_ms": 0,
                    "detail": "Head request submitted",
                }
            )
            return original_submit(function, *args)

        self.conductor.submit = submitted

    def timestamp(self):
        return self.now if self.modelled else self.origin[0] + time.perf_counter() - self.origin[1]

    def _watch(self, owner, method, check):
        """Note a threat decision as it is made; the head decides on a thread of its own, and the
        next tick reports it."""
        original = getattr(owner, method)

        def watched(*args, **kwargs):
            result = original(*args, **kwargs)
            reason = check(result)
            if reason:
                with self.notice_lock:
                    self.notices.append(reason)
            return result

        setattr(owner, method, watched)

    def take_notice(self):
        with self.notice_lock:
            reason = self.notices[0] if self.notices else None
            self.notices.clear()
        return reason

    def _timed(self, owner, method, stage, trace_if):
        original = getattr(owner, method)

        def timed(*args, **kwargs):
            started = time.perf_counter()
            try:
                result = original(*args, **kwargs)
            except Exception as error:
                self.errors.append(f"{stage}: {type(error).__name__}: {error}")
                raise
            duration = (time.perf_counter() - started) * 1000
            self.stage_costs[stage] = self.stage_costs.get(stage, 0) + duration
            if trace_if(result):
                timestamp = self.timestamp()
                self.trace.append(
                    {"stage": stage, "t": timestamp, "duration_ms": duration, "detail": str(result)[:240]}
                )
            return result

        setattr(owner, method, timed)

    def step(self, frame, capture, now):
        self.now = now
        if self.origin is None:
            self.origin = (now, time.perf_counter())
        self.stage_costs = {}
        kwargs = {}
        index = bisect.bisect_right(self.ocr_times, now) - 1
        if index >= 0:
            row = self.ocr_rows[index]
            text = type(self.conductor.text)(
                **{
                    key: row["text"][key]
                    for key in ("help", "objective", "subtitle", "banner", "phone_menu", "elapsed_ms")
                    if key in row["text"]
                }
            )
            kwargs.update(text=text, text_time=row["t"])
        observation, stages = self.observe(frame, capture, now, kwargs.get("text"))
        if hasattr(self, "change_key"):
            key = (
                tuple((b.color, b.border) for b in observation.reading.blips),
                observation.hud.wanted,
                None if observation.hud.health is None else round(observation.hud.health, 1),
            )
            if key != self.change_key:
                kwargs["events"] = ({"kind": "reaction_picture_changed", "time": capture},)
                self.change_key = key
        start = time.perf_counter()
        result = self.conductor.tick(observation, frame, frame_time=capture, **kwargs)
        stages["events_head_plan_skill"] = (time.perf_counter() - start) * 1000
        stages.update(self.stage_costs)
        noticed = self.take_notice()
        if self.guard is not None:
            # With a guard the row's notice is the guard's rule, on every tick on which one holds the
            # pad or counts while the guard only tells the head.
            verdict = self.conductor.guard_verdict
            noticed = f"guard {verdict.rule}" if verdict is not None and verdict.rule else None
        return Decision(
            result.pad,
            str(getattr(result, "reason", "current pilot skill")),
            stages_ms=stages,
            noticed=noticed,
        )

    @property
    def guard_log(self):
        """The guard's episodes, for the bench's row; None without a guard."""
        return None if self.guard is None else self.guard.episodes

    def close(self):
        self.conductor.close()
        self.pipeline.close()
        shutil.rmtree(self.directory)


THREAT_RULES = ("take_out_fight", "wanted_", "low_health")


def threat_event(events) -> str | None:
    for event in events or ():
        if (event.get("kind") == "wanted_changed" and event.get("wanted")) or event.get(
            "kind"
        ) == "low_health":
            return f"conductor event {event['kind']}"
    return None


def threat_rule(head) -> str | None:
    rule = getattr(head, "last_rule", None) or ""
    if rule.startswith(THREAT_RULES):
        return f"head rule {rule}"
    named = getattr(head, "named", None)
    return f"head named {named}" if named else None


class ModelHead:
    def __init__(self, config):
        self.config = config
        self.named = None

    def decide(self, request_):
        from pilot.head import HeadResponse, SkillCall

        started = time.perf_counter()
        frame = cv2.cvtColor(cv2.imread(str(request_.jpeg_path)), cv2.COLOR_BGR2RGB)
        if self.config.head_delay is not None:
            # What the readers would answer, held back for the modelled time of a head's answer; the
            # conductor runs this on a thread of its own and goes on meanwhile, as it does live.
            answer = stub_answer(frame)
            time.sleep(max(0.0, self.config.head_delay - (time.perf_counter() - started)))
        elif self.config.modelled_delay is not None:
            answer = stub_answer(frame)
        else:
            answer = request(self.config, frame, request_.time or 0)
        action = answer["action"]
        self.named = action if action != "neutral" else None
        name = {"fight": "fight", "flee": "walk", "cover": "fight", "neutral": "wait"}[action]
        args = (
            {"duration": 10, "x": 0, "y": -1, "sprint": True}
            if action == "flee"
            else {"cover": "yes"}
            if action == "cover"
            else {}
        )
        return HeadResponse(plan=(SkillCall(name, args),), sentence=answer.get("why", "model answer"))


class Head(Pilot):
    def __init__(self, config):
        from pilot.head import CodexHead

        super().__init__(config, head=CodexHead() if config.codex else ModelHead(config))
        self.change_key = None


class ReflexJudge:
    def __init__(self, config: Config, reflex=None, judge=None):
        self.reflex = reflex or Reflex(config)
        self.judge = judge or Judge(config)
        self.threat_since = None

    def step(self, frame, capture, now):
        cheap = self.reflex.step(frame, capture, now)
        considered = self.judge.step(frame, capture, now)
        if cheap.pad != Pad():
            if self.threat_since is None:
                self.threat_since = capture
        else:
            self.threat_since = None
        noticed = cheap.noticed or considered.noticed
        if considered.judgment_capture is not None and (
            self.threat_since is None or considered.judgment_capture >= self.threat_since
        ):
            return replace(considered, noticed=noticed)
        return replace(cheap, noticed=noticed)

    def close(self):
        self.reflex.close()
        self.judge.close()

    @property
    def errors(self):
        return self.judge.errors

    @property
    def answer_log(self):
        return self.judge.answer_log


# An additional implementation needs exactly one entry here; the runner is generic.
REGISTRY = {
    "reflex": Reflex,
    "pilot": Pilot,
    "judge": Judge,
    "judge-second": lambda config: Judge(Config(**{**vars(config), "second": True})),
    "head": Head,
    "pilot+guard": lambda config: Pilot(replace(config, guard=True)),
    "head+guard": lambda config: Head(replace(config, guard=True)),
    "reflex+judge": ReflexJudge,
    "policy": lambda config: Judge(config, policy=True),
}


def create(name: str, config: Config):
    return REGISTRY[name](config)
