"""Offline first-reaction measurements. No console or feedback transport."""

from __future__ import annotations

import bisect
import hashlib
import html
import json
import platform
import subprocess
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cv2
import numpy as np

from pilot.contract import Pad

LINK_SECONDS = 0.135
LINK_SOURCE = "docs/LOG.md:15: camera measurement, 60 fps, 10 samples, median 135 ms"


@dataclass
class Scene:
    id: str
    recording: str
    onset: float
    kind: str
    answers: list[dict] = field(default_factory=list)
    onset_method: str = "unverified"
    confidence: str = "unverified"
    uncertainty_frames: int = 0
    start: float | None = None
    end: float | None = None
    human: dict = field(default_factory=dict)
    notes: str = ""
    # How long before the onset the picture held no threat (no red marker, no stars), up to six
    # seconds: a model that calls a threat there is wrong. None means not measured.
    calm_before_s: float | None = None

    @property
    def begin(self) -> float:
        return self.onset - 6 if self.start is None else self.start

    @property
    def stop(self) -> float:
        return self.onset + 4 if self.end is None else self.end


@dataclass
class Decision:
    pad: Pad = field(default_factory=Pad)
    why: str = "neutral"
    detection_capture: float | None = None
    judgment_capture: float | None = None
    stages_ms: dict[str, float] = field(default_factory=dict)
    source_capture: float | None = None
    # Set by the approach itself on every tick on which it decides something because of a threat,
    # whether or not the pad answers yet: Fight turns towards a blip before it aims, and a replayed
    # picture never turns, so the pad alone would call a threat that was seen at once unanswered.
    noticed: str | None = None


def matches(pad: Pad, answers: list[dict]) -> bool:
    """OR of explicitly named input sets, AND within each input set."""
    for answer in answers:
        conditions = []
        for key, value in answer.items():
            if key == "why":
                continue
            if key == "buttons":
                conditions.append(set(value).issubset(pad.buttons))
            elif key in ("l2", "r2"):
                conditions.append(getattr(pad, key) >= value)
            elif key in ("left_x", "left_y", "right_x", "right_y"):
                stick, axis = key.split("_")
                actual = getattr(pad, stick)[0 if axis == "x" else 1]
                conditions.append(actual >= value if value >= 0 else actual <= value)
            else:
                raise ValueError(f"Unknown answer predicate: {key}")
        if conditions and all(conditions):
            return True
    return False


def load_scenes(path: Path) -> list[Scene]:
    data = json.loads(path.read_text())
    scenes = [
        Scene(**{**row, "answers": row.get("answers", data.get("answer_sets", {}).get(row["kind"], []))})
        for row in data["scenes"]
    ]
    if len({s.id for s in scenes}) != len(scenes):
        raise ValueError("Duplicate scene id")
    for scene in scenes:
        if scene.uncertainty_frames > 2 or scene.confidence == "unverified":
            raise ValueError(f"Unverified onset: {scene.id}")
        if scene.begin < 0 or scene.stop <= scene.onset or not scene.answers:
            raise ValueError(f"Invalid scene window/answers: {scene.id}")
    return scenes


def percentile(values: list[float], q: float) -> float | None:
    return float(np.percentile(values, q)) if values else None


def first_after_onset(scene: Scene, samples: list[dict], key) -> tuple[dict | None, bool, int]:
    """The first sample at or after the onset for which `key` holds, the pre-onset veto, and the
    false episodes: a state held in the two seconds before the onset voids the try and counts as
    false, as does every episode on a calm scene."""
    threat = scene.kind != "calm"
    early = [r for r in samples if key(r) and scene.onset - 2 <= r["t"] < scene.onset]
    after = [r for r in samples if key(r) and r["t"] >= scene.onset]
    first = after[0] if threat and after and not early else None
    episodes = 0
    active = False
    for row in samples:
        in_false_window = not threat or scene.onset - 2 <= row["t"] < scene.onset
        false = in_false_window and key(row)
        if false and not active:
            episodes += 1
        active = false
    return first, bool(early) if threat else False, episodes


def measure(scene: Scene, samples: list[dict]) -> dict:
    """Score actual decision completion times, never scheduled tick times.

    Two times per try: "answered" is the first pad from the scene's answer set, "noticed" the first
    tick on which the approach says it decided something because of a threat (Decision.noticed).
    """
    threat = scene.kind != "calm"
    answer, void, alarms = first_after_onset(scene, samples, lambda r: r["matches"])
    reaction = answer["t"] - scene.onset if answer else None
    notice, notice_void, false_notices = first_after_onset(scene, samples, lambda r: bool(r.get("noticed")))
    noticed = notice["t"] - scene.onset if notice else None
    times = [r["decision_s"] for r in samples]
    elapsed = max(scene.stop - scene.begin, samples[-1]["t"] - scene.begin) if samples else 0
    return {
        "reaction_s": reaction,
        "reaction_link_s": reaction + LINK_SECONDS if reaction is not None else None,
        "answered_3s": reaction is not None and reaction <= 3,
        "void_pre_onset": void,
        "false_answers": alarms,
        "false_answer_ticks": sum(r["matches"] for r in samples if not threat or r["t"] < scene.onset),
        "noticed_s": noticed,
        "noticed_3s": noticed is not None and noticed <= 3,
        "notice_void_pre_onset": notice_void,
        "false_notices": false_notices,
        "notice": notice,
        "decision_median_s": percentile(times, 50),
        "decision_p90_s": percentile(times, 90),
        "decision_rate_hz": len(samples) / elapsed if elapsed else 0,
        "elapsed_s": elapsed,
        "decisions": len(samples),
        "answer": answer,
    }


class Recording:
    """Read-only sequential decoder with timestamps from frames.jsonl."""

    def __init__(self, path: str):
        root = Path(path)
        self.rows = [
            json.loads(line) for line in (root / "frames.jsonl").read_text().splitlines() if line.strip()
        ]
        videos = sorted(root.glob("*.mp4"))
        if len(videos) != 1:
            raise ValueError(f"Expected one mp4 in {root}, got {len(videos)}")
        self.cap = cv2.VideoCapture(str(videos[0]))
        self.index = -1
        self.frame = None
        self.capture = None

    def at(self, timestamp: float):
        if self.index == -1:
            first = max(0, bisect.bisect_right([row["t"] for row in self.rows], timestamp) - 1)
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.rows[first]["i"])
            self.index = first - 1
        while self.index + 1 < len(self.rows) and self.rows[self.index + 1]["t"] <= timestamp:
            ok, frame = self.cap.read()
            if not ok:
                raise ValueError(f"Recording ended at frame {self.index + 1}")
            self.index += 1
            self.frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.capture = self.rows[self.index]["t"]
        if self.frame is None:
            raise ValueError("No captured frame at scene start")
        return self.frame, self.capture

    def close(self):
        self.cap.release()


def replay(
    scene: Scene,
    approach,
    *,
    mode: str = "realtime",
    cost_s: float | None = None,
    recording=None,
    clock: Callable[[], float] = time.perf_counter,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    if mode not in ("realtime", "modelled"):
        raise ValueError("mode must be realtime or modelled")
    if mode == "modelled" and (cost_s is None or cost_s <= 0):
        raise ValueError("Modelled replay requires a positive measured cost")
    source = recording or Recording(scene.recording)
    samples = []
    try:
        source.at(scene.begin)  # Decode pre-roll before starting the measured clock.
        anchor = clock()
        tick = scene.begin
        while tick < scene.stop:
            if mode == "realtime":
                sleep(max(0, tick - scene.begin - (clock() - anchor)))
                now = scene.begin + clock() - anchor
                if now >= scene.stop:
                    break
            else:
                now = tick
            frame, capture = source.at(now)
            decision = approach.step(frame, capture, now)
            done = scene.begin + clock() - anchor if mode == "realtime" else now + cost_s
            samples.append(
                {
                    "t": done,
                    "capture": capture,
                    "pad": asdict(decision.pad),
                    "why": decision.why,
                    "noticed": decision.noticed,
                    "matches": matches(decision.pad, scene.answers),
                    "decision_s": max(
                        0, done - (capture if decision.source_capture is None else decision.source_capture)
                    ),
                    "frame_age_s": max(0, done - capture),
                    "detection_age_s": None
                    if decision.detection_capture is None
                    else max(0, done - decision.detection_capture),
                    "judgment_age_s": None
                    if decision.judgment_capture is None
                    else max(0, done - decision.judgment_capture),
                    "compute_s": done - now,
                    "stages_ms": decision.stages_ms,
                }
            )
            # Missed deadlines are skipped. Do not replay old frames to catch up.
            tick = max(tick + 1 / 30, done)
    finally:
        source.close()
        approach.close()
    return {
        "scene": asdict(scene),
        "mode": mode,
        "metrics": measure(scene, samples),
        "samples": samples,
        "chain": getattr(approach, "trace", []),
        "errors": getattr(approach, "errors", []),
        # A policy gives pads and nothing else; its "noticed" is unknown, not never.
        "reports_notice": getattr(approach, "reports_notice", True),
        "model_answers": list(getattr(approach, "answer_log", [])),
    }


def human_result(scene: Scene) -> dict:
    """Hold human states between pad changes, aligned to the picture clock."""
    lead = scene.human["lead_s"]
    rows = [
        json.loads(line)
        for line in (Path(scene.recording) / "pad.jsonl").read_text().splitlines()
        if line.strip()
    ]
    human_rows = [r for r in rows if r.get("src") == "human"]
    samples = []
    prior = None
    for row in human_rows:
        aligned = row["t"] + lead
        if aligned <= scene.begin:
            prior = row
            continue
        if prior is not None and not samples:
            pad = Pad(**{k: prior[k] for k in ("buttons", "left", "right", "l2", "r2")})
            samples.append(
                {
                    "t": scene.begin,
                    "matches": matches(pad, scene.answers),
                    "decision_s": 0,
                    "pad": asdict(pad),
                }
            )
        if aligned > scene.stop:
            break
        pad = Pad(**{k: row[k] for k in ("buttons", "left", "right", "l2", "r2")})
        samples.append(
            {"t": aligned, "matches": matches(pad, scene.answers), "decision_s": 0, "pad": asdict(pad)}
        )
    # Inject held states at scoring boundaries, not only state-change events.
    for boundary in (scene.onset - 2, scene.onset):
        previous = [r for r in samples if r["t"] <= boundary]
        if previous:
            samples.append({**previous[-1], "t": boundary})
            samples.sort(key=lambda r: r["t"])
    metrics = measure(scene, samples)
    metrics["decision_median_s"] = None
    metrics["decision_p90_s"] = None
    metrics["decisions"] = 0
    metrics["decision_rate_hz"] = None
    # For Kerim only the pad exists: nothing says when he saw the threat.
    metrics["noticed_s"] = None
    metrics["noticed_3s"] = False
    metrics["false_notices"] = 0
    loose = first_new_press(scene, samples)
    metrics["loose_reaction_s"] = loose["t"] - scene.onset if loose else None
    metrics["loose_answer"] = loose
    return {
        "approach": "Kerim",
        "mode": "recorded-human-" + scene.human["lead_source"],
        "scene": asdict(scene),
        "metrics": metrics,
        "samples": samples,
        "reports_notice": False,
    }


def first_new_press(scene: Scene, samples: list[dict]) -> dict | None:
    """The looser reading of Kerim's reaction: his first answering input that is pressed anew after
    the onset, even while another one is held from before. Held inputs void the strict reading,
    which then says nothing; this one says when his hand changed, not that the change answered."""
    if scene.kind == "calm":
        return None
    previous = None
    for row in samples:
        if previous is not None and scene.onset <= row["t"] <= scene.stop:
            now, before = Pad(**_pad_fields(row["pad"])), Pad(**_pad_fields(previous["pad"]))
            for answer in scene.answers:
                if matches(now, [answer]) and not matches(before, [answer]):
                    return {"t": row["t"], "why": answer.get("why", ""), "pad": row["pad"]}
        previous = row
    return None


def _pad_fields(pad: dict) -> dict:
    return {
        "buttons": tuple(pad["buttons"]),
        "left": tuple(pad["left"]),
        "right": tuple(pad["right"]),
        "l2": pad["l2"],
        "r2": pad["r2"],
    }


def compact(result: dict) -> dict:
    samples = result.pop("samples")
    scene = result["scene"]
    # Sixty scenes and a dozen ways of control share lab/reaction's 5 MB: a row keeps what the board
    # and an audit of the scoring need, and the scene file's hash points to the rest of the scene.
    result["scene"] = {key: scene[key] for key in SCENE_KEYS if key in scene}
    result["scene"]["human"] = {key: scene["human"][key] for key in HUMAN_KEYS if key in scene["human"]}
    # Transitions from just before the pre-onset veto on; on a calm scene all of them.
    since = scene["onset"] - 2.5 if scene["kind"] != "calm" else float("-inf")
    result["transitions"] = []
    last = None
    for sample in samples:
        # A change of answering or noticing, with the reason at that tick: the skills' reasons change
        # on every tick and made a pilot row 17 kB.
        signature = (sample["matches"], sample.get("noticed"))
        if sample["t"] >= since and (signature != last or not result["transitions"]):
            result["transitions"].append(
                {k: _round(v) for k, v in sample.items() if k != "stages_ms" and v is not None}
            )
        last = signature
    result["model_answers"] = [
        {k: _round(v) for k, v in row.items() if v is not None} for row in result.get("model_answers", [])
    ]
    result["ages_median_s"] = {
        key: percentile([r[key] for r in samples if r.get(key) is not None], 50)
        for key in ("frame_age_s", "detection_age_s", "judgment_age_s", "compute_s")
    }
    result["stage_median_ms"] = {
        key: percentile([r["stages_ms"][key] for r in samples if key in r.get("stages_ms", {})], 50)
        for key in {key for row in samples for key in row.get("stages_ms", {})}
    }
    return result


SCENE_KEYS = (
    "id",
    "recording",
    "onset",
    "kind",
    "start",
    "end",
    "uncertainty_frames",
    "calm_before_s",
    "human",
)
HUMAN_KEYS = ("lead_s", "lead_source", "answer_t", "loose_t")


def _round(value):
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, dict):
        return {k: _round(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_round(v) for v in value]
    return value


def provenance(root: Path) -> dict:
    def git(*args):
        result = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=True)
        return result.stdout.strip()

    return {
        "commit": git("rev-parse", "HEAD"),
        "dirty": bool(git("status", "--porcelain")),
        "implementation_sha256": implementation_hash(root),
        "machine": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "python": platform.python_version(),
        },
        "link_s": LINK_SECONDS,
        "link_source": LINK_SOURCE,
    }


def implementation_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for name in ("pilot/src/pilot/reaction.py", "pilot/src/pilot/approaches.py", "pilot/tools/reaction.py"):
        digest.update((root / name).read_bytes())
    return digest.hexdigest()


def append_result(path: Path, result: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        stream.write(json.dumps(result, separators=(",", ":")) + "\n")


def aggregate(rows: list[dict], key: str = "reaction_s") -> dict:
    """`key` picks the time: reaction_s (answered), noticed_s, or Kerim's loose_reaction_s."""
    threats = [r for r in rows if r["scene"]["kind"] != "calm"]
    calm = [r for r in rows if r["scene"]["kind"] == "calm"]
    values = [r["metrics"].get(key) for r in threats if r["metrics"].get(key) is not None]
    noticed = [r["metrics"].get("noticed_s") for r in threats if r["metrics"].get("noticed_s") is not None]
    calm_alarms = sum(r["metrics"]["false_answers"] for r in calm)
    calm_seconds = sum(r["metrics"]["elapsed_s"] for r in calm)
    return {
        "threats": len(threats),
        "calm": len(calm),
        "share_3s": sum(r["metrics"].get(key) is not None and r["metrics"][key] <= 3 for r in threats)
        / len(threats)
        if threats
        else None,
        "median_s": percentile(values, 50),
        "p90_s": percentile(values, 90),
        "worst_s": max(values) if values else None,
        "reports_notice": all(r.get("reports_notice", True) for r in rows),
        "noticed_share_3s": sum(r["metrics"].get("noticed_3s", False) for r in threats) / len(threats)
        if threats
        else None,
        "noticed_median_s": percentile(noticed, 50),
        "noticed_p90_s": percentile(noticed, 90),
        "noticed_worst_s": max(noticed) if noticed else None,
        "false_notices": sum(r["metrics"].get("false_notices", 0) for r in rows),
        "false_answers": sum(r["metrics"]["false_answers"] for r in rows),
        "calm_false_per_scene": calm_alarms / len(calm) if calm else None,
        "calm_false_per_minute": calm_alarms / (calm_seconds / 60) if calm_seconds else None,
        "decision_median_s": percentile(
            [
                r["metrics"]["decision_median_s"]
                for r in rows
                if r["metrics"]["decision_median_s"] is not None
            ],
            50,
        ),
        "rate_hz": sum(r["metrics"]["decisions"] for r in rows) / sum(r["metrics"]["elapsed_s"] for r in rows)
        if rows and any(r["metrics"].get("decision_rate_hz") is not None for r in rows)
        else None,
    }


def approach_label(row: dict) -> str:
    name = row["approach"]
    if name in ("reflex", "pilot", "Kerim"):
        return name
    parts = [row["model"]] if row.get("model") else []
    if row.get("question"):
        parts.append(row["question"] + " question")
    if row.get("head_delay_s") is not None:
        parts.append(f"head delay {row['head_delay_s']:.2f} s")
    return f"{name} ({', '.join(parts)})" if parts else name


def answer_stats(rows: list[dict]) -> dict | None:
    """What a model said, answer by answer: how long each took and whether it was right.

    On a threat scene the model names the threat when an answer about a frame from the onset on is
    anything but neutral; "answers" counts how many answers about such frames that took. On calm
    scenes, and on the calm part of the six seconds before each onset (Scene.calm_before_s), every
    answer that is not neutral calls a threat where there is none.
    """
    answers = [a for r in rows for a in r.get("model_answers", [])]
    if not answers:
        return None
    durations = [a["duration_s"] for a in answers if a.get("error") is None]
    threats = [r for r in rows if r["scene"]["kind"] != "calm"]
    named, needed = 0, []
    calm_calls = calm_total = lead_calls = lead_total = 0
    for row in rows:
        onset = row["scene"]["onset"]
        good = [a for a in row.get("model_answers", []) if a.get("error") is None]
        if row["scene"]["kind"] == "calm":
            calm_total += len(good)
            calm_calls += sum(a["action"] != "neutral" for a in good)
            continue
        calm_before = row["scene"].get("calm_before_s")
        lead = 6 if calm_before is None else min(6, calm_before)
        before = [a for a in good if onset - lead <= a["capture"] < onset]
        lead_total += len(before)
        lead_calls += sum(a["action"] != "neutral" for a in before)
        after = sorted((a for a in good if a["capture"] >= onset), key=lambda a: a["capture"])
        for index, answer in enumerate(after, 1):
            if answer["action"] != "neutral":
                named += 1
                needed.append(index)
                break
    return {
        "answers": len(answers),
        "errors": sum(a.get("error") is not None for a in answers),
        "answer_median_s": percentile(durations, 50),
        "answer_p90_s": percentile(durations, 90),
        "answer_worst_s": max(durations) if durations else None,
        "named_share": named / len(threats) if threats else None,
        "named_needed_median": percentile(needed, 50),
        "calm_false_share": calm_calls / calm_total if calm_total else None,
        "lead_false_share": lead_calls / lead_total if lead_total else None,
        "calm_answers": calm_total,
        "lead_answers": lead_total,
    }


def board(rows: list[dict], destination: Path, provenance_line: str = "") -> str:
    """Keep modes separate and keep every repetition visible in the timeline."""
    groups = {}
    for row in rows:
        groups.setdefault((approach_label(row), row["mode"]), []).append(row)
    lines = [
        "# First-reaction bench",
        "",
        "Every number inherits the mode in its row. Two times per try: noticed is the first tick on which the way of control decides anything because of the threat, by its own account; answered is the first pad from the scene's answer set. For Kerim only the pad exists. Missing answers are not zero. Time statistics include noticed or answered, non-void threat scenes only; a state held in the two seconds before the onset voids the try. Repetitions are separate trials. Pilot/head use cached timestamped OCR and no object reader; their measured wall-clock results do not include fresh OCR/object inference. Delayed-stub rows measure a local reader stub, not model quality. A head delay row runs in real time with a head answer delayed by a modelled time. The recording never responds to these pads.",  # noqa: E501
        "",
        f"Link addition: {LINK_SECONDS * 1000:.0f} ms; {LINK_SOURCE}. {provenance_line}".rstrip(),
        "",
        "| Approach | Mode | Threat/calm trials | Noticed ≤3s | Noticed median / p90 / worst ms | Answered ≤3s | Answered median / p90 / worst ms | Answered with link ms | False notices | False answers | Calm / scene / min | Decision ms | Hz |",  # noqa: E501
        "|---|---|---:|---:|---|---:|---|---|---:|---:|---|---:|---:|",
    ]

    def number(value, factor=1):
        return "n/a" if value is None else f"{value * factor:.1f}"

    def times(a, prefix=""):
        return " / ".join(number(a[f"{prefix}{k}"], 1000) for k in ("median_s", "p90_s", "worst_s"))

    def table_row(name, mode, a, *, notices=True, noticed_cells=None):
        reactions = [a[k] for k in ("median_s", "p90_s", "worst_s")]
        linked = " / ".join(number(v + LINK_SECONDS if v is not None else None, 1000) for v in reactions)
        if noticed_cells is None:
            noticed_cells = (
                (f"{number(a['noticed_share_3s'], 100)}%", times(a, "noticed_"), str(a["false_notices"]))
                if notices
                else ("n/a", "n/a", "n/a")
            )
        return f"| {name} | {mode} | {a['threats']}/{a['calm']} | {noticed_cells[0]} | {noticed_cells[1]} | {number(a['share_3s'], 100)}% | {times(a)} | {linked} | {noticed_cells[2]} | {a['false_answers']} | {number(a['calm_false_per_scene'])} / {number(a['calm_false_per_minute'])} | {number(a['decision_median_s'], 1000)} | {number(a['rate_hz'])} |"  # noqa: E501

    ordered = sorted(groups.items(), key=lambda item: (item[0][0] != "Kerim", item[0]))
    for (name, mode), trials in ordered:
        a = aggregate(trials)
        lines.append(table_row(name, mode, a, notices=a["reports_notice"]))
        if name == "Kerim":
            loose = aggregate(trials, "loose_reaction_s")
            lines.append(
                table_row(
                    "Kerim, looser reading: first new press after the onset",
                    mode,
                    loose,
                    noticed_cells=("n/a", "n/a", "n/a"),
                )
            )
    stats = [(name, mode, answer_stats(trials)) for (name, mode), trials in ordered]
    stats = [item for item in stats if item[2] is not None]
    if stats:
        lines += [
            "",
            "## Model answers",
            "",
            "One line per way of control that asks a model. Time per answer is from the request to the reply. Named: the share of threat scenes on which an answer about a frame from the onset on names any threat, and the median number of such answers it took. False calls: the share of answers that call a threat on calm scenes and on the six seconds before each onset.",  # noqa: E501
            "",
            "| Approach | Mode | Answers (errors) | Per answer median / p90 / worst ms | Threat named | Answers to name it | False calls calm | False calls before onset |",  # noqa: E501
            "|---|---|---:|---|---:|---:|---:|---:|",
        ]
        for name, mode, s in stats:
            lines.append(
                f"| {name} | {mode} | {s['answers']} ({s['errors']}) | {number(s['answer_median_s'], 1000)} / {number(s['answer_p90_s'], 1000)} / {number(s['answer_worst_s'], 1000)} | {number(s['named_share'], 100)}% | {number(s['named_needed_median'])} | {number(s['calm_false_share'], 100)}% of {s['calm_answers']} | {number(s['lead_false_share'], 100)}% of {s['lead_answers']} |"  # noqa: E501
            )
    lines += [
        "",
        "## Per-scene timeline",
        "",
        "All times below are seconds on the recording clock. Each trial includes onset, Kerim's aligned input under both readings, and the approach's first notice and first valid answer. A void trial has no valid answer.",  # noqa: E501
        "",
        "| Scene / kind | Approach | Mode | Onset | Kerim | Kerim looser | Noticed | Answered | Pre-onset void |",  # noqa: E501
        "|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    # Kerim's times come from his own row of the scene, so that every row of it shows them.
    human = {row["scene"]["id"]: row["scene"]["human"] for row in rows if row["approach"] == "Kerim"}
    for row in rows:
        scene, metrics = row["scene"], row["metrics"]
        answer = metrics["answer"]
        notice = metrics.get("notice")
        kerim = human.get(scene["id"], scene["human"])
        lines.append(
            f"| {scene['id']} / {scene['kind']} | {approach_label(row)} | {row['mode']} | {scene['onset']:.3f} | {number(kerim.get('answer_t'))} | {number(kerim.get('loose_t'))} | {number(notice['t'] if notice else None)} | {number(answer['t'] if answer else None)} | {metrics['void_pre_onset']} |"  # noqa: E501
        )
    content = "\n".join(lines) + "\n"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "board.md").write_text(content)
    # Standalone HTML with actual tables, no CDN or JS dependency.
    rendered = []
    in_table = False
    for line in lines:
        if line.startswith("|---"):
            continue
        if line.startswith("|"):
            if not in_table:
                rendered.append("<table>")
                in_table = True
            rendered.append(
                "<tr>"
                + "".join(f"<td>{html.escape(cell.strip())}</td>" for cell in line.strip("|").split("|"))
                + "</tr>"
            )
        else:
            if in_table:
                rendered.append("</table>")
                in_table = False
            rendered.append(f"<p>{html.escape(line.lstrip('# '))}</p>")
    if in_table:
        rendered.append("</table>")
    rendered.append(
        "<p>Timelines: a ring is the first notice, a dot the first answer, the red line the onset.</p>"
    )
    for scene_id in dict.fromkeys(row["scene"]["id"] for row in rows):
        trials = [row for row in rows if row["scene"]["id"] == scene_id]
        scene = trials[0]["scene"]
        height = 65 + 26 * len(trials)
        rendered.append(
            f'<h2>{html.escape(scene_id)}</h2><svg viewBox="0 0 1150 {height}" role="img" aria-label="Reaction timeline">'  # noqa: E501
        )
        rendered.append(f'<line x1="650" y1="20" x2="650" y2="{height}" stroke="#bd324a"/>')
        rendered.append('<text x="650" y="14" font-size="12">onset (0 s)</text>')
        for index, row in enumerate(trials):
            y = 42 + index * 26
            label = html.escape(approach_label(row) + " / " + row["mode"])
            rendered.append(f'<text x="0" y="{y}" font-size="12">{label}</text>')
            rendered.append(f'<line x1="350" y1="{y - 4}" x2="850" y2="{y - 4}" stroke="#c9d5df"/>')
            notice = row["metrics"].get("notice")
            if notice:
                x = 650 + max(-6, min(4, notice["t"] - scene["onset"])) * 50
                rendered.append(
                    f'<circle cx="{x:.2f}" cy="{y - 4}" r="6" fill="none" stroke="#126b98" stroke-width="2"/>'
                )
            answer = row["metrics"]["answer"]
            if answer:
                delay = answer["t"] - scene["onset"]
                x = 650 + max(-6, min(4, delay)) * 50
                rendered.append(
                    f'<circle cx="{x:.2f}" cy="{y - 4}" r="5" fill="#126b98"/><text x="870" y="{y}" font-size="12">{delay:.3f} s</text>'  # noqa: E501
                )
            else:
                status = "pre-onset void" if row["metrics"]["void_pre_onset"] else "no valid answer"
                if notice:
                    status = f"noticed {notice['t'] - scene['onset']:.3f} s; {status}"
                rendered.append(f'<text x="870" y="{y}" font-size="12">{html.escape(status)}</text>')
        rendered.append("</svg>")
    (destination / "board.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>Reaction bench</title><style>body{font:15px system-ui;margin:32px;color:#152536}table{border-collapse:collapse;margin:24px 0}td{border:1px solid #ccd5df;padding:8px}tr:first-child{font-weight:bold;background:#edf2f7}</style>'  # noqa: E501
        + "".join(rendered)
        + "</html>"
    )
    return content
