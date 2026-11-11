"""Label/check the recorded pause map, using capture indices rather than MP4 seconds.

Run from pilot: .venv/bin/python tools/inspect_map_clip.py --output ../lab/waypoint
The recording is read-only. OCR results are cached so checks can be repeated offline.
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from pilot.scene import SceneText, TextLine, TextReader
from pilot.waypoint import map_screen, read_map

RECORDINGS = Path("/Users/kerim/Documents/ChatGPT/gta/recordings")


def inspect(root, output):
    output.mkdir(parents=True, exist_ok=True)
    cache_path = output / "ocr.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    reader = None
    labels = []
    examples = []
    for recording in ("20261110-091812", "20261110-093238"):
        times = [json.loads(line) for line in (root / recording / "frames.jsonl").read_text().splitlines()]
        wanted = {}
        for t in np.arange(0, times[-1]["t"], 2):
            row = min(times, key=lambda row: abs(row["t"] - t))
            if recording.endswith("093238") and 383 <= row["t"] <= 396:
                continue
            wanted[row["i"]] = "non-map"
        if recording.endswith("093238"):
            wanted.update({i: "map" for i in range(8191, 8316)})
            pad = [json.loads(line) for line in (root / recording / "pad.jsonl").read_text().splitlines()]
            pad = [row for row in pad if 383 <= row["t"] <= 394]
            (output / "pad-clip.json").write_text(json.dumps(pad, indent=2) + "\n")
        by_index = {row["i"]: row for row in times}
        video = cv2.VideoCapture(str(root / recording / "video.mp4"))
        for index, label in sorted(wanted.items()):
            video.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = video.read()
            if not ok:
                raise RuntimeError(f"missing frame {recording}/{index}")
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            key = f"{recording}/{index}"
            if key not in cache:
                reader = reader or TextReader()
                result = reader.read(frame)
                cache[key] = [vars(line) for line in result.lines]
                if len(cache) % 20 == 0:
                    cache_path.write_text(json.dumps(cache, indent=2) + "\n")
                    print(f"OCR {len(cache)}", flush=True)
            text = SceneText(tuple(TextLine(**line) for line in cache[key]))
            screen = map_screen(frame, text)
            category = {
                ("20261110-093238", 10940): "weapon-wheel",
                ("20261110-093238", 856): "failed",
                ("20261110-093238", 886): "failed",
                ("20261110-093238", 7172): "cutscene",
                ("20261110-093238", 7211): "cutscene",
            }.get((recording, index), label)
            labels.append(
                {
                    "recording": recording,
                    **by_index[index],
                    "label": label,
                    "category": category,
                    "screen": screen,
                }
            )
            if label == "map" and index in {8191, 8192, 8216, 8221, 8252, 8286, 8305, 8315}:
                cv2.imwrite(str(output / f"map-{index}.jpg"), cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
                picture = read_map(frame, text)
                print(
                    f"frame {index}: {picture.screen}, cursor={picture.cursor}, player={picture.player}, "
                    f"missions={picture.missions}, waypoint={picture.waypoint}",
                    flush=True,
                )
            tile = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR), (256, 144))
            cv2.putText(
                tile,
                f"{recording[-6:]} i{index} {by_index[index]['t']:.2f}",
                (3, 15),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (0, 0, 255),
                1,
            )
            examples.append((label, tile))
        video.release()
    cache_path.write_text(json.dumps(cache, indent=2) + "\n")
    (output / "labels.json").write_text(json.dumps(labels, indent=2) + "\n")
    for label in ("map", "non-map"):
        tiles = [tile for name, tile in examples if name == label]
        for page, start in enumerate(range(0, len(tiles), 60)):
            chunk = tiles[start : start + 60]
            chunk += [np.zeros_like(chunk[0])] * ((-len(chunk)) % 6)
            montage = np.vstack([np.hstack(chunk[i : i + 6]) for i in range(0, len(chunk), 6)])
            cv2.imwrite(str(output / f"{label}-contact-{page}.jpg"), montage)
    positives = [row for row in labels if row["label"] == "map"]
    negatives = [row for row in labels if row["label"] == "non-map"]
    summary = {
        "map_frames": len(positives),
        "map_missed": [row["i"] for row in positives if not row["screen"]],
        "non_map_frames": len(negatives),
        "false_maps": [row for row in negatives if row["screen"]],
    }
    (output / "classification.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recordings", type=Path, default=RECORDINGS)
    parser.add_argument("--output", type=Path, default=Path("../lab/waypoint"))
    args = parser.parse_args()
    result = inspect(args.recordings, args.output)
    raise SystemExit(bool(result["map_missed"] or result["false_maps"] or result["non_map_frames"] < 300))
