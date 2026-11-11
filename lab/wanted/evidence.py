"""Render temporal context and every labelled error without assigning labels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from prepare import OUT, ROOT, clock


def sheets(cells: list[np.ndarray], prefix: str, per_page: int = 24) -> None:
    for old in (OUT / "contact-sheets").glob(f"{prefix}-*.jpg"):
        old.unlink()
    for page, start in enumerate(range(0, len(cells), per_page)):
        part = cells[start : start + per_page]
        part += [np.zeros_like(cells[0])] * ((-len(part)) % 4)
        sheet = np.vstack([np.hstack(part[k : k + 4]) for k in range(0, len(part), 4)])
        cv2.imwrite(str(OUT / "contact-sheets" / f"{prefix}-{page:02d}.jpg"), sheet)


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
    times = clock(sources["wifi"])
    cap = cv2.VideoCapture(str(sources["wifi"] / "video.mp4"))
    for prefix, targets in (
        ("blue-576", np.linspace(574, 578, 25)),
        ("blue-624", np.linspace(622, 626, 25)),
        ("death", np.linspace(626, 644, 49)),
    ):
        cells = []
        for target in targets:
            i = int(np.abs(times - target).argmin())
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError(f"Cannot decode wifi:{i}")
            cell = np.zeros((230, 384, 3), np.uint8)
            cell[14:] = cv2.resize(frame, (384, 216))
            if prefix.startswith("blue"):
                cell[25:121, 15:321] = cv2.resize(
                    frame[30:62, 1118:1220], (306, 96), interpolation=cv2.INTER_NEAREST
                )
            cv2.putText(
                cell,
                f"wifi-{i:05d} {times[i]:.3f}s",
                (5, 12),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (255, 255, 255),
                1,
            )
            cells.append(cell)
        sheets(cells, prefix)
    cap.release()
    evaluation_path = OUT / "evaluation.json"
    if not evaluation_path.exists():
        return
    evaluation = json.loads(evaluation_path.read_text())
    cells = []
    for source, directory in sources.items():
        cap = cv2.VideoCapture(str(directory / "video.mp4"))
        for row in evaluation["errors"]:
            if row["source"] != source:
                continue
            cap.set(cv2.CAP_PROP_POS_FRAMES, row["i"])
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError(f"Cannot decode {row['id']}")
            cell = np.zeros((230, 384, 3), np.uint8)
            cell[14:] = cv2.resize(frame, (384, 216))
            title = f"{row['id']} wanted {row['wanted']} read {row['actual_wanted']}"
            cv2.putText(
                cell, title, (4, 12), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1
            )
            cells.append(cell)
        cap.release()
    sheets(cells, "errors")


if __name__ == "__main__":
    main()
