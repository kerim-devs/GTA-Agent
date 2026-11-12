"""Measure, per recorded tick of a pilot session, whether the figure got anywhere.

    pilot/.venv/bin/python lab/foot/measure.py /Users/kerim/recordings/pilot/20261111-204712 lab/foot/stuck-session.jsonl

For every tick in play.jsonl that had a fresh frame it writes what was sent (left and right stick, the
skill), the blips the reader saw, and three ways of telling motion: `moving` as the pipeline hands it
to the skills (map motion over 0.2 s, its stationary band), `shift` (`pilot.foot.map_shift`, the ground
under the arrow over 0.5 s with the camera's turn taken out) and `world` (mean absolute difference of
the picture outside the HUD over 0.5 s, 0..255). Frames are decoded one at a time and not kept.
"""

import json
import sys
from collections import deque
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pilot" / "src"))

from pilot.conductor import minimap_crop
from pilot.foot import map_shift
from pilot.loop import Pipeline


class NoGPS:
    def poll(self, crop, timestamp):
        return None


def world(rgb):
    gray = cv2.cvtColor(
        cv2.resize(rgb, (160, 90), interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2GRAY
    )
    gray = gray.astype(np.int16)
    gray[60:, :40] = -1  # the HUD corner
    return gray


def main(recording: Path, out: Path):
    rows = [json.loads(line) for line in (recording / "play.jsonl").open()]
    ticks = {}
    for row in rows:
        if row.get("fresh") and row.get("reading") is not None:
            ticks.setdefault(row["frame_id"], row)
    frames = [json.loads(line) for line in (recording / "frames.jsonl").open()]
    capture = cv2.VideoCapture(str(recording / "video.mp4"))
    pipeline = Pipeline(gps_reader=NoGPS())
    history = deque()
    with out.open("w") as sink:
        for item in frames:
            ok, bgr = capture.read()
            if not ok:
                break
            row = ticks.get(item["frame_id"])
            if row is None:
                continue
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            t = row["t"]
            crop = minimap_crop(rgb)
            _reading, moving, _ = pipeline.step(crop, t, feedback=False)
            picture = world(rgb)
            while history and history[0][0] < t - 0.6:
                history.popleft()
            shift = diff = None
            if history and t - history[0][0] >= 0.4:
                _, old_crop, old_picture = history[0]
                shift = map_shift(old_crop, crop)
                both = (old_picture >= 0) & (picture >= 0)
                diff = float(np.abs(old_picture - picture)[both].mean())
            history.append((t, crop, picture))
            pad = row.get("sent_pad") or (row.get("result") or {}).get("pad") or {}
            reading = row["reading"]
            sink.write(
                json.dumps(
                    {
                        "t": round(t, 3),
                        "frame_id": item["frame_id"],
                        "skill": (row.get("skill") or {}).get("name"),
                        "left": pad.get("left"),
                        "right": pad.get("right"),
                        "minimap": reading["minimap"],
                        "corrupt": reading["corrupt"],
                        "arrow": reading["arrow"],
                        "blips": [
                            [b["color"], round(b["x"]), round(b["y"]), b["border"]]
                            for b in reading.get("blips", [])
                        ],
                        "moving": moving,
                        "shift": None if shift is None else round(shift, 2),
                        "world": None if diff is None else round(diff, 2),
                    }
                )
                + "\n"
            )
    capture.release()


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
