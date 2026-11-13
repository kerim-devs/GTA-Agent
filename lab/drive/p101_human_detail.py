"""Short human recovery windows: controller timing and rotation-corrected map translation."""

import json
from bisect import bisect_right
from pathlib import Path

import cv2
import numpy as np

from pilot.minimap import read
from pilot.motion import _BASE, _X0, _X1, _Y0, _Y1
from pilot.replay import hud_crop

HERE = Path(__file__).resolve().parent
ROOT = Path("/Users/kerim/recordings/kerim")
WINDOWS = [
    ("20261113-185312", 91.5, 96.5),
    ("20261113-185312", 113.5, 117.5),
    ("20261113-184225", 428, 437),
]


def displacement(previous, current):
    a = cv2.cvtColor(previous[_Y0:_Y1, _X0:_X1], cv2.COLOR_RGB2GRAY)
    b = cv2.cvtColor(current[_Y0:_Y1, _X0:_X1], cv2.COLOR_RGB2GRAY)
    points = cv2.goodFeaturesToTrack(a, 60, 0.015, 5, mask=_BASE)
    if points is None:
        return None
    target, status, error = cv2.calcOpticalFlowPyrLK(a, b, points, None, winSize=(15, 15), maxLevel=2)
    valid = (status.ravel() > 0) & (error.ravel() < 15)
    if valid.sum() < 8:
        return None
    matrix, mask = cv2.estimateAffinePartial2D(
        points[valid], target[valid], method=cv2.RANSAC, ransacReprojThreshold=0.8
    )
    if matrix is None or mask.sum() < 8:
        return None
    anchor = np.array([123 - _X0, 117 - _Y0, 1.0])
    shift = matrix @ anchor - anchor[:2]
    return shift.tolist()


def main():
    cv2.setNumThreads(1)
    result = []
    for session, start, end in WINDOWS:
        folder = ROOT / session
        frames = [json.loads(line) for line in (folder / "frames.jsonl").read_text().splitlines()]
        pads = [json.loads(line) for line in (folder / "pad.jsonl").read_text().splitlines()]
        times = [p["t"] for p in pads]
        cap = cv2.VideoCapture(str(folder / "video.mp4"))
        first = next(f["i"] for f in frames if f["t"] >= start)
        cap.set(cv2.CAP_PROP_POS_FRAMES, first)
        samples, thumbs, previous, at = [], [], None, start
        for f in frames[first:]:
            if f["t"] > end:
                break
            if not cap.grab():
                raise RuntimeError("Missing human frame")
            if f["t"] < at:
                continue
            at = f["t"] + 0.2
            ok, image = cap.retrieve()
            assert ok
            crop = hud_crop(image)
            reading = read(crop)
            shift = None if previous is None else displacement(previous, crop)
            previous = crop
            pad = pads[max(0, bisect_right(times, f["t"]) - 1)]
            samples.append(
                {
                    "t": f["t"],
                    "i": f["i"],
                    "shift_px": shift,
                    "arrow": reading.arrow,
                    "corrupt": reading.corrupt,
                    "pad": pad,
                }
            )
            thumb = cv2.resize(image, (320, 180))
            cv2.rectangle(thumb, (0, 0), (320, 22), (0, 0, 0), -1)
            cv2.putText(
                thumb,
                f"{f['t']:.2f} L2 {pad.get('l2', 0):.1f} R2 {pad.get('r2', 0):.1f}",
                (3, 15),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (255, 255, 255),
                1,
            )
            thumbs.append(thumb)
        cap.release()
        while len(thumbs) % 4:
            thumbs.append(np.zeros_like(thumbs[0]))
        cv2.imwrite(
            str(HERE / f"p101-human-detail-{session[-6:]}-{start}.jpg"),
            np.concatenate([np.concatenate(thumbs[i : i + 4], axis=1) for i in range(0, len(thumbs), 4)]),
        )
        result.append({"session": session, "start": start, "end": end, "samples": samples})
    (HERE / "p101-human-detail.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
