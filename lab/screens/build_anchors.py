"""Reproduce embedded UI-only anchors from the cable tour (RGB, 1280x720)."""

import base64
import zlib
from pathlib import Path
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
# The footer controls are fixed UI; the wheel support is its opaque fist only.
ANCHORS = {
    "PAUSE_UI": (120, (862, 665, 908, 679)),
    "PAUSE_TITLE_UI": (120, (207, 80, 385, 108)),
    "MAP_UI": (360, (1129, 665, 1187, 680)),
    "WHEEL_UI": (780, (625, 443, 660, 476)),
    "PHONE_UI": (1080, (1093, 423, 1142, 445)),
    "INTERACTION_UI": (1380, (68, 111, 211, 128)),
}


def build():
    cap = cv2.VideoCapture(
        str(Path.home() / "recordings/screen-tour/20261111-070239/video.mp4")
    )
    (ROOT / "lab/screens/review").mkdir(exist_ok=True)
    blocks = []
    for name, (i, rect) in ANCHORS.items():
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, bgr = cap.read()
        assert ok
        x0, y0, x1, y1 = rect
        gray = cv2.cvtColor(bgr[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
        if name == "PAUSE_TITLE_UI":
            other = cv2.imread(str(ROOT / "lab/hud/fixtures/wifi-08196.png"))
            other = cv2.cvtColor(other[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
            second = cv2.VideoCapture(
                str(Path.home() / "recordings/calibrate/20261111-065642/video.mp4")
            )
            second.set(cv2.CAP_PROP_POS_FRAMES, 1920)
            ok, f = second.read()
            assert ok
            second.release()
            third = cv2.cvtColor(f[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
            white = (np.minimum(np.minimum(gray, other), third) > 170).astype(np.uint8)
            black = np.maximum(np.maximum(gray, other), third) < 100
            mask = (
                white.astype(bool)
                | (black & cv2.dilate(white, np.ones((3, 3), np.uint8)).astype(bool))
            ).astype(np.uint8)
        elif name == "WHEEL_UI":
            dark = (gray < 75).astype(np.uint8)
            contours, _ = cv2.findContours(
                dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            mask = np.zeros_like(gray)
            cv2.drawContours(mask, [max(contours, key=cv2.contourArea)], -1, 1, -1)
            mask = cv2.erode(mask, np.ones((3, 3), np.uint8))
        elif name == "PAUSE_UI":
            mask = np.zeros_like(gray)
            mask[1:13, 1:19] = 1
            mask[1:13, 27:45] = 1
        else:
            # Glyph core and the immediately adjacent printed shadow/panel.
            white = (gray > 155).astype(np.uint8)
            mask = cv2.dilate(white, np.ones((3, 3), np.uint8))
        gray = gray * mask
        for suffix, data in [("", gray), ("_MASK", mask)]:
            encoded = base64.b85encode(zlib.compress(data.tobytes(), 9))
            chunks = [repr(encoded[j : j + 100]) for j in range(0, len(encoded), 100)]
            blocks.append(
                f"{name}{suffix} = _template({data.shape!r},\n    "
                + "\n    ".join(chunks)
                + "\n)"
                + (".astype(bool)" if suffix else "")
            )
        cv2.imwrite(
            str(ROOT / "lab/screens/review" / f"{name}.png"),
            cv2.resize(gray, None, fx=6, fy=6, interpolation=cv2.INTER_NEAREST),
        )
    cap.release()
    return "\n\n".join(blocks)


if __name__ == "__main__":
    print(build())
