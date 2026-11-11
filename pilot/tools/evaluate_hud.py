"""Reproduce P15's labelled-frame evaluation without a console connection."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from time import perf_counter_ns

import cv2
import numpy as np

from pilot.hud import read

ROOT = Path(__file__).resolve().parents[2]
SCREENS = ("game", "pause", "map", "weapon_wheel", "phone", "failed", "passed", "loading")


def frames(labels: dict, roots: dict[str, Path]):
    """Frame ordinals, not nominal video seconds, identify captured pictures."""
    for name, source in labels["sources"].items():
        directory = roots[source["root"]] / source["recording"]
        cap = cv2.VideoCapture(str(directory / "video.mp4"))
        if not cap.isOpened():
            raise ValueError(f"Cannot open {directory / 'video.mp4'}")
        try:
            for row in labels["frames"]:
                if row["source"] != name:
                    continue
                cap.set(cv2.CAP_PROP_POS_FRAMES, row["i"])
                ok, bgr = cap.read()
                if not ok:
                    raise ValueError(f"Cannot decode {name}:{row['i']}")
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                digest = hashlib.sha256(rgb.tobytes()).hexdigest()
                if row.get("rgb_sha256") and row["rgb_sha256"] != digest:
                    raise ValueError(f"Frame content changed: {row['id']}")
                yield row, rgb
        finally:
            cap.release()


def evaluate(labels: dict, roots: dict[str, Path], repeats: int) -> dict:
    confusion = {s: {p: 0 for p in SCREENS} for s in SCREENS}
    misses, health_misses, health_errors, times = [], [], [], []
    groups: dict[str, Counter] = {}
    for row, rgb in frames(labels, roots):
        hud = read(rgb)
        expected = row["screen"]
        confusion[expected][hud.screen] += 1
        group = groups.setdefault(row["selection"], Counter())
        group["count"] += 1
        group["correct"] += expected == hud.screen
        identity = {k: row[k] for k in ("id", "source", "i", "capture_s")}
        if expected != hud.screen:
            misses.append({**identity, "expected": expected, "actual": hud.screen})
        if isinstance(row.get("health"), (float, int)):
            error = None if hud.health is None else abs(hud.health - row["health"])
            health_errors.append(error)
            if error is None or error > 0.05:
                health_misses.append(
                    {**identity, "expected": row["health"], "actual": hud.health, "error": error}
                )
        # Decoding, hashes and warmup are deliberately outside the timed section.
        for _ in range(3):
            read(rgb)
        start = perf_counter_ns()
        for _ in range(repeats):
            read(rgb)
        times.append((perf_counter_ns() - start) / repeats / 1e6)
    total = sum(sum(v.values()) for v in confusion.values())
    games = sum(confusion["game"].values())
    false_stops = games - confusion["game"]["game"]
    available_errors = [e for e in health_errors if e is not None]
    health_hits = sum(e is not None and e <= 0.05 for e in health_errors)
    result = {
        "frames": total,
        "confusion": confusion,
        "groups": groups,
        "screen_accuracy": (total - len(misses)) / total,
        "ordinary_game_frames": games,
        "false_stops": false_stops,
        "false_stop_rate": false_stops / games if games else None,
        "health_labels": len(health_errors),
        "health_within_005": health_hits,
        "health_hit_rate": health_hits / len(health_errors) if health_errors else 0,
        "health_abstentions": sum(e is None for e in health_errors),
        "health_mae_when_read": float(np.mean(available_errors)) if available_errors else None,
        "mean_ms": float(np.mean(times)),
        "p95_frame_mean_ms": float(np.percentile(times, 95)),
        "repeats_per_frame": repeats,
        "misses": misses,
        "health_misses": health_misses,
        "missing_screen_classes": [s for s in SCREENS if not sum(confusion[s].values())],
    }
    result["passed"] = (
        total >= 150
        and len(health_errors) >= 60
        and result["screen_accuracy"] >= 0.95
        and result["false_stop_rate"] is not None
        and result["false_stop_rate"] < 0.01
        and result["health_hit_rate"] >= 0.9
        and result["mean_ms"] < 2.0
        and not result["missing_screen_classes"]
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, default=ROOT / "lab/hud/labels.json")
    parser.add_argument("--recordings", type=Path, default=ROOT / "recordings")
    parser.add_argument("--clean-recordings", type=Path, default=Path.home() / "recordings/pilot")
    parser.add_argument("--repeats", type=int, default=30)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    labels = json.loads(args.labels.read_text())
    result = evaluate(labels, {"wifi": args.recordings, "clean": args.clean_recordings}, args.repeats)
    output = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(output)
    print(output, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
