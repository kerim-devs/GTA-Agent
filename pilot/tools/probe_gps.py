"""Read-only native OCR timing probe on explicitly supplied offline video."""

import argparse
import json
from pathlib import Path
from statistics import median
from time import perf_counter

import cv2

from pilot.gps import recognize, turn_arrow
from pilot.replay import hud_crop, json_lines


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    frames = json_lines(args.recording / "frames.jsonl")
    first = frames[0]["t"]
    capture = cv2.VideoCapture(str(args.recording / "video.mp4"))
    rows = []
    try:
        for t in (238.6, 241, 246.1, 254, 260, 270, 280, 293.5, 300, 305.95):
            frame = min(frames, key=lambda frame: abs(frame["t"] - first - t))
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame["i"])
            ok, bgr = capture.read()
            if not ok:
                raise RuntimeError(f"Cannot decode frame {frame['i']}")
            crop = hud_crop(bgr)
            error, distance = None, None
            started = perf_counter()
            try:
                fix = recognize(crop)
                distance = None if fix is None else fix.distance
            except Exception as exc:
                error = str(exc)
            elapsed = (perf_counter() - started) * 1000
            rows.append(
                dict(t=frame["t"] - first, distance=distance, arrow=turn_arrow(crop), ms=elapsed, error=error)
            )
    finally:
        capture.release()
    result = dict(
        samples=rows,
        fixes=sum(r["distance"] is not None for r in rows),
        median_ms=median(r["ms"] for r in rows),
        max_ms=max(r["ms"] for r in rows),
    )
    text = json.dumps(result, indent=2) + "\n"
    print(text, end="")
    if args.out:
        args.out.write_text(text)


if __name__ == "__main__":
    main()
