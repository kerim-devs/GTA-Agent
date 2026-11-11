"""Rebuild contact sheets from the manually labelled, frame-id-pinned sample."""
import argparse
import json
from pathlib import Path
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "pilot/src"))
from pilot.replay import hud_crop


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recording", type=Path, default=Path("/Users/kerim/recordings/pilot/20261111-130955"))
    args = parser.parse_args()
    here = Path(__file__).parent
    labels = json.loads((here / "frames.json").read_text())
    cap = cv2.VideoCapture(str(args.recording / "video.mp4"))
    for page in range((len(labels) + 24) // 25):
        sample = labels[page * 25:(page + 1) * 25]
        sheet = np.full((((len(sample) + 4) // 5) * 285, 5 * 390, 3), 30, np.uint8)
        for j, row in enumerate(sample):
            cap.set(cv2.CAP_PROP_POS_FRAMES, row["i"])
            ok, bgr = cap.read()
            if not ok:
                raise RuntimeError(f'Missing sample frame {row["frame_id"]}')
            crop = cv2.cvtColor(hud_crop(bgr), cv2.COLOR_RGB2BGR)
            x, y = j % 5 * 390, j // 5 * 285
            sheet[y + 30:y + 285, x:x + 390] = cv2.resize(crop, (390, 255), interpolation=cv2.INTER_NEAREST)
            label = "damaged" if row["corrupt"] else "clean"
            cv2.putText(sheet, f'{row["sample_t"]}s / {row["frame_id"]} / {label}', (x + 5, y + 20), cv2.FONT_HERSHEY_SIMPLEX, .5, (255, 255, 255), 1)
        cv2.imwrite(str(here / f"contact-{page + 1}.png"), sheet)
    cap.release()


if __name__ == "__main__":
    main()
