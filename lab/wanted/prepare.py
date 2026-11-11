"""Extract capture-clock samples and contact sheets using OpenCV only."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent


def clock(root: Path) -> np.ndarray:
    rows = [
        json.loads(line) for line in (root / "frames.jsonl").read_text().splitlines()
    ]
    times = np.array([row["t"] for row in rows])
    return times - times[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recordings", type=Path, default=ROOT / "recordings")
    parser.add_argument(
        "--clean-recordings", type=Path, default=Path.home() / "recordings/pilot"
    )
    args = parser.parse_args()
    sources = {
        "wifi": args.recordings / "20261110-093238",
        "clean1": args.clean_recordings / "20261110-230229",
        "clean2": args.clean_recordings / "20261110-231512",
    }
    (OUT / "scratch" / "crops").mkdir(parents=True, exist_ok=True)
    (OUT / "contact-sheets").mkdir(exist_ok=True)
    rows = []
    for source, root in sources.items():
        times = clock(root)
        targets = (
            np.concatenate((np.linspace(500, 650, 361), np.linspace(5, 490, 240)))
            if source == "wifi"
            else np.linspace(1, 237, 240)
        )
        indices = sorted({int(np.abs(times - t).argmin()) for t in targets})
        cap = cv2.VideoCapture(str(root / "video.mp4"))
        cells = []
        for i in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ok, bgr = cap.read()
            if not ok:
                raise RuntimeError(f"Cannot decode {source}:{i}")
            key = f"{source}-{i:05d}"
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            rows.append(
                {
                    "id": key,
                    "source": source,
                    "i": i,
                    "capture_s": round(float(times[i]), 4),
                    "rgb_sha256": hashlib.sha256(rgb.tobytes()).hexdigest(),
                }
            )
            # Keep native star pixels plus a small scene context for manual labels.
            crop = bgr[20:130, 1000:1250]
            cv2.imwrite(str(OUT / "scratch" / "crops" / f"{key}.png"), crop)
            cell = np.full((174, 320, 3), 28, np.uint8)
            cell[22:132, 35:285] = crop
            cell[134:174, :72] = cv2.resize(bgr, (72, 40))
            cv2.putText(
                cell,
                f"{key} {times[i]:.2f}s",
                (5, 16),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                (240, 240, 240),
                1,
            )
            cells.append(cell)
        cap.release()
        for page, start in enumerate(range(0, len(cells), 60)):
            part = cells[start : start + 60]
            part += [np.zeros_like(cells[0])] * ((-len(part)) % 5)
            sheet = np.vstack(
                [np.hstack(part[k : k + 5]) for k in range(0, len(part), 5)]
            )
            cv2.imwrite(str(OUT / "contact-sheets" / f"{source}-{page:02d}.jpg"), sheet)
        print(source, len(indices), flush=True)
    (OUT / "scratch" / "samples.json").write_text(
        json.dumps(
            {"sources": {k: str(v) for k, v in sources.items()}, "frames": rows},
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
