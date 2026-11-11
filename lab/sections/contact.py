"""Make independent, one-second contact sheets before running the section reader."""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("recordings", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    for recording in args.recordings:
        meta = json.loads((recording / "meta.json").read_text())
        if "seconds" not in meta:
            continue
        rows = [json.loads(line) for line in (recording / "frames.jsonl").read_text().splitlines()]
        targets = {}
        cursor = 0
        for second in range(int(meta["seconds"])):
            while cursor + 1 < len(rows) and abs(rows[cursor + 1]["t"] - second) < abs(
                rows[cursor]["t"] - second
            ):
                cursor += 1
            targets[rows[cursor]["i"]] = second
        output = args.out / recording.name
        output.mkdir(parents=True, exist_ok=True)
        cap = cv2.VideoCapture(str(recording / "video.mp4"))
        canvas = np.zeros((6 * 164, 5 * 256, 3), dtype=np.uint8)
        page = 0
        count = 0
        for row in rows:
            if not cap.grab():
                raise ValueError(f"Video ends at frame {row['i']}")
            if row["i"] not in targets:
                continue
            ok, frame = cap.retrieve()
            if not ok:
                raise ValueError(f"Cannot decode frame {row['i']}")
            second = targets[row["i"]]
            cell = count % 30
            x, y = (cell % 5) * 256, (cell // 5) * 164
            canvas[y : y + 144, x : x + 256] = cv2.resize(frame, (256, 144))
            cv2.putText(
                canvas,
                f"{second}s  frame {row['i']}",
                (x + 4, y + 159),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (255, 255, 255),
                1,
            )
            count += 1
            if count % 30 == 0:
                cv2.imwrite(str(output / f"{page:03d}.jpg"), canvas)
                canvas[:] = 0
                page += 1
        if count % 30:
            cv2.imwrite(str(output / f"{page:03d}.jpg"), canvas)
        cap.release()
        print(f"{recording.name}: {count} one-second frames, {page + bool(count % 30)} sheets", flush=True)


if __name__ == "__main__":
    main()
