"""Compose the exact recorded crops and annotate only the old reader's detections."""

import math
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot/src"))
from p50_replay import baseline
from pilot.foot import find_road
from pilot.minimap import _tilt_score

OUT = ROOT / "lab/foot/p50"


def sheet(paths, destination, captions=None):
    width, height = 520, 375
    result = np.full((height * ((len(paths) + 2) // 3), width * 3, 3), 245, np.uint8)
    old = baseline("minimap")
    for index, path in enumerate(paths):
        rgb = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
        road = find_road(rgb) if destination == "roads.png" else None
        tilt = _tilt_score(rgb)
        if road is not None:
            point = (
                round(123 + math.sin(math.radians(road.bearing)) * road.distance),
                round(117 - math.cos(math.radians(road.bearing)) * road.distance),
            )
            cv2.circle(rgb, point, 6, (240, 40, 40), 1)
        if destination == "blips.png":
            for b in old.read(rgb).blips:
                color = (240, 40, 40) if b.color == "red" else (240, 170, 0)
                cv2.circle(rgb, (round(123 + b.x), round(117 - b.y)), 9, color, 1)
        image = cv2.resize(rgb, (520, 340), interpolation=cv2.INTER_NEAREST)
        x, y = (index % 3) * width, (index // 3) * height
        result[y + 35 : y + 375, x : x + 520] = image
        label = (captions or {}).get(path.name, path.stem)
        cv2.putText(
            result,
            label,
            (x + 8, y + 15),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (20, 20, 20),
            1,
        )
        if destination == "roads.png":
            road = find_road(cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB))
            cv2.putText(
                result,
                f"Road: {road is not None}; tilt score: {tilt:.2f}",
                (x + 8, y + 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (20, 20, 20),
                1,
            )
    cv2.imwrite(str(OUT / destination), cv2.cvtColor(result, cv2.COLOR_RGB2BGR))


def main():
    paths = sorted(OUT.glob("*-blip-*.png"))
    sheet(paths, "blips.png")
    roadpaths = [
        OUT / "20261112-100318-6-map.png",
        OUT / "20261112-100318-7-map.png",
        OUT / "20261112-100713-112-map.png",
    ]
    if all(p.exists() for p in roadpaths):
        sheet(roadpaths, "roads.png")
    result = np.full((420, 640, 3), 245, np.uint8)
    for index, name in enumerate(["hill-a", "hill-b", "hospital", "pier"]):
        x, y = (index % 2) * 320, (index // 2) * 210
        result[y + 25 : y + 205, x : x + 320] = cv2.imread(str(OUT / (name + "-a.png")))
        cv2.putText(
            result,
            name,
            (x + 8, y + 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (20, 20, 20),
            1,
        )
    cv2.imwrite(str(OUT / "motion.png"), result)


if __name__ == "__main__":
    main()
