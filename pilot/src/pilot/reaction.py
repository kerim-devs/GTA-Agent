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


def measure(scene: Scene, samples: list[dict]) -> dict:
    """Score actual decision completion times, never scheduled tick times."""
    matching = [row for row in samples if row["matches"]]
    early = [r for r in matching if scene.onset - 2 <= r["t"] < scene.onset]
    after = [r for r in matching if r["t"] >= scene.onset]
    threat = scene.kind != "calm"
    answer = after[0] if threat and after and not early else None
    reaction = answer["t"] - scene.onset if answer else None
    alarms = 0
    active = False
    for row in samples:
        in_false_window = not threat or scene.onset - 2 <= row["t"] < scene.onset
        false = in_false_window and row["matches"]
        if false and not active:
            alarms += 1
        active = false
    times = [r["decision_s"] for r in samples]
    elapsed = max(scene.stop - scene.begin, samples[-1]["t"] - scene.begin) if samples else 0
    return {
        "reaction_s": reaction,
        "reaction_link_s": reaction + LINK_SECONDS if reaction is not None else None,
        "answered_3s": reaction is not None and reaction <= 3,
        "void_pre_onset": bool(early) if threat else False,
        "false_answers": alarms,
        "false_answer_ticks": sum(r["matches"] for r in samples if not threat or r["t"] < scene.onset),
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
    return {
        "approach": "Kerim",
        "mode": "recorded-human-" + scene.human["lead_source"],
        "scene": asdict(scene),
        "metrics": metrics,
        "samples": samples,
    }


def compact(result: dict) -> dict:
    samples = result.pop("samples")
    result["transitions"] = []
    last = None
    for sample in samples:
        signature = (sample["matches"], sample.get("why"))
        if signature != last:
            result["transitions"].append(sample)
            last = signature
    result["ages_median_s"] = {
        key: percentile([r[key] for r in samples if r.get(key) is not None], 50)
        for key in ("frame_age_s", "detection_age_s", "judgment_age_s", "compute_s")
    }
    result["stage_median_ms"] = {
        key: percentile([r["stages_ms"][key] for r in samples if key in r.get("stages_ms", {})], 50)
        for key in {key for row in samples for key in row.get("stages_ms", {})}
    }
    return result


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


def aggregate(rows: list[dict]) -> dict:
    threats = [r for r in rows if r["scene"]["kind"] != "calm"]
    calm = [r for r in rows if r["scene"]["kind"] == "calm"]
    values = [r["metrics"]["reaction_s"] for r in threats if r["metrics"]["reaction_s"] is not None]
    calm_alarms = sum(r["metrics"]["false_answers"] for r in calm)
    calm_seconds = sum(r["metrics"]["elapsed_s"] for r in calm)
    return {
        "threats": len(threats),
        "calm": len(calm),
        "share_3s": sum(r["metrics"]["answered_3s"] for r in threats) / len(threats) if threats else None,
        "median_s": percentile(values, 50),
        "p90_s": percentile(values, 90),
        "worst_s": max(values) if values else None,
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
    if name not in ("reflex", "pilot", "Kerim") and row.get("model"):
        return f"{name} ({row['model']})"
    return name


def board(rows: list[dict], destination: Path) -> str:
    """Keep modes separate and keep every repetition visible in the timeline."""
    groups = {}
    for row in rows:
        groups.setdefault((approach_label(row), row["mode"]), []).append(row)
    lines = [
        "# First-reaction bench",
        "",
        "Every number inherits the mode in its row. Missing answers are not zero. Reaction statistics include answered, non-void threat scenes only. Repetitions are separate trials. Pilot/head use cached timestamped OCR and no object reader; their measured wall-clock results do not include fresh OCR/object inference. Delayed-stub rows measure a local reader stub, not model quality. The recording never responds to these pads.",  # noqa: E501
        "",
        f"Link addition: {LINK_SECONDS * 1000:.0f} ms; {LINK_SOURCE}.",
        "",
        "| Approach | Mode | Threat/calm trials | Answer ≤3s | Median / p90 / worst ms | With link ms | False alarms | Calm / scene / min | Decision ms | Hz |",  # noqa: E501
        "|---|---|---:|---:|---|---|---:|---|---:|---:|",
    ]

    def number(value, factor=1):
        return "n/a" if value is None else f"{value * factor:.1f}"

    for (name, mode), trials in sorted(groups.items(), key=lambda item: (item[0][0] != "Kerim", item[0])):
        a = aggregate(trials)
        reactions = [a[k] for k in ("median_s", "p90_s", "worst_s")]
        plain = " / ".join(number(v, 1000) for v in reactions)
        linked = " / ".join(number(v + LINK_SECONDS if v is not None else None, 1000) for v in reactions)
        lines.append(
            f"| {name} | {mode} | {a['threats']}/{a['calm']} | {number(a['share_3s'], 100)}% | {plain} | {linked} | {a['false_answers']} | {number(a['calm_false_per_scene'])} / {number(a['calm_false_per_minute'])} | {number(a['decision_median_s'], 1000)} | {number(a['rate_hz'])} |"  # noqa: E501
        )
    lines += [
        "",
        "## Per-scene timeline",
        "",
        "All times below are seconds on the recording clock. Each trial includes onset, Kerim's aligned input and the approach's first valid answer. A void trial has no valid answer.",  # noqa: E501
        "",
        "| Scene / kind | Approach | Mode | Onset | Kerim | Answer | Pre-onset void |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for row in rows:
        scene, metrics = row["scene"], row["metrics"]
        answer = metrics["answer"]
        lines.append(
            f"| {scene['id']} / {scene['kind']} | {row['approach']} | {row['mode']} | {scene['onset']:.3f} | {number(scene['human'].get('answer_t'))} | {number(answer['t'] if answer else None)} | {metrics['void_pre_onset']} |"  # noqa: E501
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
    for scene_id in dict.fromkeys(row["scene"]["id"] for row in rows):
        trials = [row for row in rows if row["scene"]["id"] == scene_id]
        scene = trials[0]["scene"]
        height = 65 + 26 * len(trials)
        rendered.append(
            f'<h2>{html.escape(scene_id)}</h2><svg viewBox="0 0 1000 {height}" role="img" aria-label="Reaction timeline">'  # noqa: E501
        )
        rendered.append(f'<line x1="650" y1="20" x2="650" y2="{height}" stroke="#bd324a"/>')
        rendered.append('<text x="650" y="14" font-size="12">onset (0 s)</text>')
        for index, row in enumerate(trials):
            y = 42 + index * 26
            label = html.escape(approach_label(row) + " / " + row["mode"])
            rendered.append(f'<text x="0" y="{y}" font-size="12">{label}</text>')
            rendered.append(f'<line x1="350" y1="{y - 4}" x2="850" y2="{y - 4}" stroke="#c9d5df"/>')
            answer = row["metrics"]["answer"]
            if answer:
                delay = answer["t"] - scene["onset"]
                x = 650 + max(-6, min(4, delay)) * 50
                rendered.append(
                    f'<circle cx="{x:.2f}" cy="{y - 4}" r="5" fill="#126b98"/><text x="870" y="{y}" font-size="12">{delay:.3f} s</text>'  # noqa: E501
                )
            else:
                status = "pre-onset void" if row["metrics"]["void_pre_onset"] else "no valid answer"
                rendered.append(f'<text x="870" y="{y}" font-size="12">{status}</text>')
        rendered.append("</svg>")
    (destination / "board.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>Reaction bench</title><style>body{font:15px system-ui;margin:32px;color:#152536}table{border-collapse:collapse;margin:24px 0}td{border:1px solid #ccd5df;padding:8px}tr:first-child{font-weight:bold;background:#edf2f7}</style>'  # noqa: E501
        + "".join(rendered)
        + "</html>"
    )
    return content
