"""Decode selected P98 context frames without changing the recordings."""

import json
from pathlib import Path

import cv2
import numpy as np

cv2.setNumThreads(1)
root = Path(__file__).resolve().parent
scenes = [
    ("pilot", "20261113-225006", [60.5, 83.5, 91.4, 205, 210, 214, 218, 220, 225]),
    ("pilot", "20261113-230030", [569.5, 712.1, 725.4]),
    ("kerim", "20261113-141634", [120, 150, 180]),
    ("kerim", "20261113-031159", [15, 45, 75]),
]
for kind, name, times in scenes:
    d = Path("/Users/kerim/recordings") / kind / name
    frames = [json.loads(x) for x in (d / "frames.jsonl").read_text().splitlines()]
    cap = cv2.VideoCapture(str(d / "video.mp4"))
    images = []
    for t in times:
        f = min(frames, key=lambda f: abs(f["t"] - t))
        cap.set(cv2.CAP_PROP_POS_FRAMES, f["i"])
        ok, bgr = cap.read()
        assert ok
        im = cv2.resize(bgr, (640, 360))
        cv2.putText(im, f"{name} {f['t']:.2f}s", (12, 25), 0, 0.6, (0, 255, 255), 2)
        images.append(im)
    cap.release()
    while len(images) % 3:
        images.append(np.zeros_like(images[0]))
    sheet = np.vstack([np.hstack(images[i : i + 3]) for i in range(0, len(images), 3)])
    cv2.imwrite(str(root / f"p98-context-{name}.jpg"), sheet)
