"""Replay P54 evidence offline; never contact the console or modify recordings."""

import argparse
import csv
import json
import subprocess
import sys
import time
import types
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "pilot/src"))
from pilot.replay import hud_crop

from pilot import minimap

OUT = Path(__file__).parent
SHEETS = Path("/private/tmp/p54-audit")
BASE = "51356e9"
SPANS = {
    "20261112-110449": [(10.5, 25.6)],
    "20261112-102851": [(73.6, 88.8)],
    "20261112-100713": [(179.3, 184.6), (194.3, 197.5), (199.5, 206.8), (207.1, 212.8)],
    "20261112-104424": [(121.7, 124.3)],
}


def baseline():
    module = types.ModuleType("pilot.p54_baseline")
    sys.modules[module.__name__] = module
    source = subprocess.check_output(
        ["git", "show", f"{BASE}:pilot/src/pilot/minimap.py"], cwd=ROOT
    )
    exec(compile(source, f"{BASE}:pilot/src/pilot/minimap.py", "exec"), module.__dict__)  # noqa: S102
    return module


def stats(rows, key):
    current = longest = count = 0
    start = end = 0.0
    longest_seconds = 0.0
    for row in rows:
        if row[key]:
            if not current:
                start = row["t"]
            current += 1
            count += 1
            end = row["t"]
            longest = max(longest, current)
            longest_seconds = max(longest_seconds, end - start)
        else:
            current = 0
    return {
        "ticks": len(rows),
        "corrupt": count,
        "share": count / len(rows) if rows else 0,
        "longest_ticks": longest,
        "longest_seconds": longest_seconds,
    }


class Sheets:
    def __init__(self, name):
        self.name = name
        self.images = []
        self.pages = 0

    def add(self, rgb, label):
        tile = np.zeros((192, 260, 3), np.uint8)
        tile[:170] = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        cv2.putText(
            tile, label, (3, 186), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1
        )
        self.images.append(tile)
        if len(self.images) == 48:
            self.flush()

    def flush(self):
        if not self.images:
            return
        canvas = np.zeros((((len(self.images) + 5) // 6) * 192, 1560, 3), np.uint8)
        for j, tile in enumerate(self.images):
            canvas[
                j // 6 * 192 : (j // 6 + 1) * 192, j % 6 * 260 : (j % 6 + 1) * 260
            ] = tile
        SHEETS.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(
            str(SHEETS / f"{self.name}-{self.pages:03}.jpg"),
            canvas,
            [cv2.IMWRITE_JPEG_QUALITY, 82],
        )
        self.pages += 1
        self.images.clear()


def session(folder):
    before = baseline()
    frame_file = folder / "frames.jsonl"
    metadata = (
        [json.loads(s) for s in frame_file.read_text().splitlines()]
        if frame_file.exists()
        else None
    )
    play_file = folder / "play.jsonl"
    ticks = (
        [json.loads(s) for s in play_file.read_text().splitlines()]
        if play_file.exists()
        else []
    )
    cap = cv2.VideoCapture(str(folder / "video.mp4"))
    fps = cap.get(cv2.CAP_PROP_FPS)
    rows, by_id = [], {}
    lost = Sheets(folder.name + "-lost")
    # The short clean session is benchmarked separately; avoid decode/timing noise.
    index = 0
    with (OUT / f"{folder.name}-changes.csv").open("w") as stream:
        writer = csv.writer(stream)
        writer.writerow(("i", "frame_id", "t", "before", "after", "route", "blocks"))
        while True:
            ok, bgr = cap.read()
            if not ok:
                break
            frame = (
                metadata[index]
                if metadata is not None
                else {"i": index, "frame_id": index, "t": index / fps}
            )
            crop = hud_crop(bgr)
            old = before.read(crop)
            new = minimap.read(crop)
            row = dict(**frame, before=int(old.corrupt), after=int(new.corrupt))
            rows.append(row)
            by_id[frame["frame_id"]] = row
            if old.corrupt != new.corrupt:
                writer.writerow(
                    (
                        index,
                        frame["frame_id"],
                        frame["t"],
                        int(old.corrupt),
                        int(new.corrupt),
                        new.route,
                        before._blocks(crop)[0],
                    )
                )
                if old.corrupt:
                    lost.add(crop, f"{index} t={frame['t']:.3f}")
            index += 1
            if index % 10000 == 0:
                print(folder.name, index, flush=True)
    cap.release()
    lost.flush()
    if metadata is not None and len(rows) != len(metadata):
        raise RuntimeError(f"Video/metadata mismatch: {len(rows)} / {len(metadata)}")
    matched = [
        dict(by_id[t["frame_id"]], t=t["t"]) for t in ticks if t["frame_id"] in by_id
    ]
    selected = matched if ticks else rows
    result = {
        "session": folder.name,
        "source": str(folder),
        "frames": len(rows),
        "before": stats(selected, "before"),
        "after": stats(selected, "after"),
        "frame_before": stats(rows, "before"),
        "frame_after": stats(rows, "after"),
        "lost": sum(r["before"] and not r["after"] for r in rows),
        "gained": sum(r["after"] and not r["before"] for r in rows),
        "unmatched_ticks": len(ticks) - len(matched),
        "sheets": lost.pages,
        "spans": [],
    }
    for start, stop in SPANS.get(folder.name, []):
        subset = [r for r in selected if start <= r["t"] < stop]
        result["spans"].append(
            {
                "start": start,
                "stop": stop,
                "before": stats(subset, "before"),
                "after": stats(subset, "after"),
            }
        )
    (OUT / f"{folder.name}.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)


def corpus(path):
    before = baseline()
    crops = np.load(path, mmap_mode="r")
    lost = Sheets("corpus-lost")
    result = {"crops": len(crops), "before": 0, "after": 0, "lost": [], "gained": []}
    for i, crop in enumerate(crops):
        old, new = before.read(crop), minimap.read(crop)
        result["before"] += int(old.corrupt)
        result["after"] += int(new.corrupt)
        if old.corrupt and not new.corrupt:
            result["lost"].append(i)
            lost.add(crop, str(i))
        if new.corrupt and not old.corrupt:
            result["gained"].append(i)
    lost.flush()
    (OUT / "corpus.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)


def benchmark(folder):
    before = baseline()
    frames = [json.loads(s) for s in (folder / "frames.jsonl").read_text().splitlines()]
    ticks = [json.loads(s) for s in (folder / "play.jsonl").read_text().splitlines()]
    weights = {}
    for tick in ticks:
        weights[tick["frame_id"]] = weights.get(tick["frame_id"], 0) + 1
    totals = [0, 0]
    samples = [[], []]
    cap = cv2.VideoCapture(str(folder / "video.mp4"))
    for i, frame in enumerate(frames):
        ok, bgr = cap.read()
        if not ok:
            raise RuntimeError("Missing benchmark frame")
        weight = weights.get(frame["frame_id"], 0)
        if not weight:
            continue
        crop = hud_crop(bgr)
        # Alternate order to balance cache/thermal effects; decoding is excluded.
        for j in (0, 1) if i % 2 else (1, 0):
            reader = before if j == 0 else minimap
            start = time.perf_counter_ns()
            reader.read(crop)
            elapsed = time.perf_counter_ns() - start
            totals[j] += weight * elapsed
            samples[j].extend([elapsed] * weight)
    cap.release()
    result = {
        "session": folder.name,
        "ticks": len(samples[0]),
        "mean_ms": [v / len(samples[0]) / 1e6 for v in totals],
        "median_ms": [float(np.median(v)) / 1e6 for v in samples],
        "ratio": totals[1] / totals[0],
    }
    (OUT / "benchmark.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=Path)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--benchmark", type=Path)
    args = parser.parse_args()
    if args.session:
        session(args.session)
    if args.corpus:
        corpus(args.corpus)
    if args.benchmark:
        benchmark(args.benchmark)
