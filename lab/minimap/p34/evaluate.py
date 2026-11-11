"""Replay every captured frame from the two P34 stretches, without a live source."""

import argparse
import csv
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "pilot/src"))


def load(path, name):
    spec = importlib.util.spec_from_file_location("pilot." + name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--recordings", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    before = load(args.before, "p34_before")
    after = load(ROOT / "pilot/src/pilot/minimap.py", "p34_after")
    args.output.mkdir(parents=True, exist_ok=True)
    # Match the first affected play tick through frame_id, not the MP4's nominal FPS.
    for session, start_i in (("20261111-123938", 983), ("20261111-123334", 1000)):
        source = args.recordings / session
        frames = [
            json.loads(line)
            for line in (source / "frames.jsonl").read_text().splitlines()
        ]
        cap = cv2.VideoCapture(str(source / "video.mp4"))
        counts = Counter()
        with (args.output / f"{session}.csv").open("w") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "i",
                    "frame_id",
                    "t",
                    "before",
                    "before_bearing",
                    "after",
                    "after_bearing",
                    "corrupt",
                ],
            )
            writer.writeheader()
            for frame in frames:
                ok, bgr = cap.read()
                if not ok:
                    raise RuntimeError(f"Missing video frame {frame['i']}")
                if frame["i"] < start_i:
                    continue
                crop = cv2.cvtColor(bgr[530:700, 30:290], cv2.COLOR_BGR2RGB)
                old, new = before.read(crop), after.read(crop)
                writer.writerow(
                    {
                        "i": frame["i"],
                        "frame_id": frame["frame_id"],
                        "t": frame["t"],
                        "before": old.route,
                        "before_bearing": old.bearing,
                        "after": new.route,
                        "after_bearing": new.bearing,
                        "corrupt": new.corrupt,
                    }
                )
                counts["frames"] += 1
                counts["before_" + old.route] += 1
                counts["after_" + new.route] += 1
                counts["new_purple"] += old.route != "purple" and new.route == "purple"
                counts["lost_purple"] += old.route == "purple" and new.route != "purple"
        cap.release()
        print(session, json.dumps(counts, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
