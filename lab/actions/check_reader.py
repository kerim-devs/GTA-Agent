"""Read samples of the data set back through `training_frames`, as a training job would, and draw them.

    check_reader.py <index.jsonl> <recording name> [--count 12] [--seed 7] [--out sheet.jpg]

Checks that every frame comes back as 720x1280 RGB at the index's frame number, by decoding the same
frame a second way (seeking), and puts the frames with their labels on one sheet.
"""

import argparse
import json
import tempfile
import time
from pathlib import Path

import cv2
import numpy as np

from pilot.actions import training_frames


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("index", type=Path)
    parser.add_argument("name")
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "sheets" / "reader-check.jpg")
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.index.read_text().splitlines()]
    rows = [row for row in rows if Path(row["recording"]).name == args.name]
    with tempfile.TemporaryDirectory() as scratch:
        subset = Path(scratch) / "index.jsonl"
        subset.write_text("".join(json.dumps(row) + "\n" for row in rows))
        started = time.perf_counter()
        pairs = list(training_frames(subset, limit=args.count, seed=args.seed))
        elapsed = time.perf_counter() - started
    tiles, same = [], 0
    for frame, row in pairs:
        assert frame.shape == (720, 1280, 3) and frame.dtype == np.uint8
        seek = cv2.VideoCapture(str(Path(row["recording"]) / "video.mp4"))
        seek.set(cv2.CAP_PROP_POS_FRAMES, row["frame"])
        ok, bgr = seek.read()
        seek.release()
        same += bool(ok) and float(np.abs(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(int) - frame).mean()) < 1.0
        tile = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR), (400, 225), interpolation=cv2.INTER_AREA)
        text = f"{row['time']:.1f}s f{row['frame']} {row['action']}"
        cv2.putText(tile, text, (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)
        tiles.append(tile)
    while len(tiles) % 4:
        tiles.append(np.zeros_like(tiles[0]))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(args.out), np.vstack([np.hstack(tiles[k : k + 4]) for k in range(0, len(tiles), 4)]))
    print(
        f"{len(pairs)} samples of {len(rows)} from {args.name} in {elapsed:.1f} s; "
        f"{same} equal to the frame found by seeking; sheet {args.out}"
    )


if __name__ == "__main__":
    main()
