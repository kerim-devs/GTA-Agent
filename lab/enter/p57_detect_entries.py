"""Dump fresh detections at all 71 entries using the original recording clock.

Run outside the sandbox. This only reads recordings and emits JSON; no console
connection is made. Boxes require target matching before accuracy can be scored.
"""

import argparse
import bisect
import json
import sys
from dataclasses import asdict, replace
from itertools import groupby
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot/src"))
from pilot.vehicle_entry import occupant_visible, within_reach


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def dump_entries(detector, base, events):
    result = []
    for session, grouped in groupby(
        sorted(events, key=lambda e: (e["session"], e["start"])),
        key=lambda e: e["session"],
    ):
        folder = base / "kerim" / session
        frames = records(folder / "frames.jsonl")
        times = [frame["t"] for frame in frames]
        video = cv2.VideoCapture(str(folder / "video.mp4"))
        try:
            for action in grouped:
                line = action["line"]
                # Action schema uses start/end; fail loudly rather than guessing a
                # video media timestamp if the source format changes.
                start = action["start"]
                samples = []
                for delta in (-1, -0.5, 0, 0.5, 1):
                    requested = max(times[0], start + delta)
                    index = min(bisect.bisect_left(times, requested), len(frames) - 1)
                    if index and abs(times[index - 1] - requested) < abs(
                        times[index] - requested
                    ):
                        index -= 1
                    frame = frames[index]
                    video.set(cv2.CAP_PROP_POS_FRAMES, frame.get("i", index))
                    ok, bgr = video.read()
                    if not ok:
                        raise RuntimeError(
                            f"{folder.name}: cannot decode manifest frame {index}"
                        )
                    objects = detector.detect(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
                    vehicles = []
                    for obj in objects:
                        if obj.kind not in {"car", "bus", "truck", "motorcycle"}:
                            continue
                        a, b, c, d = obj.box
                        normalized = replace(
                            obj, box=(a / 1280, b / 720, c / 1280, d / 720)
                        )
                        vehicles.append(
                            {
                                "box": list(obj.box),
                                "kind": obj.kind,
                                "occupant_box": occupant_visible(normalized, objects),
                                "within_reach": within_reach(normalized),
                            }
                        )
                    samples.append(
                        {
                            "requested_t": requested,
                            "frame_t": frame["t"],
                            "frame_index": frame.get("i", index),
                            "objects": [asdict(obj) for obj in objects],
                            "signals": vehicles,
                        }
                    )
                result.append(
                    {
                        "session": folder.name,
                        "action_line": line,
                        "action_start": start,
                        "samples": samples,
                    }
                )
        finally:
            video.release()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--recordings", type=Path, default=Path("/Users/kerim/recordings")
    )
    parser.add_argument(
        "--entries",
        type=Path,
        default=Path(__file__).with_name("p57-entries.json"),
        help="Frozen event snapshot; concurrent new classifications do not change this cohort",
    )
    args = parser.parse_args()
    from pilot.objects import Detector

    result = dump_entries(
        Detector(), args.recordings, json.loads(args.entries.read_text())["events"]
    )
    json.dump(
        {
            "scope": "Fresh boxes and occupancy hints, not ground-truth accuracy. Match the actual target to p57-entries.json before scoring.",
            "entries": result,
        },
        sys.stdout,
        indent=2,
    )
    print()
