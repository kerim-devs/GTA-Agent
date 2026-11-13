"""Reproduce P79's offline wheel confusion table; never connects to a console.

Run from the repository root with pilot/.venv/bin/python lab/story/audit_switch.py.
Only the small JSON result is written; frames remain in the recordings folder.
"""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import cv2

from pilot.wheel import wheel

ROOT = Path(__file__).resolve().parents[2]


def decode(video, indices):
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        raise RuntimeError(f"Cannot open {video}")
    try:
        # Match the HUD manifest's exact OpenCV frame-index decoding.
        for index in sorted(indices):
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()
            if not ok:
                raise RuntimeError(f"Cannot decode {video} frame {index}")
            yield index, cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    finally:
        capture.release()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--recordings", type=Path, default=Path("/Users/kerim/recordings"))
    parser.add_argument(
        "--wifi-recordings", type=Path, default=Path("/Users/kerim/Documents/ChatGPT/gta/recordings")
    )
    parser.add_argument("--output", type=Path, default=ROOT / "lab/story/p79-wheel-audit.json")
    args = parser.parse_args()
    labels = json.loads((ROOT / "lab/hud/labels.json").read_text())
    rows = next(
        value for key, value in labels.items() if isinstance(value, list) and value and "source" in value[0]
    )
    results = []
    for source, metadata in labels["sources"].items():
        wanted = {row["i"]: row for row in rows if row["source"] == source}
        root = args.wifi_recordings if metadata["root"] == "wifi" else args.recordings / "pilot"
        video = root / metadata["recording"] / "video.mp4"
        for index, frame in decode(video, wanted):
            row = wanted[index]
            digest = hashlib.sha256(frame.tobytes()).hexdigest()
            if digest != row["rgb_sha256"]:
                raise RuntimeError(f"RGB hash mismatch for {row['id']}")
            reading = wheel(frame)
            results.append(
                {
                    "id": row["id"],
                    "screen": row["screen"],
                    "expected": "none",
                    "actual": reading.highlight if reading.visible else "none",
                    "visible": reading.visible,
                    "rgb_sha256": digest,
                }
            )

    ranges = [
        ("20261111-190825", 24290, 24349, "top"),
        ("20261111-190825", 24360, 24419, "left"),
        ("20261112-105402", 9698, 9704, "right"),
    ]
    for recording, start, end, expected in ranges:
        video = args.recordings / "kerim" / recording / "video.mp4"
        for index, frame in decode(video, range(start, end + 1)):
            reading = wheel(frame)
            results.append(
                {
                    "id": f"{recording}:{index}",
                    "expected": expected,
                    "actual": reading.highlight if reading.visible else "none",
                    "visible": reading.visible,
                    "disabled": sorted(reading.disabled),
                    "rgb_sha256": hashlib.sha256(frame.tobytes()).hexdigest(),
                }
            )
    confusion = Counter((row["expected"], row["actual"]) for row in results)
    report = {
        "scope": (
            "127 wheel frames and the existing 200 hash-verified HUD negatives. "
            "Adjacent frames are correlated; calibration references come from the same recordings. "
            "No bottom-positive example is available."
        ),
        "negative_screens": dict(Counter(row["screen"] for row in results if "screen" in row)),
        "confusion": [
            {"expected": expected, "actual": actual, "count": count}
            for (expected, actual), count in sorted(confusion.items(), key=lambda item: str(item[0]))
        ],
        "wheel_false_positives": sum(row["visible"] for row in results if row["expected"] == "none"),
        "wheel_false_negatives": sum(not row["visible"] for row in results if row["expected"] != "none"),
        "results": results,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "results"}, indent=2))


if __name__ == "__main__":
    main()
