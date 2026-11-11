"""sheet.py <session> <out.jpg> <seconds>... : frames at those seconds of a pilot session, side by side."""

import json
import sys

import cv2
import numpy as np

d, out, seconds = sys.argv[1], sys.argv[2], [float(s) for s in sys.argv[3:]]
times = [json.loads(l)["t"] for l in open(d + "/frames.jsonl")]
video = cv2.VideoCapture(d + "/video.mp4")
tiles = []
for s in seconds:
    i = min(range(len(times)), key=lambda k: abs(times[k] - times[0] - s))
    video.set(cv2.CAP_PROP_POS_FRAMES, i)
    ok, f = video.read()
    if not ok:
        continue
    f = cv2.resize(f, (640, 360))
    cv2.putText(f, f"{s:.1f}s", (8, 24), 0, 0.7, (0, 255, 255), 2)
    tiles.append(f)
cols = 3 if len(tiles) > 4 else len(tiles)
while len(tiles) % cols:
    tiles.append(np.zeros_like(tiles[0]))
cv2.imwrite(
    out, np.vstack([np.hstack(tiles[i : i + cols]) for i in range(0, len(tiles), cols)])
)
