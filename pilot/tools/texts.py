"""Extract native Vision text at 2 Hz on the recording's source clock."""

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

import cv2

from pilot.notes import consolidate
from pilot.scene import TextReader, VisionUnavailableError


def extract(recording, out, reader):
    frames = [json.loads(line) for line in (recording / "frames.jsonl").read_text().splitlines()]
    selected = {}
    target = 0.0
    for frame in frames:
        if frame["t"] >= target:
            selected[frame["i"]] = frame["t"]
            target += 0.5
            while target <= frame["t"]:
                target += 0.5
    destination = out / recording.name
    destination.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(recording / "video.mp4"))
    readings = []
    started = time.monotonic()
    try:
        with (destination / "readings.jsonl").open("w") as stream:
            for index in range(max(selected, default=-1) + 1):
                if not capture.grab():
                    raise RuntimeError(f"Video ended before indexed frame {index}: {recording}")
                if index not in selected:
                    continue
                ok, image = capture.retrieve()
                if not ok:
                    raise RuntimeError(f"Cannot decode frame {index}: {recording}")
                rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                scene = reader.read(rgb)
                row = {"t": selected[index], "i": index, "text": asdict(scene)}
                readings.append(row)
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                if len(readings) % 120 == 0:
                    stream.flush()
                    print(f"{recording.name}: {row['t']:.1f}s", flush=True)
    finally:
        capture.release()
    intervals = consolidate(readings)
    (destination / "texts.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in intervals)
    )
    elapsed = time.monotonic() - started
    metrics = {
        "recording": recording.name,
        "seconds": frames[-1]["t"],
        "sample_hz": 2,
        "samples": len(readings),
        "wall_seconds": elapsed,
        "realtime_factor": frames[-1]["t"] / elapsed,
        "reader": "native macOS Vision",
    }
    (destination / "extraction.json").write_text(json.dumps(metrics, indent=2) + "\n")
    print(json.dumps(metrics), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recordings", nargs="+", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--level", choices=("fast", "accurate"), default="fast")
    parser.add_argument(
        "--cached-readings",
        type=Path,
        help="Consolidate an existing native OCR cache for one recording without invoking Vision",
    )
    args = parser.parse_args()
    try:
        if args.cached_readings:
            if len(args.recordings) != 1:
                parser.error("--cached-readings requires exactly one recording")
            rows = [json.loads(line) for line in args.cached_readings.read_text().splitlines()]
            destination = args.out / args.recordings[0].name
            destination.mkdir(parents=True, exist_ok=True)
            (destination / "texts.jsonl").write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in consolidate(rows))
            )
            (destination / "source.json").write_text(
                json.dumps(
                    {
                        "ocr_source": str(args.cached_readings),
                        "cached": True,
                        "samples": len(rows),
                        "first": rows[0]["t"] if rows else None,
                        "last": rows[-1]["t"] if rows else None,
                        "native_extraction_benchmarked": False,
                    },
                    indent=2,
                )
                + "\n"
            )
            return
        reader = TextReader(level=args.level)
        for recording in args.recordings:
            extract(recording, args.out, reader)
    except (VisionUnavailableError, RuntimeError, OSError, ValueError) as error:
        parser.exit(1, f"Text extraction failed: {error}\n")


if __name__ == "__main__":
    main()
