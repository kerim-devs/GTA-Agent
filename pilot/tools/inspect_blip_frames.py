"""Render source scenes for independent map-mode checks on label candidates."""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    output = root / "lab/blips"
    parser = argparse.ArgumentParser()
    parser.add_argument("--group", choices=("flat", "vehicle"), default="vehicle")
    group = parser.parse_args().group
    meta = json.loads((root / "lab/minimap/data/meta.json").read_text())
    labels = json.loads((output / f"{group}-labels.json").read_text())
    caps, indices = {}, {}
    tiles = []
    for label in labels:
        info = meta[label["id"]]
        rec = info["rec"]
        if rec not in caps:
            path = Path("/Users/kerim/Documents/ChatGPT/gta/recordings") / rec
            caps[rec] = cv2.VideoCapture(str(path / "video.mp4"))
            indices[rec] = list(map(json.loads, (path / "frames.jsonl").read_text().splitlines()))
        cap = caps[rec]
        frame_index = min(indices[rec], key=lambda f: abs(f["t"] - info["t"]))["i"]
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = cap.read()
        if not ok:
            raise RuntimeError(f"Failed frame {info}")
        tile = np.zeros((390, 640, 3), np.uint8)
        tile[:360] = cv2.resize(frame, (640, 360))
        cv2.putText(tile, str(label["id"]), (10, 383), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        tiles.append(tile)
    for cap in caps.values():
        cap.release()
    for i in range(0, len(tiles), 4):
        cv2.imwrite(str(output / f"{group}-scenes-{i // 4}.jpg"), np.concatenate(tiles[i : i + 4], axis=0))


if __name__ == "__main__":
    main()
