"""Read Pacific Bluffs captures without contacting the running pilot or console.

Run from pilot: env -u PS5_HOST .venv/bin/python ../lab/waypoint/p35_second_round.py.
Pairs match recorded command frames and the first settled decision, not pad-release frames.
"""

import json
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

from pilot.contract import HUD_RECT
from pilot.hud import read as read_hud
from pilot.minimap import read as read_minimap
from pilot.scene import TextReader
from pilot.waypoint import _map_features, land_at_cursor, map_motion, map_shift, read_map

PAIRS = {
    "133505": [(41468, 41563), (41565, 41683), (41685, 41805)],
    "132729": [
        (14356, 14455),
        (14457, 14566),
        (14961, 15056),
        (15058, 15164),
        (15555, 15650),
        (15652, 15760),
        (15762, 15877),
        (16269, 16365),
        (16367, 16474),
        (16876, 16978),
        (16980, 17087),
    ],
}
GAME = {"133505": [41293, 42111, 42193], "132729": [14181, 17393, 17478]}


def flow_support(before, after):
    a, b = _map_features(before), _map_features(after)
    if a is None or b is None:
        return None
    moved, forward, error = cv2.calcOpticalFlowPyrLK(a[0], b[0], a[1], None, winSize=(31, 31), maxLevel=4)
    returned, backward, _ = cv2.calcOpticalFlowPyrLK(b[0], a[0], moved, None, winSize=(31, 31), maxLevel=4)
    valid = (
        (forward[:, 0] == 1)
        & (backward[:, 0] == 1)
        & (error[:, 0] < 20)
        & (np.linalg.norm(a[1] - returned, axis=2)[:, 0] < 1.5)
    )
    return {"valid": int(valid.sum()), "total": len(valid), "fraction": float(valid.mean())}


def first_round_phase(before, after):
    windows = []
    for left in (250, 700):
        gradients = []
        for frame in (before, after):
            gray = cv2.cvtColor(frame[165:565, left:980], cv2.COLOR_RGB2GRAY).astype(np.float32)
            gradients.append(cv2.Sobel(gray, cv2.CV_32F, 1, 0) + cv2.Sobel(gray, cv2.CV_32F, 0, 1))
        delta, response = cv2.phaseCorrelate(*gradients)
        windows.append({"delta": delta, "response": response})
    return windows


def main():
    fixture = Path(__file__).parents[2] / "pilot/tests/fixtures/waypoint/live"
    reader = TextReader()
    output = {"frames": {}, "pairs": []}
    for stamp, pairs in PAIRS.items():
        recording = Path("/Users/kerim/recordings/pilot") / f"20261111-{stamp}"
        frames = {
            row["frame_id"]: row
            for row in map(json.loads, (recording / "frames.jsonl").read_text().splitlines())
        }
        capture = cv2.VideoCapture(str(recording / "video.mp4"))
        images = {}
        for frame_id in sorted({value for pair in pairs for value in pair} | set(GAME[stamp])):
            meta = frames[frame_id]
            capture.set(cv2.CAP_PROP_POS_FRAMES, meta["i"])
            ok, bgr = capture.read()
            assert ok
            frame = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            images[frame_id] = frame
            name = f"{stamp}-{frame_id}"
            cv2.imwrite(str(fixture / f"{name}.png"), bgr)
            text = reader.read(frame)
            picture = read_map(frame, text)
            map_result = asdict(picture)
            map_result["road_count"] = len(map_result.pop("roads"))
            x, y, w, h = HUD_RECT
            output["frames"][name] = {
                "recording": recording.name,
                "capture": meta,
                "text": asdict(text),
                "map": map_result,
                "land": land_at_cursor(frame) if picture.screen == "map" else None,
                "hud": asdict(read_hud(frame, text)),
                "minimap": asdict(read_minimap(frame[y : y + h, x : x + w])),
            }
        capture.release()
        for before, after in pairs:
            a, b = images[before], images[after]
            output["pairs"].append(
                {
                    "before": f"{stamp}-{before}",
                    "after": f"{stamp}-{after}",
                    "flow_support": flow_support(a, b),
                    "first_round_phase": first_round_phase(a, b),
                    "map_shift": map_shift(a, b),
                    "map_motion": map_motion(a, b),
                }
            )
    destination = Path(__file__).with_name("p35-second-round.json")
    destination.write_text(json.dumps(output, indent=2) + "\n")
    (fixture / "second-round.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output["pairs"], indent=2))


if __name__ == "__main__":
    main()
