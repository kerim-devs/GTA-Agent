"""Create contact sheets from decoded frame ordinals, never controller events."""

from pathlib import Path
import argparse
import cv2
import numpy as np

SOURCES = {
    "tour": "screen-tour/20261111-070239",
    "calibration2": "calibrate/20261111-065642",
    "pilot1": "pilot/20261110-230229",
    "pilot2": "pilot/20261110-231512",
    "kerim": "kerim/20261111-065022",
    "camera": "camera-probe/20261111-065904",
    "calibration1": "calibrate/20261111-063233",
}
ROOT = Path(__file__).resolve().parent


def contact(source, indices, root=Path.home() / "recordings", name=None):
    cap = cv2.VideoCapture(str(root / SOURCES[source] / "video.mp4"))
    out = ROOT / "review"
    out.mkdir(exist_ok=True)
    indices = list(indices)
    for start in range(0, len(indices), 25):
        batch = indices[start : start + 25]
        sheet = np.zeros((((len(batch) + 4) // 5) * 200, 5 * 320, 3), np.uint8)
        for j, i in enumerate(batch):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ok, frame = cap.read()
            if not ok:
                raise ValueError((source, i))
            tile = cv2.resize(frame, (320, 180))
            y, x = (j // 5) * 200, (j % 5) * 320
            sheet[y : y + 180, x : x + 320] = tile
            cv2.putText(
                sheet,
                f"{source}:{i}",
                (x + 5, y + 195),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (255, 255, 255),
                1,
            )
        cv2.imwrite(str(out / f"{name or source}-{start // 25}.jpg"), sheet)
    cap.release()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("source", choices=SOURCES)
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--stop", type=int, required=True)
    p.add_argument("--step", type=int, default=60)
    p.add_argument("--name")
    a = p.parse_args()
    contact(a.source, range(a.start, a.stop, a.step), name=a.name)
