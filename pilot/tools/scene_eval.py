"""Replay local recordings with OpenCV; emit JSON evidence without live access."""

import argparse
import json
import statistics
import time
from dataclasses import asdict
from pathlib import Path

import cv2

from pilot.contract import HUD_RECT
from pilot.minimap import read
from pilot.scene import EventDetector, TextReader, VisionUnavailableError


def evaluate(path: Path, hz: float, reader: TextReader | None, output) -> None:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot decode {path}; use original recordings, not LFS pointers")
    detector = EventDetector()
    next_sample = 0.0
    count = 0
    events = 0
    costs = []
    last = -1.0
    # Capture timestamps, not nominal 30-fps video time, include Wi-Fi stalls.
    with path.with_name("frames.jsonl").open() as source:
        times = [json.loads(line)["t"] for line in source]
    index = 0
    try:
        while True:
            ok, bgr = cap.read()
            if not ok:
                break
            if index >= len(times):
                raise RuntimeError(f"video has more frames than frames.jsonl: {path}")
            timestamp = times[index] - times[0]
            index += 1
            if timestamp <= last:
                raise RuntimeError(f"non-increasing video PTS at frame {count}: {path}")
            last = timestamp
            if timestamp + 1e-6 < next_sample:
                continue
            next_sample = timestamp + 1 / hz
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            x, y, w, h = HUD_RECT
            reading = read(rgb[y : y + h, x : x + w])
            text = reader.read(rgb) if reader else None
            if text:
                costs.append(text.elapsed_ms)
            emitted = detector.update(reading, timestamp, text=text)
            events += len(emitted)
            count += 1
            record = {
                "recording": path.parent.name,
                "time": round(timestamp, 3),
                "reading": asdict(reading),
                "text": asdict(text) if text else None,
                "events": [asdict(event) for event in emitted],
            }
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
    finally:
        cap.release()
    if index != len(times):
        raise RuntimeError(f"decoded {index} frames but metadata has {len(times)}: {path}")
    print(
        json.dumps(
            {
                "recording": path.parent.name,
                "samples": count,
                "last_pts": last,
                "events": events,
                "ocr_median_ms": statistics.median(costs) if costs else None,
                "ocr_p95_ms": sorted(costs)[int((len(costs) - 1) * 0.95)] if costs else None,
            }
        ),
        flush=True,
    )


def benchmark(path: Path, timestamp: float, iterations: int) -> None:
    cap = cv2.VideoCapture(str(path))
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
        ok, bgr = cap.read()
        if not ok:
            raise RuntimeError(f"cannot decode benchmark frame: {path}")
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    finally:
        cap.release()
    for mode in ("fast", "accurate"):
        reader = TextReader(mode)
        for region in ("help", None):
            costs = []
            for _ in range(iterations + 1):
                started = time.perf_counter()
                result = reader.read(rgb, region)
                costs.append((time.perf_counter() - started) * 1000)
            warm = costs[1:]
            print(
                json.dumps(
                    {
                        "mode": mode,
                        "region": region or "full",
                        "cold_ms": costs[0],
                        "median_ms": statistics.median(warm),
                        "p95_ms": sorted(warm)[int((len(warm) - 1) * 0.95)],
                        "iterations": iterations,
                        "text": asdict(result),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recordings", type=Path, help="local recording root or one video.mp4")
    parser.add_argument("--output", type=Path, help="local JSONL timeline path")
    parser.add_argument("--hz", type=float, default=2.0)
    parser.add_argument("--no-ocr", action="store_true")
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument("--at", type=float, default=13.0)
    args = parser.parse_args()
    if not 0.5 <= args.hz <= 4:
        parser.error("--hz must be between 0.5 and 4; OCR never belongs in the 30 Hz loop")
    paths = [args.recordings] if args.recordings.is_file() else sorted(args.recordings.glob("*/video.mp4"))
    if not paths:
        parser.error("no local video.mp4 recordings found")
    if args.benchmark:
        benchmark(paths[0], args.at, 10)
        return
    if args.output is None:
        parser.error("--output is required for a replay")
    try:
        reader = None if args.no_ocr else TextReader()
    except VisionUnavailableError as exc:
        parser.error(f"{exc}; use --no-ocr for detector-only evaluation")
    with args.output.open("w") as output:
        for path in paths:
            evaluate(path, args.hz, reader, output)


if __name__ == "__main__":
    main()
