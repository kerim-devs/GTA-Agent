"""Render timestamp-based context around the twenty selected P40 divergences."""

import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent / "out"
moments = json.loads((ROOT / "divergences.json").read_text())
for group in range(0, len(moments), 4):
    strips = []
    for moment in moments[group:group + 4]:
        recording = Path(moment["recording"])
        frames = [json.loads(line) for line in (recording / "frames.jsonl").read_text().splitlines()]
        times = np.array([frame["t"] for frame in frames])
        capture = cv2.VideoCapture(str(recording / "video.mp4"))
        pictures = []
        for offset in (-1, 0, 1):
            index = int(np.argmin(abs(times - moment["t"] - offset)))
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()
            if not ok:
                raise RuntimeError(f"missing review frame {recording}:{index}")
            frame = cv2.resize(frame, (640, 360))
            cv2.putText(frame, f"#{moment['rank']} {recording.name} {times[index]:.3f}s", (10, 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
            pictures.append(frame)
        capture.release()
        strips.append(np.hstack(pictures))
    cv2.imwrite(str(ROOT / f"context-{group // 4 + 1:02d}.jpg"), np.vstack(strips))
