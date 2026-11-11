"""Exhaustive offline cable screen evaluation against visually labelled spans."""

from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path
from time import perf_counter_ns
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot/src"))
from pilot.hud import read
from prepare import SOURCES

CLASSES = (
    "game",
    "pause",
    "map",
    "weapon_wheel",
    "phone",
    "interaction_menu",
    "failed",
    "passed",
    "loading",
    "wasted",
)


def runs(values):
    result = []
    for i, value in enumerate(values):
        if not result or result[-1]["screen"] != value:
            result.append({"first": i, "last": i, "screen": str(value)})
        else:
            result[-1]["last"] = i
    return result


def evaluate(root):
    lab = ROOT / "lab/screens"
    labels = json.loads((lab / "labels.json").read_text())
    results = {}
    total_ns = total_frames = 0
    for source, directory in SOURCES.items():
        path = root / directory
        source_labels = labels["sources"][source]
        raw_metadata = (path / "frames.jsonl").read_bytes()
        if hashlib.sha256(raw_metadata).hexdigest() != source_labels["metadata_sha256"]:
            raise ValueError(f"{source}: capture metadata changed")
        metadata = [json.loads(line) for line in raw_metadata.splitlines()]
        if [r["i"] for r in metadata] != list(range(len(metadata))):
            raise ValueError(f"{source}: noncontiguous frame ordinals")
        times = np.array([r["t"] for r in metadata])
        cap = cv2.VideoCapture(str(path / "video.mp4"))
        predicted = []
        ns = 0
        try:
            while True:
                ok, bgr = cap.read()
                if not ok:
                    break
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                start = perf_counter_ns()
                result = read(rgb)
                ns += perf_counter_ns() - start
                predicted.append(result.screen)
        finally:
            cap.release()
        predicted = np.array(predicted)
        if len(predicted) != len(metadata) or len(predicted) != source_labels["frames"]:
            raise ValueError(f"{source}: video/metadata/label lengths differ")
        total_ns += ns
        total_frames += len(predicted)
        expected = np.full(len(predicted), "game", dtype="<U20")
        episodes = []
        previous_last = -1
        for interval in source_labels["intervals"]:
            a, b, screen = interval["first"], interval["last"], interval["screen"]
            if (
                not (previous_last < a <= b < len(predicted))
                or screen not in CLASSES[1:]
            ):
                raise ValueError(
                    f"{source}: invalid or overlapping interval {interval}"
                )
            previous_last = b
            expected[a : b + 1] = screen
            hits = np.flatnonzero(predicted[a : b + 1] == screen)
            episodes.append(
                {
                    **interval,
                    "first_visible_s": float(times[a]),
                    "last_visible_s": float(times[b]),
                    "frames": b - a + 1,
                    "hits": len(hits),
                    "first_detection": int(a + hits[0]) if len(hits) else None,
                    "delay_ms": float((times[a + hits[0]] - times[a]) * 1000)
                    if len(hits)
                    else None,
                }
            )
        normal = expected == "game"
        false = np.flatnonzero(normal & (predicted != "game"))
        result = {
            "frames": len(predicted),
            "mean_ms": ns / len(predicted) / 1e6,
            "prediction_counts": dict(Counter(predicted)),
            "non_game_runs": [r for r in runs(predicted) if r["screen"] != "game"],
            "ordinary_frames": int(normal.sum()),
            "false_stops": [
                {"i": int(i), "capture_s": float(times[i]), "actual": str(predicted[i])}
                for i in false
            ],
            "episodes": episodes,
            "classes": {
                c: {
                    "visible_frames": int((expected == c).sum()),
                    "hits": int(((expected == c) & (predicted == c)).sum()),
                }
                for c in CLASSES[1:]
                if (expected == c).any()
            },
            "misses": [
                {
                    "i": int(i),
                    "capture_s": float(times[i]),
                    "expected": str(expected[i]),
                    "actual": str(predicted[i]),
                }
                for i in np.flatnonzero(~normal & (predicted != expected))
            ],
        }
        results[source] = result
        print(
            f"{source}: {len(predicted)} frames, {len(false)} false stops", flush=True
        )
    output = {
        "sources": results,
        "frames": total_frames,
        "mean_ms": total_ns / total_frames / 1e6,
        "ordinary_frames": sum(r["ordinary_frames"] for r in results.values()),
        "false_stop_count": sum(len(r["false_stops"]) for r in results.values()),
        "missing_cable_classes": ["failed", "passed", "wasted"],
        "hud_sha256": hashlib.sha256(
            (ROOT / "pilot/src/pilot/hud.py").read_bytes()
        ).hexdigest(),
        "labels_sha256": hashlib.sha256((lab / "labels.json").read_bytes()).hexdigest(),
    }
    output["passed"] = (
        output["false_stop_count"] == 0
        and output["mean_ms"] < 1
        and all(e["hits"] > 0 for r in results.values() for e in r["episodes"])
    )
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.home() / "recordings")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "lab/screens/evaluation.json"
    )
    args = parser.parse_args()
    result = evaluate(args.root)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "sources"}, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
