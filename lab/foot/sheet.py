"""Contact sheet of a session at the moments the guard's replay decided something.

    pilot/.venv/bin/python lab/foot/sheet.py RECORDING REPLAY.json OUT.jpg [TIMES]

Each tile is the frame at a first decision of `replay.py` (or at the comma-separated TIMES), with the
minimap beside it at twice its size, what was sent and what the guard would have sent.
"""

import json
import sys
from pathlib import Path

import cv2
import numpy as np


def main(recording: Path, replay: Path, out: Path, times=None):
    decisions = json.loads(replay.read_text())["decisions"]
    if times is None:
        marks = [
            (
                d["t"],
                f"sent {d['sent']['left']}  guard: {d['decision']} {d['would_send']['left']}",
            )
            for d in decisions
            if d["first"]
        ]
    else:
        marks = [(t, "") for t in times]
    frames = [json.loads(line) for line in (recording / "frames.jsonl").open()]
    stamps = np.array([f["t"] for f in frames])
    wanted = sorted((int(np.argmin(abs(stamps - t))), t, label) for t, label in marks)
    capture = cv2.VideoCapture(str(recording / "video.mp4"))
    index, tiles = 0, []
    for frame_index, t, label in wanted:
        while index <= frame_index:
            ok, bgr = capture.read()
            index += 1
        small = cv2.resize(bgr, (384, 216), interpolation=cv2.INTER_AREA)
        crop = cv2.resize(
            bgr[530:700, 30:290], (330, 216), interpolation=cv2.INTER_AREA
        )
        tile = np.zeros((246, 714, 3), np.uint8)
        tile[:216, :384] = small
        tile[:216, 384:] = crop
        cv2.putText(
            tile, f"{t:.1f}s", (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2
        )
        cv2.putText(
            tile, label, (8, 238), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1
        )
        tiles.append(tile)
    capture.release()
    if len(tiles) % 2:
        tiles.append(np.zeros_like(tiles[0]))
    sheet = np.vstack([np.hstack(tiles[i : i + 2]) for i in range(0, len(tiles), 2)])
    cv2.imwrite(str(out), sheet, [cv2.IMWRITE_JPEG_QUALITY, 72])


if __name__ == "__main__":
    extra = [float(x) for x in sys.argv[4].split(",")] if len(sys.argv) > 4 else None
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), extra)
