"""Replay every recorded frame without connecting to a console."""
import argparse
import csv
import json
from pathlib import Path
import sys

import cv2

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "pilot/src"))
from pilot import minimap
from pilot.replay import hud_crop

SESSIONS = ("20261111-130955", "20261111-131346", "20261111-131628")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recordings", type=Path, default=Path("/Users/kerim/recordings/pilot"))
    parser.add_argument("--phase", choices=("before", "after"), required=True)
    args = parser.parse_args()
    if args.phase == "before":
        from before import module as reader
    else:
        reader = minimap
    out = Path(__file__).parent
    results = {}
    for session in SESSIONS:
        folder = args.recordings / session
        frames = [json.loads(line) for line in (folder / "frames.jsonl").read_text().splitlines()]
        ticks = [json.loads(line) for line in (folder / "play.jsonl").read_text().splitlines()]
        by_id = {}
        for tick in ticks:
            by_id.setdefault(tick["frame_id"], []).append(tick)
        cap = cv2.VideoCapture(str(folder / "video.mp4"))
        counts = dict(frames=0, corrupt=0, matched_ticks=0, corrupt_ticks=0, recorded_corrupt_ticks=0)
        with (out / f"{session}-{args.phase}.csv").open("w") as stream:
            writer = csv.DictWriter(stream, fieldnames=("i", "frame_id", "t", "corrupt", "blocks", "blocks_near", "confidence"))
            writer.writeheader()
            for frame in frames:
                ok, bgr = cap.read()
                if not ok:
                    raise RuntimeError(f"Missing video frame {session}: {frame['i']}")
                crop = hud_crop(bgr)
                reading, debug = reader._analyse(crop, keep=True)
                writer.writerow({**frame, "corrupt": int(reading.corrupt), "blocks": debug["blocks"], "blocks_near": debug["blocks_near"], "confidence": reading.confidence})
                counts["frames"] += 1
                counts["corrupt"] += int(reading.corrupt)
                for tick in by_id.get(frame["frame_id"], []):
                    counts["matched_ticks"] += 1
                    counts["corrupt_ticks"] += int(reading.corrupt)
                    counts["recorded_corrupt_ticks"] += int(tick.get("reading", {}).get("corrupt", False))
        cap.release()
        counts["unmatched_ticks"] = len(ticks) - counts["matched_ticks"]
        results[session] = counts
        print(session, counts, flush=True)
    (out / f"sessions-{args.phase}.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
