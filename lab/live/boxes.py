"""boxes.py <session> <seconds>...: the vehicle and person boxes the detector finds at those moments, as 0 to 1."""

import json
import sys

import cv2
from pilot.objects import Detector

d, seconds = sys.argv[1], [float(s) for s in sys.argv[2:]]
times = [json.loads(l)["t"] for l in open(d + "/frames.jsonl")]
video = cv2.VideoCapture(d + "/video.mp4")
detector = Detector()
for s in seconds:
    i = min(range(len(times)), key=lambda k: abs(times[k] - times[0] - s))
    video.set(cv2.CAP_PROP_POS_FRAMES, i)
    ok, f = video.read()
    rgb = cv2.cvtColor(cv2.resize(f, (1280, 720)), cv2.COLOR_BGR2RGB)
    out = []
    for o in detector.detect(rgb, exclude_player=False):
        x0, y0, x1, y1 = o.box
        out.append(
            f"{o.kind} {o.confidence:.2f} x {x0 / 1280:.2f}-{x1 / 1280:.2f} y {y0 / 720:.2f}-{y1 / 720:.2f} h {(y1 - y0) / 720:.2f}"
        )
    print(f"{s:5.1f}s", " | ".join(out))
