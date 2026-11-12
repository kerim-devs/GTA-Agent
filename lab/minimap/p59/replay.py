"""Replay recordings through the damage flag before and after P59; read-only, no console.

    python lab/minimap/p59/replay.py SESSION_DIR [SESSION_DIR ...] [--base COMMIT] [--stretch A:B ...]

Every decoded frame goes through the minimap reader of the base commit and through the working tree;
the ticks of play.jsonl (when there is one) are joined by frame_id, so the shares are shares of pilot
ticks as in lab/minimap/p54. The result is one JSON line per session on stdout.
"""

import argparse
import json
import subprocess
import sys
import types
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "pilot/src"))
from pilot import minimap  # noqa: E402
from pilot.replay import hud_crop  # noqa: E402

BASE = "6cb7201"  # the integration branch before the repair


def baseline(commit):
    module = types.ModuleType("pilot.p59_baseline")
    sys.modules[module.__name__] = module
    source = subprocess.check_output(["git", "show", f"{commit}:pilot/src/pilot/minimap.py"], cwd=ROOT)
    exec(compile(source, f"{commit}:minimap.py", "exec"), module.__dict__)
    return module


def longest(rows, key):
    run = best = 0
    start = best_seconds = 0.0
    for row in rows:
        if row[key]:
            if not run:
                start = row["t"]
            run += 1
            best = max(best, run)
            best_seconds = max(best_seconds, row["t"] - start)
        else:
            run = 0
    return best, round(best_seconds, 3)


def share(rows, key):
    return sum(1 for row in rows if row[key])


def session(folder, commit=BASE, stretches=()):
    folder = Path(folder)
    old_reader = baseline(commit)
    frames = [json.loads(s) for s in (folder / "frames.jsonl").read_text().splitlines()]
    play = folder / "play.jsonl"
    ticks = [json.loads(s) for s in play.read_text().splitlines()] if play.exists() else []
    cap = cv2.VideoCapture(str(folder / "video.mp4"))
    by_id = {}
    index = 0
    while True:
        ok, bgr = cap.read()
        if not ok or index >= len(frames):
            break
        crop = hud_crop(bgr)
        by_id[frames[index]["frame_id"]] = (
            frames[index]["t"],
            int(old_reader.read(crop).corrupt),
            int(minimap.read(crop).corrupt),
        )
        index += 1
    if ticks:
        rows = [
            {
                "t": tick["t"],
                "before": by_id[tick["frame_id"]][1],
                "after": by_id[tick["frame_id"]][2],
                "live": int(tick["reading"]["corrupt"]),
            }
            for tick in ticks
            if tick["fresh"] and tick["frame_id"] in by_id
        ]
    else:
        rows = [{"t": t, "before": b, "after": a, "live": 0} for t, b, a in by_id.values()]
    result = {"session": folder.name, "frames": len(by_id), "ticks": len(rows)}
    for key in ("live", "before", "after"):
        result[key] = share(rows, key)
        result[f"{key}_longest"] = longest(rows, key)
    for stretch in stretches:
        a, b = (float(x) for x in stretch.split(":"))
        part = [row for row in rows if a <= row["t"] < b]
        result[stretch] = {key: share(part, key) for key in ("live", "before", "after")} | {
            "ticks": len(part)
        }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("sessions", nargs="+")
    parser.add_argument("--base", default=BASE)
    parser.add_argument("--stretch", action="append", default=[])
    args = parser.parse_args()
    with ProcessPoolExecutor(min(len(args.sessions), 8)) as pool:
        futures = [pool.submit(session, s, args.base, args.stretch) for s in args.sessions]
        for future in futures:
            print(json.dumps(future.result()), flush=True)


if __name__ == "__main__":
    main()
