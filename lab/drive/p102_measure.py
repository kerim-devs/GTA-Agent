"""Bounded offline P102 human measurements and incident reader verification."""

import argparse
import gzip
import json
import sys
from dataclasses import asdict
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot/src"))
from p98_human import extract
from pilot.minimap import read
from pilot.replay import hud_crop

cv2.setNumThreads(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reader", action="store_true")
    args = parser.parse_args()
    if args.reader:
        directory = Path("/Users/kerim/recordings/pilot/20261114-011017")
        frames = [
            json.loads(x) for x in (directory / "frames.jsonl").read_text().splitlines()
        ]
        cap = cv2.VideoCapture(str(directory / "video.mp4"))
        rows = []
        for frame in frames:
            if (
                not 96 <= frame["t"] <= 106
                or rows
                and frame["t"] - rows[-1]["t"] < 0.25
            ):
                continue
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame["i"])
            ok, image = cap.read()
            assert ok
            rows.append(dict(frame, reading=asdict(read(hud_crop(image)))))
        cap.release()
        with gzip.open(ROOT / "lab/drive/p102-reader.json.gz", "wt") as stream:
            json.dump(rows, stream)
        print("reader", len(rows), "frames, 96-106 seconds")
        return
    for name, start, end in [
        ("20261113-141634", 192, 225),
        ("20261113-180503", 73, 91),
    ]:
        target = ROOT / "lab/drive" / f"p102-human-{name}.json.gz"
        if target.exists():
            with gzip.open(target, "rt") as stream:
                rows = json.load(stream)
        else:
            rows = extract(name, start, end)
            with gzip.open(target, "wt") as stream:
                json.dump(rows, stream)
        print(name, len(rows), "samples", flush=True)
        for sec in range(start, end):
            row = min(rows, key=lambda r: abs(r["t"] - sec))
            print(
                round(row["t"], 2),
                row["distance"],
                round(row["speed"], 2) if row["speed"] is not None else None,
                row["r2"],
                row["l2"],
                flush=True,
            )


if __name__ == "__main__":
    main()
