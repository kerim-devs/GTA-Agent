"""Recreate the seed-15 sample and visual contact sheets; never infer labels."""

import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
SOURCES = {
    "wifi": {"root": "wifi", "recording": "20261110-093238"},
    "clean1": {"root": "clean", "recording": "20261110-230229"},
    "clean2": {"root": "clean", "recording": "20261110-231512"},
}
RARE_TIMES = (
    list(np.linspace(14.75, 15.45, 8))
    + list(np.linspace(537.8, 539.2, 8))
    + list(np.linspace(153.8, 159, 12))
    + list(np.linspace(34, 40.8, 12))
    + list(np.linspace(338.5, 342, 12))
    + list(np.linspace(385.2, 387.5, 10))
    + list(np.linspace(388.2, 393, 12))
    + list(np.linspace(41.6, 42.9, 6))
    + list(np.linspace(14.8, 15.3, 5))
    + list(np.linspace(154, 156, 5))
    + list(np.linspace(35.2, 38.2, 5))
    + list(np.linspace(389, 391, 5))
)


def prepare(roots, destination):
    destination.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(15)
    labels = {"seed": 15, "sources": SOURCES, "frames": []}
    thumbs = []
    bars = []
    for name, source in SOURCES.items():
        directory = roots[source["root"]] / source["recording"]
        metadata = [
            json.loads(line)
            for line in (directory / "frames.jsonl").read_text().splitlines()
        ]
        times = np.array([row["t"] for row in metadata])
        times -= times[0]
        selected = [
            (int(i), "random")
            for i in sorted(
                rng.choice(len(metadata), 60 if name == "wifi" else 20, replace=False)
            )
        ]
        if name == "wifi":
            used = {i for i, _ in selected}
            for t in RARE_TIMES:
                index = next(
                    int(i) for i in np.argsort(np.abs(times - t)) if int(i) not in used
                )
                used.add(index)
                selected.append((index, "rare"))
        cap = cv2.VideoCapture(str(directory / "video.mp4"))
        for index, selection in selected:
            cap.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, bgr = cap.read()
            if not ok:
                raise RuntimeError((name, index))
            number = len(labels["frames"])
            identity = f"{name}-{index:05d}"
            row = {
                "id": identity,
                "source": name,
                "i": index,
                "capture_s": round(float(times[index]), 4),
                "selection": selection,
                "rgb_sha256": hashlib.sha256(
                    cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).tobytes()
                ).hexdigest(),
                "screen": None,
            }
            labels["frames"].append(row)
            thumb = cv2.resize(bgr, (400, 225))
            cv2.rectangle(thumb, (0, 0), (399, 22), (0, 0, 0), -1)
            cv2.putText(
                thumb,
                f"{number} {identity} {times[index]:.2f}s",
                (5, 16),
                0,
                0.45,
                (0, 200, 255),
                1,
            )
            thumbs.append(thumb)
            strip = cv2.resize(
                bgr[670:685, 60:250], (760, 60), interpolation=cv2.INTER_NEAREST
            )
            strip = cv2.copyMakeBorder(strip, 22, 0, 0, 0, cv2.BORDER_CONSTANT)
            cv2.putText(
                strip,
                f"{number} {identity} {times[index]:.2f}s",
                (5, 16),
                0,
                0.45,
                (0, 200, 255),
                1,
            )
            bars.append(strip)
        cap.release()
    assert len(labels["frames"]) == 200
    assert len({r["id"] for r in labels["frames"]}) == 200
    (destination / "unlabelled.json").write_text(json.dumps(labels, indent=2) + "\n")
    for start in range(0, len(thumbs), 20):
        chunk = thumbs[start : start + 20]
        cv2.imwrite(
            str(destination / f"screens-{start:03d}.jpg"),
            np.vstack([np.hstack(chunk[i : i + 4]) for i in range(0, 20, 4)]),
        )
        cv2.imwrite(
            str(destination / f"bars-{start:03d}.png"),
            np.vstack(bars[start : start + 20]),
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recordings", type=Path, required=True)
    parser.add_argument(
        "--clean-recordings", type=Path, default=Path.home() / "recordings/pilot"
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New directory, separate from reviewed labels",
    )
    args = parser.parse_args()
    prepare({"wifi": args.recordings, "clean": args.clean_recordings}, args.output)
