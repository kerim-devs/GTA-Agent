"""Make recorded full-frame and minimap sheets for offline visual review."""

import json
from pathlib import Path

import cv2
import numpy as np


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    output = root / "lab/blips"
    metadata = [
        json.loads(s)
        for s in Path("/Users/kerim/Documents/ChatGPT/gta/recordings/20261110-093238/frames.jsonl")
        .read_text()
        .splitlines()
    ]
    times = np.array([f["t"] for f in metadata])
    cap = cv2.VideoCapture("/Users/kerim/Documents/ChatGPT/gta/recordings/20261110-093238/video.mp4")
    rows = []
    for t in (76, 122, 624, 625, 646, 649, 656, 680):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(np.argmin(abs(times - t))))
        ok, frame = cap.read()
        if not ok:
            raise RuntimeError(f"No frame at {t}")
        small = cv2.resize(frame, (640, 360))
        crop = cv2.resize(frame[530:700, 30:290], (520, 340), interpolation=cv2.INTER_NEAREST)
        row = np.zeros((380, 1160, 3), np.uint8)
        row[:360, :640] = small
        row[:340, 640:] = crop
        cv2.putText(row, f"t={t}s", (645, 370), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        rows.append(row)
    cap.release()
    for i in range(2):
        cv2.imwrite(str(output / f"camera-review-{i}.jpg"), np.concatenate(rows[i * 4 : (i + 1) * 4]))
    crops = np.load(root / "lab/minimap/data/crops.npy", mmap_mode="r")
    rng = np.random.default_rng(12026)
    ids = rng.choice(len(crops), 120, replace=False)
    np.save(output / "candidate-ids.npy", ids)
    for sheet in range(6):
        tiles = []
        for idx in ids[sheet * 20 : (sheet + 1) * 20]:
            tile = np.zeros((370, 520, 3), np.uint8)
            tile[:340] = cv2.resize(
                cv2.cvtColor(crops[idx], cv2.COLOR_RGB2BGR), (520, 340), interpolation=cv2.INTER_NEAREST
            )
            cv2.putText(tile, str(idx), (5, 365), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            tiles.append(tile)
        rows = [np.concatenate(tiles[i : i + 4], axis=1) for i in range(0, 20, 4)]
        cv2.imwrite(str(output / f"candidates-{sheet}.jpg"), np.concatenate(rows))
    print("Saved camera review and 120 fixed-seed random candidate crops.")


if __name__ == "__main__":
    main()
