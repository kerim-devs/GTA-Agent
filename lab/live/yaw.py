"""yaw.py <session> <from> <to> [<from> <to>...]: how far the picture moved sideways in each span.

Consecutive frames are aligned by phase correlation on the band above the figure's feet; the first
span is taken as a turn of more than a full circle and gives the pixels of 360 degrees from the
moment the first frame comes round again.
"""

import json
import sys

import cv2
import numpy as np

d = sys.argv[1]
spans = [(float(a), float(b)) for a, b in zip(sys.argv[2::2], sys.argv[3::2])]
times = np.array([json.loads(l)["t"] for l in open(d + "/frames.jsonl")])
times -= times[0]
video = cv2.VideoCapture(d + "/video.mp4")


def band(i):
    video.set(cv2.CAP_PROP_POS_FRAMES, i)
    ok, f = video.read()
    g = cv2.cvtColor(cv2.resize(f, (640, 360)), cv2.COLOR_BGR2GRAY).astype(np.float32)
    return g[20:230, 150:640]  # no minimap, no ground


def shifts(a, b):
    first, last = np.searchsorted(times, a), np.searchsorted(times, b)
    video.set(cv2.CAP_PROP_POS_FRAMES, int(first))
    out, prev, frames = [], None, []
    for i in range(first, last):
        ok, f = video.read()
        if not ok:
            break
        g = cv2.cvtColor(cv2.resize(f, (640, 360)), cv2.COLOR_BGR2GRAY).astype(
            np.float32
        )[20:230, 150:640]
        if prev is not None:
            (dx, dy), response = cv2.phaseCorrelate(
                prev, g, cv2.createHanningWindow(g.shape[::-1], cv2.CV_32F)
            )
            out.append((times[i], dx, response))
        prev = g
        frames.append(g)
    return out, frames


import os

circle = float(os.environ["CIRCLE"]) if "CIRCLE" in os.environ else None
known = circle is not None
for n, (a, b) in enumerate(spans):
    out, frames = shifts(a, b)
    dx = np.array([o[1] for o in out])
    t = np.array([o[0] for o in out])
    total = -dx.sum()  # the picture moves left when the camera turns right
    moving = np.abs(dx) > 0.3
    rate = (
        -dx[moving].sum() / (t[moving][-1] - t[moving][0]) if moving.sum() > 2 else 0.0
    )
    line = f"{a:5.1f}-{b:5.1f}s  {total:8.0f} px  {rate:7.0f} px/s while moving  response {np.median([o[2] for o in out]):.2f}"
    if n == 0 and not known:
        ref = frames[5]
        score = [
            float(cv2.matchTemplate(g, ref, cv2.TM_CCOEFF_NORMED)[0, 0]) for g in frames
        ]
        cum = np.concatenate([[0], np.cumsum(-dx)])
        later = [(s, k) for k, s in enumerate(score) if k > 60]
        best, k = max(later)
        circle = cum[k] - cum[5]
        line += f"  | first frame comes round at {t[k - 1] - t[5]:.2f}s (match {best:.2f}), {circle:.0f} px a circle"
    if circle:
        line += f"  = {total / circle * 360:6.0f} deg, {rate / circle * 360:5.0f} deg/s"
    print(line)
