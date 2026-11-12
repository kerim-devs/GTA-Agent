"""Audit stored OCR, or repeat it on fresh frames outside the sandbox."""

import argparse
import json
from collections import Counter
from pathlib import Path

from pilot.legend import read_legend


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fresh", type=Path, help="Video to read with native Vision instead of stored lines")
    args = parser.parse_args()
    stored = json.loads(Path(__file__).with_name("readings.json").read_text())["readings"]
    capture = reader = None
    if args.fresh:
        import cv2

        from pilot.scene import TextReader

        capture = cv2.VideoCapture(str(args.fresh))
        if not capture.isOpened():
            raise RuntimeError("could not open recording")
        reader = TextReader()
    audit = []
    try:
        for sample in stored:
            lines, frame = sample["lines"], None
            if capture is not None:
                capture.set(cv2.CAP_PROP_POS_FRAMES, sample["i"])
                ok, frame = capture.read()
                if not ok:
                    raise RuntimeError(f"could not decode frame {sample['i']}")
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                lines = reader.read(frame).lines
            picture = read_legend(lines, frame if capture is not None else None)
            audit.append(
                {
                    "t": sample["t"],
                    "screen": picture.screen,
                    "selected": picture.selected.name if picture.selected else None,
                    "counter": [picture.position, picture.total] if picture.position else None,
                    "distance_m": picture.distance,
                }
            )
    finally:
        if capture is not None:
            capture.release()
    summary = {
        "samples": len(audit),
        "counters": sum(row["counter"] is not None for row in audit),
        "selected": dict(Counter(row["selected"] for row in audit if row["selected"])),
        "waypoint_samples": sum(row["distance_m"] is not None for row in audit),
        "unreadable_selection": sum(row["screen"] == "map" and row["selected"] is None for row in audit),
    }
    print(json.dumps({"summary": summary, "readings": audit}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
