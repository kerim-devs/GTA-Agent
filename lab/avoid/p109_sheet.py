"""Small diagnostic JPEG from read-only footage; no inference."""

import json

import cv2
import numpy as np

from p107_measure import HERE, ROOT

rows = list(map(json.loads, (HERE / 'p109-073626-boxes.jsonl').open()))
capture = cv2.VideoCapture(str(ROOT / '20261114-073626/video.mp4'))
tiles = []
for t in (94.23, 94.83, 95.25, 95.61, 95.91, 96.19):
    row = min(rows, key=lambda r: abs(r['t'] - t))
    capture.set(cv2.CAP_PROP_POS_FRAMES, row['i'])
    ok, pixels = capture.read()
    if not ok:
        raise RuntimeError(t)
    for obj in row['objects']:
        x0, y0, x1, y1 = map(int, obj['box'])
        cv2.rectangle(pixels, (x0, y0), (x1, y1), (0, 255, 255), 2)
    cv2.line(pixels, (640, 240), (640, 500), (0, 255, 0), 1)
    pixels = cv2.resize(pixels, (512, 288))
    cv2.putText(pixels, f"{row['t']:.4f}s / frame {row['frame_id']}", (10, 24), cv2.FONT_HERSHEY_SIMPLEX, .55, (255, 255, 255), 1)
    tiles.append(pixels)
capture.release()
target = HERE / 'p109-night-sheet.jpg'
cv2.imwrite(str(target), np.vstack([np.hstack(tiles[i:i+2]) for i in range(0, 6, 2)]), [cv2.IMWRITE_JPEG_QUALITY, 70])
assert target.stat().st_size < 300000
print(target, target.stat().st_size)
