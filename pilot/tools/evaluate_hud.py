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


def longest_run(rows, predicate):
    """Use source ordinals and capture time, never nominal video FPS."""
    best = None
    start = end = None
    count = 0
    for row in rows:
        if predicate(row):
            if end is None or row["source"] != end["source"]:
                start, count = row, 0
            end = row
            count += 1
            duration = end["capture_s"] - start["capture_s"]
            if (
                best is None
                or duration > best["capture_span_s"]
                or (duration == best["capture_span_s"] and count > best["frames"])
            ):
                best = {
                    "source": row["source"],
                    "first_i": start["i"],
                    "last_i": end["i"],
                    "first_capture_s": start["capture_s"],
                    "last_capture_s": end["capture_s"],
                    "frames": count,
                    "capture_span_s": round(duration, 4),
                }
        else:
            start = end = None
            count = 0
    return best


def evaluate_wanted(labels, roots, repeats, full_recordings):
    predictions = []
    timings = []
    for row, rgb in frames(labels, roots):
        hud = read(rgb)
        predictions.append({**row, "actual_wanted": hud.wanted, "actual_screen": hud.screen})
        for _ in range(3):
            read(rgb)
        start = perf_counter_ns()
        for _ in range(repeats):
            read(rgb)
        timings.append((perf_counter_ns() - start) / repeats / 1e6)
    known = [r for r in predictions if r["wanted"] is not None]
    no_stars = [r for r in predictions if not r["stars_present"]]
    errors = [r for r in predictions if r["wanted"] != r["actual_wanted"]]

    def false_positive(r):
        return not r["stars_present"] and (r["actual_wanted"] or 0) > 0

    def missed(r):
        return r["stars_present"] and r["actual_wanted"] in (None, 0)

    result = {
        "labelled_frames": len(predictions),
        "window_500_650_frames": sum(
            r["source"] == "wifi" and 500 <= r["capture_s"] <= 650 for r in predictions
        ),
        "readable_labels": len(known),
        "readable_correct": sum(r["wanted"] == r["actual_wanted"] for r in known),
        "readable_abstentions": sum(r["actual_wanted"] is None for r in known),
        "readable_wrong_counts": sum(
            r["actual_wanted"] is not None and r["actual_wanted"] != r["wanted"] for r in known
        ),
        "unknown_labels": len(predictions) - len(known),
        "unknown_abstentions": sum(r["wanted"] is None and r["actual_wanted"] is None for r in predictions),
        "no_star_labels": len(no_stars),
        "no_star_false_positives": sum(false_positive(r) for r in predictions),
        "no_star_false_positive_rate": sum(false_positive(r) for r in predictions) / len(no_stars),
        "longest_labelled_false_positive_run": longest_run(predictions, false_positive),
        "longest_sampled_star_miss_run": longest_run(predictions, missed),
        "mean_ms": float(np.mean(timings)),
        "p95_frame_mean_ms": float(np.percentile(timings, 95)),
        "repeats_per_frame": repeats,
        "errors": errors,
        "screen_errors": [r for r in predictions if r.get("screen") and r["screen"] != r["actual_screen"]],
    }
    result["by_wanted"] = {}
    for expected in (None, 0, 1, 2, 3, 4, 5):
        group = [r for r in predictions if r["wanted"] == expected]
        result["by_wanted"][str(expected)] = {
            "labels": len(group),
            "correct": sum(r["actual_wanted"] == expected for r in group),
            "abstained": sum(r["actual_wanted"] is None for r in group),
            "wrong_count": sum(
                r["actual_wanted"] is not None and r["actual_wanted"] != expected for r in group
            ),
        }
    if full_recordings:
        scans = {}
        for source, metadata in labels["sources"].items():
            directory = roots[metadata["root"]] / metadata["recording"]
            clock = [json.loads(line) for line in (directory / "frames.jsonl").read_text().splitlines()]
            cap = cv2.VideoCapture(str(directory / "video.mp4"))
            scan = []
            try:
                for ordinal, stamp in enumerate(clock):
                    if stamp["i"] != ordinal:
                        raise ValueError(f"Non-contiguous source ordinal: {source}:{ordinal}")
                    ok, bgr = cap.read()
                    if not ok:
                        raise ValueError(f"Cannot decode {source}:{ordinal}")
                    hud = read(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
                    scan.append(
                        {
                            "source": source,
                            "i": ordinal,
                            "capture_s": round(stamp["t"] - clock[0]["t"], 4),
                            "wanted": hud.wanted,
                            "screen": hud.screen,
                        }
                    )
                if cap.read()[0]:
                    raise ValueError(f"Video has frames absent from clock: {source}")
            finally:
                cap.release()
            clean = source != "wifi"
            fps = [r for r in scan if clean and (r["wanted"] or 0) > 0]
            wasted = [r for r in scan if r["screen"] == "wasted"]
            bad_wasted = [r for r in wasted if clean or not 626 <= r["capture_s"] <= 642]

            # This interval is a manually reviewed source sequence, not an
            # assertion that every damaged decoded frame still exposes stars.
            def star_miss(r):
                return (
                    r["source"] == "wifi" and 535.06 <= r["capture_s"] <= 626.6 and r["wanted"] in (None, 0)
                )

            scans[source] = {
                "frames": len(scan),
                "clean_no_star_frames": len(scan) if clean else 0,
                "no_star_false_positives": fps,
                "no_star_false_positive_rate": len(fps) / len(scan) if clean else None,
                "longest_false_positive_run": longest_run(
                    scan, lambda r: r["source"] != "wifi" and (r["wanted"] or 0) > 0
                ),
                "longest_star_sequence_miss_run": longest_run(scan, star_miss),
                "wanted_counts": dict(Counter(str(r["wanted"]) for r in scan)),
                "screen_counts": dict(Counter(r["screen"] for r in scan)),
                "wasted_frames": wasted,
                "wasted_outside_death_window": bad_wasted,
            }
            print(f"Scanned {source}: {len(scan)} frames", flush=True)
        result["full_recordings"] = scans
    result["passed"] = (
        result["window_500_650_frames"] >= 300
        and result["no_star_labels"] >= 600
        and result["no_star_false_positives"] == 0
        and result["mean_ms"] < 1
        and not result["screen_errors"]
        and all(
            not s["no_star_false_positives"] and not s["wasted_outside_death_window"]
            for s in result.get("full_recordings", {}).values()
        )
    )
    return result


ROOT = Path(__file__).resolve().parents[2]
SCREENS = ("game", "pause", "map", "weapon_wheel", "phone", "failed", "passed", "loading", "wasted")


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
        and not (set(result["missing_screen_classes"]) - {"wasted"})
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, default=ROOT / "lab/hud/labels.json")
    parser.add_argument("--recordings", type=Path, default=ROOT / "recordings")
    parser.add_argument("--clean-recordings", type=Path, default=Path.home() / "recordings/pilot")
    parser.add_argument("--repeats", type=int, default=30)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--wanted", action="store_true", help="Evaluate the P25 wanted corpus")
    parser.add_argument("--full-recordings", action="store_true", help="Scan every source frame")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    if args.full_recordings and not args.wanted:
        parser.error("--full-recordings requires --wanted")
    if args.wanted and args.labels == ROOT / "lab/hud/labels.json":
        args.labels = ROOT / "lab/wanted/labels.json"
    labels = json.loads(args.labels.read_text())
    roots = {"wifi": args.recordings, "clean": args.clean_recordings}
    result = (
        evaluate_wanted(labels, roots, args.repeats, args.full_recordings)
        if args.wanted
        else evaluate(labels, roots, args.repeats)
    )
    output = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(output)
    print(output, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
