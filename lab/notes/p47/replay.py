"""Replay stored OCR boxes against local video pixels, without Vision or live services."""

import ast
import json
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path

import cv2
import numpy as np

from pilot.scene import _objective

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = Path(__file__).resolve().parent
RECORDINGS = Path("/Users/kerim/recordings/kerim")
DERIVED = Path("/Users/kerim/recordings/derived/kerim")


def original_classifier():
    source = subprocess.check_output(["git", "show", "926a473:pilot/src/pilot/scene.py"], cwd=ROOT, text=True)
    node = next(
        n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "_objective"
    )
    namespace = {"np": np, "re": re}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "original_scene", "exec"), namespace)
    return namespace["_objective"]


ORIGINAL = original_classifier()


def normal(text):
    return re.sub(r"[^\w]", "", text.casefold())


def replay(directory):
    name = directory.name
    rows = [json.loads(line) for line in (directory / "readings.jsonl").read_text().splitlines()]
    missions = json.loads((directory / "missions.json").read_text())
    steps = [step for mission in missions["missions"] for step in mission["steps"]]
    sections_path = DERIVED / name / "sections.json"
    if not sections_path.exists():
        sections_path = ROOT / "lab/notes/sections" / name / "sections.json"
    sections = json.loads(sections_path.read_text())["sections"] if sections_path.exists() else []
    selected = {row["i"]: row for row in rows}
    changes = {}
    disagreements = {}
    found = {"before": [], "after": []}
    dialogue = []
    cutscenes = []
    durations = {"before": [], "after": []}
    capture = cv2.VideoCapture(str(RECORDINGS / name / "video.mp4"))
    started = time.perf_counter()
    try:
        for index in range(max(selected, default=-1) + 1):
            if not capture.grab():
                raise RuntimeError(f"{name}: cannot decode frame {index}")
            if index not in selected:
                continue
            row = selected[index]
            lines = [line for line in row["text"]["lines"] if line["region"] in ("objective", "subtitle")]
            if not lines:
                continue
            ok, bgr = capture.retrieve()
            if not ok:
                raise RuntimeError(f"{name}: cannot retrieve frame {index}")
            frame = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            labels = {}
            for version, classify in (("before", ORIGINAL), ("after", _objective)):
                tick = time.perf_counter_ns()
                labels[version] = [classify(frame, tuple(line["box"]), line["text"]) for line in lines]
                durations[version].append((time.perf_counter_ns() - tick) / 1e6)
                text = " ".join(
                    line["text"]
                    for line, objective in zip(lines, labels[version], strict=True)
                    if objective and line["confidence"] >= 0.3
                )
                if text:
                    found[version].append({"text": text, "t": row["t"], "i": index})
            for line, before, after in zip(lines, labels["before"], labels["after"], strict=True):
                if before != after:
                    key = (line["text"], before, after)
                    entry = changes.setdefault(
                        key,
                        {
                            "text": line["text"],
                            "before": "objective" if before else "subtitle",
                            "after": "objective" if after else "subtitle",
                            "first_t": row["t"],
                            "first_i": index,
                            "count": 0,
                        },
                    )
                    entry.update(last_t=row["t"], last_i=index, count=entry["count"] + 1)
                if after != (line["region"] == "objective"):
                    key = (line["text"], line["region"], after)
                    entry = disagreements.setdefault(
                        key,
                        {
                            "text": line["text"],
                            "stored": line["region"],
                            "after": "objective" if after else "subtitle",
                            "first_t": row["t"],
                            "first_i": index,
                            "count": 0,
                        },
                    )
                    entry.update(last_t=row["t"], last_i=index, count=entry["count"] + 1)
                    if after and line["confidence"] >= 0.3:
                        dialogue.append({"text": line["text"], "t": row["t"], "i": index})
            if any(s["kind"] == "cutscene" and s["start"] <= row["t"] <= s["end"] for s in sections):
                cutscenes.append(
                    {
                        "t": row["t"],
                        "i": index,
                        "objectives": [
                            line["text"]
                            for line, objective in zip(lines, labels["after"], strict=True)
                            if objective and line["confidence"] >= 0.3
                        ],
                    }
                )
    finally:
        capture.release()
    matched = []
    for step in steps:
        result = {"step": step}
        for version in ("before", "after"):
            candidates = [
                reading
                for reading in found[version]
                if step["start"] - 0.6 <= reading["t"] <= step["last"] + 0.6
            ]
            best = max(
                candidates,
                key=lambda item: SequenceMatcher(
                    None, normal(step["objective"]), normal(item["text"])
                ).ratio(),
                default=None,
            )
            score = (
                SequenceMatcher(None, normal(step["objective"]), normal(best["text"])).ratio() if best else 0
            )
            result[version] = {"found": score >= 0.8, "score": score, "reading": best}
        matched.append(result)
    result = {
        "recording": name,
        "readings": len(rows),
        "known_steps": len(steps),
        "found_before": sum(step["before"]["found"] for step in matched),
        "found_after": sum(step["after"]["found"] for step in matched),
        "steps": matched,
        "changed_labels": list(changes.values()),
        "stored_label_disagreements": list(disagreements.values()),
        "dialogue_candidates": dialogue,
        "cutscene_readings": cutscenes,
        "sections_source": str(sections_path) if sections_path.exists() else None,
        "timing_ms_per_reading_with_bottom_text": {
            version: {
                "count": len(values),
                "mean": float(np.mean(values)),
                "median": float(np.median(values)),
                "p95": float(np.percentile(values, 95)),
            }
            for version, values in durations.items()
        },
        "wall_seconds": time.perf_counter() - started,
    }
    (OUTPUT / f"{name}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        f"{name}: {result['found_before']} -> {result['found_after']} / {len(steps)}; "
        f"{len(changes)} changed texts; {len(dialogue)} stored subtitle promotions",
        flush=True,
    )
    return {
        key: value
        for key, value in result.items()
        if key
        not in (
            "steps",
            "changed_labels",
            "stored_label_disagreements",
            "dialogue_candidates",
            "cutscene_readings",
        )
    }


def benchmark():
    """Isolate classification cost from parallel video decoding and native OCR."""
    directory = ROOT / "lab/notes/out/20261111-165543"
    rows = [json.loads(line) for line in (directory / "readings.jsonl").read_text().splitlines()]
    cases = []
    capture = cv2.VideoCapture(str(RECORDINGS / directory.name / "video.mp4"))
    try:
        for target in (72.8, 221.0, 373.0, 418.0):
            row = min(rows, key=lambda row: abs(row["t"] - target))
            capture.set(cv2.CAP_PROP_POS_FRAMES, row["i"])
            ok, bgr = capture.read()
            if not ok:
                raise RuntimeError(f"Cannot benchmark frame {row['i']}")
            frame = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            lines = [line for line in row["text"]["lines"] if line["region"] in ("objective", "subtitle")]
            if not lines:
                raise RuntimeError(f"No bottom text at {row['t']}")
            timings = {"before": [], "after": []}
            for iteration in range(520):
                versions = [("before", ORIGINAL), ("after", _objective)]
                if iteration % 2:
                    versions.reverse()
                for version, classify in versions:
                    tick = time.perf_counter_ns()
                    for line in lines:
                        classify(frame, tuple(line["box"]), line["text"])
                    elapsed = (time.perf_counter_ns() - tick) / 1e6
                    if iteration >= 20:
                        timings[version].append(elapsed)
            cases.append(
                {
                    "t": row["t"],
                    "i": row["i"],
                    "texts": [line["text"] for line in lines],
                    "milliseconds": {
                        version: {"median": float(np.median(values)), "p95": float(np.percentile(values, 95))}
                        for version, values in timings.items()
                    },
                }
            )
    finally:
        capture.release()
    (OUTPUT / "benchmark.json").write_text(
        json.dumps(
            {"recording": directory.name, "iterations_after_warmup": 500, "cases": cases},
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    directories = sorted(path.parent for path in (ROOT / "lab/notes/out").glob("*/readings.jsonl"))
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(replay, directories))
    (OUTPUT / "summary.json").write_text(json.dumps(results, indent=2) + "\n")
    benchmark()
