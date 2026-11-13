"""Read the recorded cyan personal-car glyph, never infer ownership from colour.

This narrow reader covers Michael's upright front-car symbol in the 13 November
recordings. Other colours, bikes and damaged symbols are not validated. The
arrow neighbourhood and uncertain shape matches abstain.
The output identifies a map glyph; it does not identify a world-view car or
prove that entering a nearby vehicle will enter the marked one.
"""

from dataclasses import dataclass

import cv2
import numpy as np

from .contract import ARROW_XY


@dataclass(frozen=True)
class VehicleMarker:
    x: float  # HUD pixels relative to the player arrow, right positive.
    y: float  # HUD pixels relative to the player arrow, up positive.
    clipped: bool  # On the radar rim: direction only, distance is not meaningful.
    confidence: float  # Shape correlation, not a calibrated probability.


# Cyan silhouette from 20261113-201617/head-0002.jpg, HUD x203:221, y51:65.
# The dark windscreen above the coloured bonnet is checked separately. Padding
# penalises letters, destination discs and long health/armour bars of this hue.
_SHAPE = np.array(
    [
        [int(c) for c in line]
        for line in (
            "000000000000000000",
            "000000000000000000",
            "000000000000000000",
            "000000000000000000",
            "000000000000000000",
            "000100000000010000",
            "000011111111110000",
            "000011111111111000",
            "000011111111111000",
            "000011111111110000",
            "000010000000100000",
            "000000000000000000",
            "000000000000000000",
            "000000000000000000",
        )
    ],
    dtype=np.uint8,
)
_MIN_SCORE = 0.76


def find_own_vehicle(crop) -> VehicleMarker | None:
    """Find one unambiguous car glyph in a 260x170 RGB uint8 HUD crop.

    A rim marker is returned with ``clipped=True`` even if its pixels are fully
    visible: the game clamps its position. Multiple separated matches abstain.
    No output means unrecognised, not that the personal vehicle is absent.
    """
    if not isinstance(crop, np.ndarray) or crop.shape != (170, 260, 3) or crop.dtype != np.uint8:
        return None
    hue, saturation, value = cv2.split(cv2.cvtColor(crop, cv2.COLOR_RGB2HSV))
    cyan = ((hue >= 85) & (hue <= 112) & (saturation >= 65) & (value >= 85)).astype(np.uint8)
    scores = cv2.matchTemplate(cyan[18:153, 24:226], _SHAPE, cv2.TM_CCOEFF_NORMED)
    candidates = []
    # Suppress all translations of one glyph, but retain separated competing
    # symbols. A bright roof or overlap with the player arrow is never accepted.
    while True:
        _, score, _, (px, py) = cv2.minMaxLoc(scores)
        if score < _MIN_SCORE:
            break
        scores[max(0, py - 7) : py + 8, max(0, px - 9) : px + 10] = -1
        left, top = px + 24, py + 18
        cx, cy = left + 8.5, top + 6.5
        if (cx - ARROW_XY[0]) ** 2 + (cy - ARROW_XY[1]) ** 2 <= 15**2:
            continue
        if np.mean(value[top + 2 : top + 5, left + 5 : left + 13] < 100) < 0.9:
            continue
        candidates.append(
            VehicleMarker(
                cx - ARROW_XY[0],
                ARROW_XY[1] - cy,
                cx <= 38 or cx >= 209 or cy <= 33 or cy >= 139,
                round(float(score), 3),
            )
        )
    return candidates[0] if len(candidates) == 1 else None
