"""Print the compact anchors used in hud.py from the original recording."""

import argparse
import base64
import zlib
from pathlib import Path

import cv2
import numpy as np

# name, decoded ordinal, (left, top, right, bottom), channel, stride
ANCHORS = [
    ("FAILED", 826, (304, 300, 976, 364), "red", 4),
    ("PASSED", 7317, (448, 124, 832, 196), "yellow", 4),
    ("PAUSE", 8216, (208, 80, 386, 108), "gray", 2),
    ("WHEEL", 343, (626, 444, 660, 476), "gray", 1),
    ("PHONE", 3436, (1092, 432, 1140, 446), "gray", 1),
    ("MAP", 8280, (604, 662, 644, 682), "gray", 1),
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path, help="20261110-093238 directory")
    args = parser.parse_args()
    cap = cv2.VideoCapture(str(args.recording / "video.mp4"))
    for name, index, (x0, y0, x1, y1), kind, step in ANCHORS:
        cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, bgr = cap.read()
        if not ok:
            raise RuntimeError(f"Cannot decode frame {index}")
        pixels = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)[y0:y1, x0:x1]
        if kind == "gray":
            anchor = cv2.cvtColor(pixels, cv2.COLOR_RGB2GRAY)[::step, ::step]
        else:
            r, g, b = pixels.astype(np.int16).transpose(2, 0, 1)
            if kind == "red":
                mask = (r - np.maximum(g, b) > 45) & (r > 100)
            else:
                mask = (np.minimum(r, g) - b > 60) & (g > 120) & (r > 120)
            anchor = mask.astype(np.uint8)[::step, ::step] * 255
        encoded = base64.b85encode(zlib.compress(anchor.tobytes(), 9)).decode()
        print(f"{name} = _template({anchor.shape},")
        for start in range(0, len(encoded), 90):
            print(f'    b"{encoded[start : start + 90]}"')
        print(")\n")
    cap.release()


if __name__ == "__main__":
    main()
