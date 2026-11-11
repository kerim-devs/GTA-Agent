"""Repeat the labelled object benchmark locally; no recording or frame is uploaded."""

import argparse
import hashlib
import json
import multiprocessing
import random
import resource
import sys
from pathlib import Path
from time import perf_counter, sleep

import cv2
import numpy as np
import psutil

from pilot.objects import MODEL, SHA256, Detector, Reader, without_player

ROOT = Path(__file__).resolve().parents[2] / "lab" / "objects"
KINDS = ("person", "car", "truck", "bus", "motorcycle", "bicycle")


def overlap(a, b):
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0, x1 - x0) * max(0, y1 - y0)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection
    return intersection / union if union else 0.0


def eligible(kind, box, *, large=False):
    return (
        box[3] - box[1] > (80 if large else 40)
        if kind == "person"
        else box[2] - box[0] > (100 if large else 60)
    )


def match(detections, labels):
    used, matches, invented = set(), [], []
    for detection in sorted(detections, key=lambda d: d.confidence, reverse=True):
        candidates = [
            (overlap(detection.box, label["box"]), i)
            for i, label in enumerate(labels)
            if i not in used and (detection.kind == "person") == (label["kind"] == "person")
        ]
        score, index = max(candidates, default=(0, -1))
        if score >= 0.4:
            used.add(index)
            matches.append((detection, labels[index]))
        elif eligible(detection.kind, detection.box) and not any(
            overlap(detection.box, label["box"]) >= 0.4 for label in labels
        ):
            invented.append(detection)
    missed = [
        label for i, label in enumerate(labels) if i not in used and eligible(label["kind"], label["box"])
    ]
    return matches, missed, invented


def memory_probe(detector, frames, count=3000):
    for i in range(100):
        detector(frames[i % len(frames)])
    unit = 1 if sys.platform == "darwin" else 1024
    process = psutil.Process()
    baseline = process.memory_info().rss
    samples = [baseline]
    peaks = [resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * unit]
    started = perf_counter()
    for i in range(count):
        detector(frames[i % len(frames)])
        if (i + 1) % 250 == 0:
            samples.append(process.memory_info().rss)
            peaks.append(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * unit)
    samples.append(process.memory_info().rss)
    return {
        "detections": count,
        "warmup": 100,
        "rss_bytes": samples,
        "peak_rss_bytes": peaks,
        "rss_growth_bytes": max(samples) - baseline,
        "peak_growth_bytes": max(peaks) - peaks[0],
        "seconds": perf_counter() - started,
        "limit_bytes": 16 * 1024 * 1024,
        "passed": max(samples) - baseline < 16 * 1024 * 1024,
    }


def busy_core(stop, ready):
    value = 0
    ready.set()
    while not stop.is_set():
        for _ in range(10000):
            value = (value + 1) % 1000003


def poller_probe(detector, frame, seconds=3):
    reader = Reader(recognizer=detector)
    started, durations, captures = perf_counter(), [], []
    ticks = 0
    try:
        while perf_counter() - started < seconds:
            before = perf_counter()
            result = reader.poll(frame, before)
            durations.append((perf_counter() - before) * 1000)
            if result is not None:
                captures.append(result[0])
            ticks += 1
            sleep(max(0, started + ticks / 30 - perf_counter()))
    finally:
        reader.close()
    return {
        "loop_hz": ticks / seconds,
        "results_hz": len(captures) / seconds,
        "poll_mean_ms": float(np.mean(durations)),
        "poll_p95_ms": float(np.percentile(durations, 95)),
        "poll_max_ms": max(durations),
    }


def evaluate(detector, records, frames):
    totals = {kind: {"found": 0, "missed": 0, "invented": 0} for kind in KINDS}
    large = {kind: {"found": 0, "missed": 0} for kind in KINDS}
    leakage, collateral, removed_player, timings, details = [], [], 0, [], []
    ignored_predictions = 0
    eligible_reports = 0
    groups = {
        name: {"found": 0, "count": 0}
        for name in ("vehicles_over_200", "vehicles_over_100", "people_over_80")
    }
    kind_agreement = {"same": 0, "matched": 0}
    for record, frame in zip(records, frames, strict=True):
        before = perf_counter()
        raw = detector.detect(frame, exclude_player=False)
        timings.append((perf_counter() - before) * 1000)
        predictions = without_player(raw)
        eligible_reports += sum(eligible(d.kind, d.box) for d in predictions)
        players = [label for label in record["labels"] if label["player"]]
        others = [label for label in record["labels"] if not label["player"]]
        hits, missed, invented = match(predictions, others)
        invented = [d for d in invented if not any(overlap(d.box, p["box"]) >= 0.4 for p in players)]
        for name, group in groups.items():
            selected = [
                label
                for label in others
                if (
                    label["kind"] == "person" and label["box"][3] - label["box"][1] > 80
                    if name == "people_over_80"
                    else label["kind"] != "person"
                    and label["box"][2] - label["box"][0] > (200 if name == "vehicles_over_200" else 100)
                )
            ]
            group["count"] += len(selected)
            group["found"] += sum(label in selected for _, label in hits)
        scored_hits = sum(eligible(label["kind"], label["box"]) for _, label in hits)
        ignored_predictions += len(predictions) - scored_hits - len(invented)
        for detection, label in hits:
            if eligible(label["kind"], label["box"]):
                totals[label["kind"]]["found"] += 1
                kind_agreement["matched"] += 1
                kind_agreement["same"] += detection.kind == label["kind"]
            if eligible(label["kind"], label["box"], large=True):
                large[label["kind"]]["found"] += 1
        for label in missed:
            totals[label["kind"]]["missed"] += 1
            if eligible(label["kind"], label["box"], large=True):
                large[label["kind"]]["missed"] += 1
        for detection in invented:
            totals[detection.kind]["invented"] += 1
        if any(overlap(d.box, p["box"]) >= 0.4 for d in predictions for p in players):
            leakage.append(record["id"])
        removed = [d for d in raw if not any(d is kept for kept in predictions)]
        removed_player += sum(any(overlap(d.box, p["box"]) >= 0.4 for p in players) for d in removed)
        collateral.extend(
            {"frame": record["id"], "kind": d.kind, "box": d.box}
            for d in removed
            if any(overlap(d.box, label["box"]) >= 0.4 for label in others)
        )
        details.append(
            {
                "frame": record["id"],
                "detections": [
                    {"kind": d.kind, "box": d.box, "confidence": d.confidence} for d in predictions
                ],
                "missed": missed,
                "invented": [{"kind": d.kind, "box": d.box} for d in invented],
            }
        )
    found = sum(v["found"] for v in totals.values())
    invented = sum(v["invented"] for v in totals.values())
    large_found = sum(v["found"] for v in large.values())
    large_count = sum(sum(v.values()) for v in large.values())
    return {
        "frames": len(frames),
        "iou": 0.4,
        "groups": {
            name: {**group, "recall": group["found"] / group["count"] if group["count"] else None}
            for name, group in groups.items()
        },
        "kind_agreement": kind_agreement,
        "per_kind": totals,
        "large_per_kind": large,
        "large_recall": large_found / large_count if large_count else None,
        "eligible_reports": eligible_reports,
        "invented_fraction": invented / eligible_reports if eligible_reports else None,
        "matched_precision_invented_fraction": invented / (found + invented) if found + invented else None,
        "ignored_small_predictions": ignored_predictions,
        "player_reported_frames": leakage,
        "player_reported_fraction": len(leakage) / len(frames),
        "player_present_frames": sum(any(x["player"] for x in r["labels"]) for r in records),
        "removed_player_detections": removed_player,
        "collateral_removed": collateral,
        "mean_ms": float(np.mean(timings)),
        "p95_ms": float(np.percentile(timings, 95)),
        "details": details,
    }


def sheets(records, frames, details, destination=None):
    destination = ROOT if destination is None else destination
    (destination / "sheets").mkdir(parents=True, exist_ok=True)
    for start in range(0, len(records), 4):
        cells = []
        for record, rgb, result in zip(
            records[start : start + 4], frames[start : start + 4], details[start : start + 4], strict=True
        ):
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            for label in record["labels"]:
                x0, y0, x1, y1 = map(int, label["box"])
                color = (255, 0, 255) if label["player"] else (0, 255, 0)
                cv2.rectangle(bgr, (x0, y0), (x1, y1), color, 2)
                cv2.putText(bgr, label["kind"], (x0, max(16, y0 - 4)), 0, 0.5, color, 1)
            for detection in result["detections"]:
                x0, y0, x1, y1 = map(int, detection["box"])
                cv2.rectangle(bgr, (x0, y0), (x1, y1), (0, 200, 255), 2)
            cv2.putText(
                bgr,
                record["id"] + " green: truth / pink: player / yellow: prediction",
                (12, 28),
                0,
                0.65,
                (255, 255, 255),
                2,
            )
            cells.append(bgr)
        while len(cells) < 4:
            cells.append(np.zeros_like(cells[0]))
        image = cv2.vconcat([cv2.hconcat(cells[:2]), cv2.hconcat(cells[2:])])
        cv2.imwrite(str(destination / "sheets" / f"labelled-{start:03}.jpg"), image)


def sample(sources, seed=1414, counts=(24, 24, 32), exclude=()):
    rng, records = random.Random(seed), []
    (ROOT / "frames").mkdir(parents=True, exist_ok=True)
    for source, count in zip(sources, counts, strict=True):
        timing = {
            row["i"]: row for row in map(json.loads, (source / "frames.jsonl").read_text().splitlines())
        }
        capture = cv2.VideoCapture(str(source / "video.mp4"))
        length, fps = int(capture.get(cv2.CAP_PROP_FRAME_COUNT)), capture.get(cv2.CAP_PROP_FPS)
        try:
            population = [i for i in range(length) if (str(source), i) not in exclude]
            for index in sorted(rng.sample(population, count)):
                capture.set(cv2.CAP_PROP_POS_FRAMES, index)
                ok, frame = capture.read()
                if not ok:
                    raise RuntimeError(f"Cannot decode frame {index} in {source}")
                ident = f"{len(records):03}"
                path = ROOT / "frames" / f"{ident}.jpg"
                cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
                records.append(
                    {
                        "id": ident,
                        "source": str(source),
                        "frame_index": index,
                        "video_time": index / fps,
                        "capture_time": timing[index]["t"],
                        "frame_id": timing[index]["frame_id"],
                        "file": f"frames/{ident}.jpg",
                        "labels": [],
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                )
        finally:
            capture.release()
    # Never replace the hand labels when regenerating the same frame sample.
    (ROOT / "sample.json").write_text(json.dumps({"seed": seed, "frames": records}, indent=2) + "\n")


def main():
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory", action="store_true")
    parser.add_argument("--memory-only", action="store_true")
    parser.add_argument("--sample", nargs=3, type=Path)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", type=int, default=1414)
    parser.add_argument("--counts", nargs=3, type=int, default=(24, 24, 32))
    parser.add_argument("--exclude", type=Path)
    args = parser.parse_args()
    ROOT = args.root.resolve()
    if args.sample:
        exclude = set()
        if args.exclude:
            exclude = {
                (r["source"], r["frame_index"]) for r in json.loads(args.exclude.read_text())["frames"]
            }
        sample(args.sample, args.seed, args.counts, exclude)
        return
    label_path = ROOT / "labels.json"
    manifest = json.loads(label_path.read_text())
    records = manifest["frames"]
    frames = [cv2.cvtColor(cv2.imread(str(ROOT / r["file"])), cv2.COLOR_BGR2RGB) for r in records]
    detector = Detector()
    if args.memory_only:
        print(json.dumps(memory_probe(detector, frames), indent=2))
        return
    if manifest["annotation"] == "Pending manual annotation":
        raise RuntimeError("Finish the independent manual labels before evaluating accuracy")
    stop, ready = multiprocessing.Event(), multiprocessing.Event()
    load = multiprocessing.Process(target=busy_core, args=(stop, ready))
    load.start()
    try:
        if not ready.wait(10):
            raise RuntimeError("CPU load process did not start")
        for frame in frames[:10]:
            detector(frame)
        result = evaluate(detector, records, frames)
        result["poller"] = poller_probe(detector, frames[40])
        result["load"] = "one separate CPU-bound Python process"
    finally:
        stop.set()
        load.join()
    if args.memory:
        result["memory"] = memory_probe(detector, frames)
    result["labels_sha256"] = hashlib.sha256(label_path.read_bytes()).hexdigest()
    result["model"] = {
        "file": MODEL.name,
        "sha256": SHA256,
        "confidence": detector.confidence,
        "input_size": detector.size,
        "native_tiles": detector.tiled,
        "provider_order": detector.session.get_providers(),
        "provider_options": detector.session.get_provider_options(),
    }
    result["evaluated_code_sha256"] = {
        "objects": hashlib.sha256(
            (Path(__file__).resolve().parents[1] / "src/pilot/objects.py").read_bytes()
        ).hexdigest(),
        "evaluator": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    result["acceptance"] = {
        **{
            name: group["recall"] is not None and group["recall"] >= target
            for (name, group), target in zip(result["groups"].items(), (0.9, 0.8, 0.8), strict=True)
        },
        "precision": result["invented_fraction"] is not None and result["invented_fraction"] <= 0.15,
        "player": result["player_reported_fraction"] < 0.02,
        "speed": result["poller"]["results_hz"] >= 8 and result["poller"]["poll_max_ms"] < 1,
    }
    destination = ROOT if args.output is None else args.output.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    sheets(records, frames, result["details"], destination)
    (destination / "metrics.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "details"}, indent=2))


if __name__ == "__main__":
    main()
