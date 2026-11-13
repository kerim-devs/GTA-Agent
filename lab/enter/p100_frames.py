"""Decode only the named audit frames, without sending any inputs."""

import bisect
import json
from pathlib import Path

import cv2
import numpy as np

OUT = Path(__file__).parent
HUMAN = {
    "20261111-190825": (85, 102),
    "20261111-165543": (207, 225),
    "20261111-171046": (133, 158),
    "20261112-085011": (874, 889),
    "20261111-185323": (793, 812),
    "20261111-182316": (187, 207),
}


def sheet(folder, times, name):
    rows = [json.loads(line) for line in (folder / "frames.jsonl").open()]
    clock = [r["t"] for r in rows]
    video = cv2.VideoCapture(str(folder / "video.mp4"))
    tiles = []
    for t in times:
        i = bisect.bisect_left(clock, t)
        video.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, bgr = video.read()
        if not ok:
            raise RuntimeError((folder, i))
        tile = cv2.resize(bgr, (480, 270))
        cv2.rectangle(tile, (0, 0), (480, 23), (0, 0, 0), -1)
        cv2.putText(
            tile,
            f"{folder.name} {clock[i]:.3f}s f{i}",
            (8, 17),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.43,
            (255, 255, 255),
            1,
        )
        tiles.append(tile)
    video.release()
    while len(tiles) % 4:
        tiles.append(np.zeros_like(tiles[0]))
    cv2.imwrite(
        str(OUT / name),
        np.vstack([np.hstack(tiles[i : i + 4]) for i in range(0, len(tiles), 4)]),
    )


if __name__ == "__main__":
    cv2.setNumThreads(1)
    for session, (start, end) in HUMAN.items():
        sheet(
            Path("/Users/kerim/recordings/kerim") / session,
            np.arange(start, end + 0.1, 1),
            f"p100-human-{session}.jpg",
        )
