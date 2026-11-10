"""Tells from two HUD crops whether the map moved. Placeholder until task P2 lands."""

from __future__ import annotations

import numpy as np

MOVING_PX = 1.0  # motion between two crops 0.2 s apart above which the player counts as moving; set in P2


def map_motion(prev: np.ndarray, cur: np.ndarray) -> float | None:
    """How far the map content moved between two HUD crops, in crop pixels. None when it cannot be told:
    no minimap in one of the crops, a damaged picture, too little structure. Pure, never raises."""
    raise NotImplementedError
