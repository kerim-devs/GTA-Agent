"""Freeze a seeded recording sample, render overlays, and score visual labels."""

import argparse
import hashlib
import json
import random
import time
from pathlib import Path

import cv2
import numpy as np

from pilot.minimap import ARROW_XY, read
from pilot.roam import read_road


def fingerprint(road):
    value = None if road is None else road.path
    return hashlib.sha256(json.dumps(value).encode()).hexdigest()[:16]


def select(data, out, seed, count):
    crops = np.load(data / "crops.npy", mmap_mode="r")
    meta = json.loads((data / "meta.json").read_text())
    pool = []
    for item in meta:
        t = item["t"]
        if item["rec"] != "20261110-093238" or item["yellow"] or item["purple"]:
            continue
        if not (145 <= t <= 210 or 313 <= t <= 385 or 395 <= t <= 480):
            continue
        reading = read(crops[item["k"]])
        if reading.minimap == "tilted" and reading.route == "none":
            pool.append(item)
    chosen = sorted(random.Random(seed).sample(pool, count), key=lambda item: item["k"])
    np.savez_compressed(out / "crops.npz", crops=crops[[item["k"] for item in chosen]])
    (out / "selection.json").write_text(
        json.dumps({"seed": seed, "pool": len(pool), "frames": chosen}, indent=2) + "\n"
    )


def evaluate(out):
    crops = np.load(out / "crops.npz")["crops"]
    items = json.loads((out / "selection.json").read_text())["frames"]
    roads = [read_road(crop) for crop in crops]
    timings = []
    for _ in range(5):
        for crop in crops:
            started = time.perf_counter_ns()
            read_road(crop)
            timings.append((time.perf_counter_ns() - started) / 1e6)
    results = []
    for page in range((len(items) + 7) // 8):
        sheet = np.full((4 * 380, 2 * 520, 3), 24, np.uint8)
        for tile, index in enumerate(range(page * 8, min(page * 8 + 8, len(items)))):
            item, road = items[index], roads[index]
            crop = cv2.cvtColor(crops[index], cv2.COLOR_RGB2BGR)
            tile_image = cv2.resize(crop, (520, 340), interpolation=cv2.INTER_NEAREST)
            if road is not None:
                points = np.array(
                    [[round((ARROW_XY[0] + x) * 2), round((ARROW_XY[1] - y) * 2)] for x, y in road.path],
                    np.int32,
                )
                cv2.polylines(tile_image, [points], False, (40, 40, 255), 2, cv2.LINE_AA)
            row, col = (tile // 2) * 380, (tile % 2) * 520
            sheet[row + 40 : row + 380, col : col + 520] = tile_image
            status = "NONE" if road is None else f"width {road.width:.1f}px"
            title = f"{index:02d} k={item['k']} t={item['t']:.2f}s {status}"
            cv2.putText(sheet, title, (col + 8, row + 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
            results.append(
                {
                    "k": item["k"],
                    "path_hash": fingerprint(road),
                    "width": None if road is None else road.width,
                }
            )
        cv2.imwrite(str(out / f"sheet-{page + 1:02d}.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 94])
    (out / "predictions.json").write_text(json.dumps(results, indent=2) + "\n")
    summary = {
        "frames": len(items),
        "mean_ms": float(np.mean(timings)),
        "p95_ms": float(np.percentile(timings, 95)),
    }
    widths = [road.width for road in roads if road is not None]
    if widths:
        summary["width_pixels_p10_p50_p90"] = np.percentile(widths, [10, 50, 90]).tolist()
    labels_path = out / "labels.json"
    summary["labelled"] = labels_path.exists()
    summary["meets_reader_targets"] = None
    if labels_path.exists():
        labels = json.loads(labels_path.read_text())
        current = {item["k"]: item for item in results}
        if len(labels) != len(results) or {label["k"] for label in labels} != set(current):
            raise ValueError("every sampled frame needs one visual label")
        for label in labels:
            if label["scene"] not in ("road", "off-road", "unreadable", "exclude"):
                raise ValueError("unknown scene label")
            if current[label["k"]]["path_hash"] != label["path_hash"]:
                raise ValueError(f"visually recheck changed path for {label['k']}")
        positives = [label for label in labels if label["scene"] == "road"]
        negatives = [label for label in labels if label["scene"] in ("off-road", "unreadable")]
        correct = sum(label["path_on_road"] is True for label in positives)
        invented = sum(current[label["k"]]["width"] is not None for label in negatives)
        summary.update(
            road_frames=len(positives),
            correct_paths=correct,
            road_accuracy=correct / max(1, len(positives)),
            no_road_frames=len(negatives),
            invented_paths=invented,
            false_positive_rate=invented / max(1, len(negatives)),
            excluded_frames=sum(label["scene"] == "exclude" for label in labels),
        )
        summary["meets_reader_targets"] = (
            len(labels) - summary["excluded_frames"] >= 60
            and bool(positives)
            and bool(negatives)
            and summary["road_accuracy"] >= 0.8
            and summary["false_positive_rate"] < 0.05
            and summary["mean_ms"] < 3
        )
    (out / "reader-results.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return summary


def pace_profile(data, out):
    crops = np.load(data / "crops.npy", mmap_mode="r")
    meta = json.loads((data / "meta.json").read_text())
    widths, changes, samples = [], [], []
    previous = None
    candidates = 0
    for item in meta:
        t = item["t"]
        if item["rec"] != "20261110-093238" or item["yellow"] or item["purple"]:
            continue
        if not (145 <= t <= 210 or 313 <= t <= 385 or 395 <= t <= 480):
            continue
        candidates += 1
        road = read_road(crops[item["k"]])
        if road is None:
            previous = None
            continue
        widths.append(road.width)
        if previous is not None and 0 < t - previous[0] <= 0.5:
            changes.append(abs(road.width / previous[1] - 1))
        previous = t, road.width
        samples.append(
            {
                "k": item["k"],
                "t": t,
                "width": road.width,
                "throttle_factor": max(0.5, min(1.0, road.width / 7)),
            }
        )
    summary = {
        "candidate_frames": candidates,
        "readable_frames": len(widths),
        "width_p10_p50_p90": np.percentile(widths, [10, 50, 90]).tolist() if widths else [],
        "adjacent_pairs": len(changes),
        "relative_width_change_p50_p90": np.percentile(changes, [50, 90]).tolist() if changes else [],
        "throttle_reduced_frames": sum(item["throttle_factor"] < 1 for item in samples),
        "metric_speed_validated": False,
    }
    (out / "pace-results.json").write_text(
        json.dumps({"summary": summary, "samples": samples}, indent=2) + "\n"
    )
    print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--select", type=Path, help="directory with recording crops.npy and meta.json")
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--count", type=int, default=72)
    parser.add_argument("--pace-data", type=Path, help="also measure road-width stability on recording crops")
    parser.add_argument(
        "--check", action="store_true", help="fail if the labelled reader targets are not met"
    )
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if args.select:
        if (args.out / "selection.json").exists():
            parser.error("selection already frozen; choose a new output directory")
        select(args.select, args.out, args.seed, args.count)
    summary = evaluate(args.out)
    if args.pace_data:
        pace_profile(args.pace_data, args.out)
    if args.check and summary["meets_reader_targets"] is not True:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
