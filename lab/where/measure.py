"""Read-only recording sampling and reproducible P60 judge measurements."""

import argparse
import bisect
import json
import sys
import time
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot/src"))
HERE = Path(__file__).resolve().parent


@lru_cache(maxsize=32)
def timeline(path):
    rows = [
        json.loads(line)
        for line in (Path(path) / "frames.jsonl").read_text().splitlines()
    ]
    return rows, [r["t"] for r in rows]


def frame(path, seconds):
    rows, times = timeline(path)
    at = bisect.bisect_left(times, seconds)
    at = min(
        range(max(0, at - 1), min(len(rows), at + 1)),
        key=lambda i: abs(times[i] - seconds),
    )
    cap = cv2.VideoCapture(str(Path(path) / "video.mp4"))
    cap.set(cv2.CAP_PROP_POS_FRAMES, rows[at]["i"])
    ok, image = cap.read()
    cap.release()
    if not ok:
        raise ValueError(f"No frame at {path}:{seconds}")
    return image


def sample():
    rows = []
    sources = sorted(
        Path("/Users/kerim/recordings/derived/kerim").glob("20261112*/sections.json")
    )
    for source in sources:
        data = json.loads(source.read_text())
        spans = [
            s
            for s in data["sections"]
            if s["kind"] == "foot" and s["end"] - s["start"] >= 1
        ]
        total = sum(s["end"] - s["start"] for s in spans)
        if not total:
            continue
        for offset in np.linspace(0.5, max(0.5, total - 0.5), 30):
            for span in spans:
                duration = span["end"] - span["start"]
                if offset < duration:
                    rows.append(
                        {
                            "source": f"/Users/kerim/recordings/kerim/{source.parent.name}",
                            "seconds": round(span["start"] + offset, 3),
                        }
                    )
                    break
                offset -= duration
    for session, start, end, count in [
        ("20261112-143714", 0, 50, 26),
        ("20261112-143128", 0, 30, 16),
        ("20261112-142428", 241, 274, 18),
    ]:
        for t in np.linspace(start, end, count):
            rows.append(
                {
                    "source": f"/Users/kerim/recordings/pilot/{session}",
                    "seconds": round(float(t), 3),
                }
            )
    for i, row in enumerate(rows):
        row["id"] = f"f{i:03}"
    (HERE / "frames.json").write_text(json.dumps(rows, indent=2) + "\n")
    sheets(rows, "foot")
    print(f"Sampled {len(rows)} candidates from {len(sources)} section manifests")


def sheets(rows, prefix):
    for page in range((len(rows) + 23) // 24):
        canvas = np.zeros((4 * 251, 6 * 400, 3), np.uint8)
        for i, row in enumerate(rows[page * 24 : (page + 1) * 24]):
            image = frame(row["source"], row["seconds"])
            tile = cv2.resize(image, (400, 225))
            if "box" in row:
                x, y, x1, y1 = row["box"]
                cv2.rectangle(
                    tile,
                    (int(x * 400), int(y * 225)),
                    (int(x1 * 400), int(y1 * 225)),
                    (0, 255, 255),
                    2,
                )
            y, x = divmod(i, 6)
            canvas[y * 251 : y * 251 + 225, x * 400 : (x + 1) * 400] = tile
            cv2.putText(
                canvas,
                f"{row['id']} {Path(row['source']).name[-6:]} {row['seconds']:.1f}s",
                (x * 400 + 3, y * 251 + 244),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.47,
                (255, 255, 255),
                1,
            )
        target = Path("/tmp") / f"p60-{prefix}-{page:02}.jpg"
        cv2.imwrite(str(target), canvas, [cv2.IMWRITE_JPEG_QUALITY, 85])


def vehicles():
    data = json.loads((ROOT / "lab/enter/p57-fresh-detections.json").read_text())
    pool = []
    for entry in data["entries"]:
        for sample in entry["samples"][::2]:
            for index, obj in enumerate(sample.get("objects", [])):
                x, y, x1, y1 = obj["box"]
                if (
                    obj["kind"] not in {"car", "truck", "bus", "motorcycle"}
                    or (x1 - x) * (y1 - y) < 2400
                ):
                    continue
                pool.append(
                    {
                        "source": f"/Users/kerim/recordings/kerim/{entry['session']}",
                        "seconds": sample["frame_t"],
                        "frame_index": sample["frame_index"],
                        "action_line": entry["action_line"],
                        "object_index": index,
                        "kind": obj["kind"],
                        "box": [x / 1280, y / 720, x1 / 1280, y1 / 720],
                    }
                )
    rows = [
        pool[i] for i in np.linspace(0, len(pool) - 1, min(216, len(pool)), dtype=int)
    ]
    for i, row in enumerate(rows):
        row["id"] = f"v{i:03}"
    (HERE / "vehicles.json").write_text(json.dumps(rows, indent=2) + "\n")
    sheets(rows, "vehicle")
    print(f"Sampled {len(rows)} vehicle boxes from {len(pool)} eligible detections")


def prepare(row, crop):
    image = frame(row["source"], row["seconds"])
    h, w = image.shape[:2]
    if "box" in row:
        x, y, x1, y1 = row["box"]
        cv2.rectangle(
            image,
            (round(x * w), round(y * h)),
            (round(x1 * w), round(y1 * h)),
            (0, 0, 255),
            3,
        )
        if crop:
            dx, dy = max(0.08, (x1 - x) * 0.8), max(0.08, (y1 - y) * 0.8)
            image = image[
                max(0, round((y - dy) * h)) : min(h, round((y1 + dy) * h)),
                max(0, round((x - dx) * w)) : min(w, round((x1 + dx) * w)),
            ]
    elif crop:
        image = image[round(0.25 * h) :, round(0.15 * w) : round(0.85 * w)]
    return image


def run(model, dataset, variants):
    from pilot.judge import ask_where, encode, parse_where

    rows = json.loads(
        (HERE / ("frames.json" if dataset == "foot" else "vehicles.json")).read_text()
    )
    labels = json.loads((HERE / "labels.json").read_text())[dataset + "_pages"]
    target = HERE / f"answers-{dataset}-{model.rsplit('-', 1)[-1]}.jsonl"
    completed = set()
    if target.exists():
        completed = {
            (r["id"], r["variant"])
            for r in map(json.loads, target.read_text().splitlines())
        }
    with target.open("a") as out:
        for index, row in enumerate(rows):
            page = labels.get(str(index // 24), "").split()
            if len(page) <= index % 24 or page[index % 24] == "X":
                continue
            for variant in variants:
                if (row["id"], variant) in completed:
                    continue
                result = {
                    "id": row["id"],
                    "variant": variant,
                    "model": model,
                    "label": page[index % 24],
                    "capture": row["seconds"],
                }
                names = ("where", "edge") if dataset == "foot" else ("vehicle", "where")
                if "plain" in variant and dataset == "foot":
                    names = ("where_plain", "edge")
                elif "plain" in variant:
                    names = ("vehicle_plain", "where")
                image = encode(prepare(row, variant.startswith("crop")), 640)
                started = time.perf_counter()
                try:
                    if variant.endswith("single"):
                        names = names[:1]
                    choice, duration = ask_where(
                        "http://192.168.0.248:1234", model, image, names, timeout=15
                    )
                    judgment = parse_where(
                        choice, row["seconds"], duration, "pc", names
                    )
                    result.update(
                        duration=duration,
                        reply=choice["message"]["content"],
                        answers={
                            k.replace("_plain", ""): {
                                "value": v.value,
                                "probability": v.probability,
                            }
                            for k, v in judgment.answers.items()
                        },
                        probabilities=judgment.probabilities,
                    )
                except Exception as exc:
                    result.update(
                        duration=time.perf_counter() - started,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                out.write(json.dumps(result, separators=(",", ":")) + "\n")
                out.flush()
            if index % 12 == 0:
                print(f"{dataset} {index}/{len(rows)}", flush=True)


def freeze():
    labels = json.loads((HERE / "labels.json").read_text())
    for dataset, filename in (("foot", "frames.json"), ("vehicle", "vehicles.json")):
        rows = json.loads((HERE / filename).read_text())
        for i, row in enumerate(rows):
            row["label"] = labels[dataset + "_pages"][str(i // 24)].split()[i % 24]
            indices, times = timeline(row["source"])
            at = bisect.bisect_left(times, row["seconds"])
            at = min(
                range(max(0, at - 1), min(len(times), at + 1)),
                key=lambda j: abs(times[j] - row["seconds"]),
            )
            row["frame_index"] = indices[at]["i"]
            row["frame_time"] = times[at]
        (HERE / filename).write_text(json.dumps(rows, indent=2) + "\n")
        for page in range((len(rows) + 23) // 24):
            contact = cv2.imread(f"/tmp/p60-{dataset}-{page:02}.jpg")
            if contact is None:
                raise ValueError("Run sample and vehicles before freeze")
            preview = cv2.resize(contact, (1440, 602), interpolation=cv2.INTER_AREA)
            cv2.imwrite(
                str(HERE / f"{dataset}-{page:02}.jpg"),
                preview,
                [cv2.IMWRITE_JPEG_QUALITY, 48],
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["sample", "vehicles", "run", "freeze"])
    parser.add_argument("--model", default="qwen/qwen3-vl-8b")
    parser.add_argument("--dataset", default="foot", choices=["foot", "vehicle"])
    parser.add_argument(
        "--variants",
        nargs="+",
        default=["whole-single", "whole-pair", "crop-single", "crop-pair"],
    )
    args = parser.parse_args()
    if args.action == "sample":
        sample()
    elif args.action == "vehicles":
        vehicles()
    elif args.action == "run":
        run(args.model, args.dataset, args.variants)
    elif args.action == "freeze":
        freeze()
