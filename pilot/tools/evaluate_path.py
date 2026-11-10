"""Reproducible offline P8 picture selection, adjacent-frame jitter and replay evidence."""

import argparse
import json
import math
import random
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

from pilot.drive import DriveConfig, Driver
from pilot.loop import Pipeline
from pilot.minimap import read
from pilot.replay import diagnostics, hud_crop, json_lines


def angle(point):
    return math.degrees(math.atan2(*point))


def difference(a, b):
    return abs((a - b + 180) % 360 - 180)


def clean(reading):
    return (
        reading.minimap == "tilted"
        and reading.route != "none"
        and not reading.corrupt
        and reading.confidence >= 0.5
    )


def sheets(crops, selected, out):
    for offset in range(0, len(selected), 10):
        sheet = np.full((5 * 380, 2 * 1040, 3), 28, np.uint8)
        for tile, item in enumerate(selected[offset : offset + 10]):
            crop = crops[item["k"]]
            raw = cv2.resize(
                cv2.cvtColor(crop, cv2.COLOR_RGB2BGR), (520, 340), interpolation=cv2.INTER_NEAREST
            )
            overlay = raw.copy()
            for x, y in item["path"]:
                cv2.circle(
                    overlay, (round((123 + x) * 2), round((117 - y) * 2)), 3, (40, 40, 255), 1, cv2.LINE_AA
                )
            row, col = divmod(tile, 2)
            y, x = row * 380, col * 1040
            sheet[y + 40 : y + 380, x : x + 520] = raw
            sheet[y + 40 : y + 380, x + 520 : x + 1040] = overlay
            cv2.putText(
                sheet,
                f"k={item['k']} {item['group']} delta={item['delta']:.1f} first={item['first']:.1f}px",
                (x + 8, y + 27),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (255, 255, 255),
                1,
            )
        cv2.imwrite(str(out / f"paths-{offset // 10 + 1}.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 90])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recording", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[2]
    crops = np.load(root / "lab/minimap/data/crops.npy", mmap_mode="r")
    candidates = []
    eligible = 0
    for k, crop in enumerate(crops):
        reading = read(crop)
        if not clean(reading):
            continue
        eligible += 1
        if reading.path:
            candidates.append(
                dict(
                    k=k,
                    path=reading.path,
                    first=math.hypot(*reading.path[0]),
                    delta=difference(angle(reading.path[0]), reading.bearing),
                )
            )
    rng = random.Random(8)
    selected = [dict(item, group="random") for item in rng.sample(candidates, 30)]
    used = {item["k"] for item in selected}
    corners = [item for item in candidates if item["delta"] > 25 and item["k"] not in used]
    selected.extend(dict(item, group="corner") for item in rng.sample(corners, 30))
    sheets(crops, selected, args.out)
    summary = dict(
        clean_route_crops=eligible,
        with_path=len(candidates),
        first_within_16=sum(item["first"] <= 16 for item in candidates),
        selection=selected,
        selection_seed=8,
    )
    if args.recording:
        pipeline = Pipeline(driver=Driver(DriveConfig(command_delay=0.14)))
        frames = json_lines(args.recording / "frames.jsonl")
        capture = cv2.VideoCapture(str(args.recording / "video.mp4"))
        rows, short_jitter, bearing_jitter = [], [], []
        previous = None
        try:
            for index, frame in enumerate(frames):
                ok, bgr = capture.read()
                if not ok or frame["i"] != index:
                    raise ValueError(f"Missing or misaligned frame {index}")
                reading, moving, command = pipeline.step(hud_crop(bgr), frame["t"], feedback=False)
                rows.append(
                    dict(
                        time=frame["t"],
                        t=frame["t"] - frames[0]["t"],
                        reading=asdict(reading),
                        moving=moving,
                        command=asdict(command),
                    )
                )
                if (
                    previous
                    and clean(reading)
                    and clean(previous)
                    and reading.path
                    and previous.path
                    and reading.route == previous.route
                ):
                    short_jitter.append(difference(angle(reading.path[0]), angle(previous.path[0])))
                    bearing_jitter.append(difference(reading.bearing, previous.bearing))
                previous = reading
        finally:
            capture.release()
        summary["consecutive_jitter"] = dict(
            pairs=len(short_jitter),
            short_median=float(np.median(short_jitter)),
            short_p90=float(np.percentile(short_jitter, 90)),
            bearing_median=float(np.median(bearing_jitter)),
            bearing_p90=float(np.percentile(bearing_jitter, 90)),
        )
        summary["direction"] = diagnostics(rows, json_lines(args.recording / "pad.jsonl"))
    (args.out / "picture-check.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "selection"}, indent=2))


if __name__ == "__main__":
    main()
