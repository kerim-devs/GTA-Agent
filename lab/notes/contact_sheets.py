"""Make source-clock contact sheets for every consolidated text change."""

import argparse
from bisect import bisect_left
import json
from pathlib import Path

import cv2
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path)
    parser.add_argument("texts", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    frames = [json.loads(line) for line in (args.recording / "frames.jsonl").read_text().splitlines()]
    intervals = [json.loads(line) for line in args.texts.read_text().splitlines()]
    changes = sorted({row["first"] for row in intervals} | {min(frames[-1]["t"], row["last"] + 0.5) for row in intervals})
    times = [row["t"] for row in frames]
    args.out.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(args.recording / "video.mp4"))
    manifest = []
    sheet = None
    try:
        for index, timestamp in enumerate(changes):
            frame = frames[min(len(frames) - 1, bisect_left(times, timestamp))]
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame["i"])
            ok, image = capture.read()
            if not ok:
                raise RuntimeError(f"Cannot read frame {frame['i']}")
            if index % 12 == 0:
                sheet = np.zeros((4 * 390, 3 * 640, 3), dtype=np.uint8)
            y, x = (index % 12 // 3) * 390, (index % 3) * 640
            sheet[y:y + 360, x:x + 640] = cv2.resize(image, (640, 360))
            cv2.putText(sheet, f"{frame['t']:.3f}s / frame {frame['i']}", (x + 5, y + 382), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 1)
            name = f"changes-{index // 12 + 1:02}.jpg"
            manifest.append({"t": frame["t"], "frame": frame["i"], "sheet": name, "cell": index % 12})
            if index % 12 == 11 or index == len(changes) - 1:
                cv2.imwrite(str(args.out / name), sheet)
        (args.out / "index.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"{len(changes)} change frames in {(len(changes) + 11) // 12} sheets")
    finally:
        capture.release()


if __name__ == "__main__":
    main()
