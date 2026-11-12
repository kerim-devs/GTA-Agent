"""Replay saved replies and compare accepted modes with the same frames' minimaps, offline."""

import argparse
import json
from pathlib import Path

import cv2
from pilot.conductor import minimap_crop
from pilot.judge import ModeFilter, parse
from pilot.minimap import read


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--recording",
        type=Path,
        default=Path("/Users/kerim/recordings/kerim/20261111-065022/video.mp4"),
    )
    args = parser.parse_args()
    video = cv2.VideoCapture(str(args.recording))
    totals = {
        "rows": 0,
        "raw_changes": 0,
        "accepted_changes": 0,
        "state_changes": 0,
        "unset": 0,
        "mismatches": 0,
        "all_mismatches": 0,
    }
    try:
        for path in sorted(Path(__file__).with_name("sequences").glob("*.jsonl")):
            modes = ModeFilter()
            previous_raw = previous_accepted = None
            counts = dict.fromkeys(totals, 0)
            transitions = []
            for line in path.read_text().splitlines():
                row = json.loads(line)
                judgment = parse(row["choice"], row["time"], row["seconds"], row["model"])
                raw = judgment.answers["mode"].value
                accepted = modes.update(judgment, row["time"])
                counts["raw_changes"] += previous_raw is not None and raw != previous_raw
                changed = accepted != previous_accepted
                counts["accepted_changes"] += previous_accepted is not None and changed
                counts["state_changes"] += changed
                if changed:
                    transitions.append({"frame": row["frame"], "capture": row["time"], "mode": accepted})
                previous_raw, previous_accepted = raw, accepted
                video.set(cv2.CAP_PROP_POS_FRAMES, row["frame"])
                ok, bgr = video.read()
                if not ok:
                    raise RuntimeError(f"cannot decode frame {row['frame']} from {args.recording}")
                minimap = read(minimap_crop(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))).minimap
                map_mode = {"flat": "foot", "tilted": "vehicle", "none": "none"}[minimap]
                counts["rows"] += 1
                counts["unset"] += accepted is None
                counts["mismatches"] += accepted is not None and accepted != map_mode
                counts["all_mismatches"] += accepted != map_mode
            print(json.dumps(dict(sequence=path.stem, **counts, transitions=transitions)))
            for key, value in counts.items():
                totals[key] += value
        print(json.dumps({"total": totals}))
    finally:
        video.release()


if __name__ == "__main__":
    main()
