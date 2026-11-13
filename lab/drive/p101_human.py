"""Selected human obstacle contexts and exact controller intervals, decoded with cv2."""

import json
from bisect import bisect_right
from itertools import pairwise
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = Path("/Users/kerim/recordings/kerim")
WINDOWS = [
    ("20261113-142257", 119, 127),
    ("20261113-180503", 152, 164),
    ("20261113-184225", 425, 439),
    ("20261113-185312", 42, 50),
    ("20261113-185312", 90, 98),
    ("20261113-185312", 112, 120),
]


def main():
    cv2.setNumThreads(1)
    result = []
    for session, start, end in WINDOWS:
        folder = ROOT / session
        frames = [json.loads(line) for line in (folder / "frames.jsonl").read_text().splitlines()]
        pads = [json.loads(line) for line in (folder / "pad.jsonl").read_text().splitlines()]
        times = [p["t"] for p in pads]
        cap = cv2.VideoCapture(str(folder / "video.mp4"))
        thumbs = []
        for t in np.linspace(start, end, 8):
            f = min(frames, key=lambda f: abs(f["t"] - t))
            cap.set(cv2.CAP_PROP_POS_FRAMES, f["i"])
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError(f"Missing human frame {session}:{f['i']}")
            pad = pads[max(0, bisect_right(times, f["t"]) - 1)]
            image = cv2.resize(frame, (480, 270))
            cv2.rectangle(image, (0, 0), (480, 24), (0, 0, 0), -1)
            cv2.putText(
                image,
                f"{session[-6:]} {f['t']:.2f}s L2={pad.get('l2', 0):.2f} R2={pad.get('r2', 0):.2f}",
                (4, 16),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.43,
                (255, 255, 255),
                1,
            )
            thumbs.append(image)
        cap.release()
        cv2.imwrite(
            str(HERE / f"p101-human-{session[-6:]}-{start}.jpg"),
            np.concatenate(
                [np.concatenate(thumbs[i : i + 2], axis=1) for i in range(0, 8, 2)],
                axis=0,
            ),
        )
        intervals = []
        for p, q in pairwise(pads):
            a, b = max(start, p["t"]), min(end, q["t"])
            if b <= a:
                continue
            key = (
                p.get("l2", 0) > 0.2,
                p.get("r2", 0) > 0.5,
                -1 if p.get("left", [0, 0])[0] < -0.5 else 1 if p.get("left", [0, 0])[0] > 0.5 else 0,
            )
            if intervals and intervals[-1][2] == key:
                intervals[-1][1] = b
            else:
                intervals.append([a, b, key])
        result.append(
            {
                "session": session,
                "start": start,
                "end": end,
                "intervals": intervals,
                "pad_rows": [p for p in pads if start <= p["t"] <= end],
            }
        )
    (HERE / "p101-human.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
