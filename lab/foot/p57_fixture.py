"""Writes pilot/tests/fixtures/p57-walks.npz: map crops of the four recorded walks, and what the walk as it was
before P57 (foot.py of BASE) did on them with a guard that lets every wanted stick through.

Run from the repository root: env -u PS5_HOST pilot/.venv/bin/python lab/foot/p57_fixture.py
Reads recordings, never writes under them, never touches the console. About twenty ticks a walk: a regular
spacing plus the ticks on which the map said lane or side, so that those are in it.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot/src"))
sys.path.insert(0, str(ROOT / "lab/foot"))
from p57_replay import NoGPS, old_walk_class, records
from pilot.contract import Observation, Reading
from pilot.foot import Steer, find_road, hud_crop
from pilot.loop import Pipeline

SESSIONS = ("122242", "110418", "110736", "111053")
EVERY = 25  # ticks between the regular samples
KNOWN = 6  # at most this many more, taken from the ticks with a lane or side reading
FLAT = Reading("flat", "none", None, None, 0.0, False, 0.9)
OUT = ROOT / "pilot/tests/fixtures/p57-walks.npz"


def collect(suffix):
    folder = Path("/Users/kerim/recordings/pilot") / ("20261112-" + suffix)
    play, frames = records(folder / "play.jsonl"), records(folder / "frames.jsonl")
    ticks = {}
    for row in play:
        if row.get("reading"):
            ticks.setdefault(row["frame_id"], []).append(row)
    start = next(r["t"] for r in play if (r.get("skill") or {}).get("name") == "walk_road")
    pipeline = Pipeline(gps_reader=NoGPS())
    video = cv2.VideoCapture(str(folder / "video.mp4"))
    regular, known = [], []
    count = 0
    for meta in frames:
        ok, bgr = video.read()
        if not ok:
            break
        for row in ticks.get(meta["frame_id"], []):
            t = row["t"]
            crop = hud_crop(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
            reading, _, _ = pipeline.step(crop, t, feedback=False)
            if t < start or reading.corrupt or reading.minimap != "flat":
                continue
            road = find_road(crop)
            item = (t, crop.copy())
            if count % EVERY == 0:
                regular.append(item)
            elif road is not None and road.position != "unknown":
                known.append(item)
            count += 1
    video.release()
    picked = known[:: max(1, len(known) // KNOWN)][:KNOWN]
    return sorted(regular + picked, key=lambda item: item[0])


def main():
    old = old_walk_class()
    arrays, meta = {}, {}
    for suffix in SESSIONS:
        samples = collect(suffix)
        walk = old({"duration": 30})
        walk.guard = SimpleNamespace(step=lambda observation, want: Steer(want))
        lefts = []
        for t, crop in samples:
            frame = np.zeros((720, 1280, 3), np.uint8)
            frame[530:700, 30:290] = crop
            result = walk.step(Observation(FLAT, None, t, frame=frame))
            lefts.append(result.pad.left)
        arrays[suffix + "_t"] = np.array([t for t, _ in samples])
        arrays[suffix + "_before"] = np.array(lefts)
        for index, (_, crop) in enumerate(samples):
            ok, png = cv2.imencode(".png", cv2.cvtColor(crop, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_PNG_COMPRESSION, 9])
            assert ok
            arrays[f"{suffix}_{index:02d}"] = png.ravel()
        meta[suffix] = len(samples)
    arrays["meta"] = np.array(json.dumps(meta))
    np.savez_compressed(OUT, **arrays)
    print(OUT, OUT.stat().st_size, meta)


if __name__ == "__main__":
    main()
