"""Estimate map displacement over a 0.2s crop pair; unknown is not stationary."""

from __future__ import annotations

from math import isfinite

import cv2
import numpy as np

from .minimap import _bars, _blocks

# Accepted real driving pairs exceed 2.53px; standing/stuck pairs stay below
# 0.24px. This threshold leaves room for compression jitter and slow movement.
MOVING_PX = 1.0

# Inset the measured map rectangle to exclude borders and HUD bars.
_X0, _X1, _Y0, _Y1 = 39, 209, 32, 138
_Y, _X = np.mgrid[_Y0:_Y1, _X0:_X1]
_BASE = np.full((_Y1 - _Y0, _X1 - _X0), 255, np.uint8)
# Fixed player arrow and upper compass area cannot provide map displacement.
_BASE[(_X - 123) ** 2 + (_Y - 117) ** 2 < 20**2] = 0
_BASE[(_X - 125) ** 2 + (_Y - 39) ** 2 < 14**2] = 0


def map_motion(prev: np.ndarray, cur: np.ndarray) -> float | None:
    """How far the map content moved between two HUD crops, in crop pixels. None when it cannot be told:
    no minimap in one of the crops, a damaged picture, too little structure. Pure, never raises."""
    try:
        for crop in (prev, cur):
            if not isinstance(crop, np.ndarray) or crop.shape != (170, 260, 3):
                return None
            if crop.dtype != np.uint8:
                return None
            # Cheap HUD checks avoid running the complete reader twice. Refuse
            # codec damage even if enough optical-flow tracks would survive it.
            if _bars(crop) < 2 or _blocks(crop)[0] >= 2:
                return None
        return _displacement(prev, cur)
    except Exception:  # Degenerate image data must not escape to the driver.
        return None


def _displacement(prev: np.ndarray, cur: np.ndarray) -> float | None:
    # Build optical-flow pyramids only for the map, avoiding work on the world.
    a = cv2.cvtColor(prev[_Y0:_Y1, _X0:_X1], cv2.COLOR_RGB2GRAY)
    b = cv2.cvtColor(cur[_Y0:_Y1, _X0:_X1], cv2.COLOR_RGB2GRAY)
    ah = cv2.cvtColor(prev[_Y0:_Y1, _X0:_X1], cv2.COLOR_RGB2HSV)
    bh = cv2.cvtColor(cur[_Y0:_Y1, _X0:_X1], cv2.COLOR_RGB2HSV)
    mask = _BASE.copy()
    # Bright saturated route/blip colours are excluded in both frames; retain
    # neutral or dark roads, including roads under moderate colour tint.
    quiet = ((ah[:, :, 1] < 85) | (ah[:, :, 2] < 150)) & ((bh[:, :, 1] < 85) | (bh[:, :, 2] < 150))
    mask[~quiet] = 0
    # 48 separated corners and a 15px, three-level search fit the measured
    # displacement range within the 2ms budget on the supplied recordings.
    points = cv2.goodFeaturesToTrack(
        a, maxCorners=48, qualityLevel=0.015, minDistance=5, mask=mask, blockSize=5
    )
    if points is None:
        return None
    forward, status, error = cv2.calcOpticalFlowPyrLK(a, b, points, None, winSize=(15, 15), maxLevel=2)
    if forward is None or status is None or error is None:
        return None
    back, back_status, _ = cv2.calcOpticalFlowPyrLK(b, a, forward, None, winSize=(15, 15), maxLevel=2)
    if back is None or back_status is None:
        return None
    # Photometric error <15 and round-trip error <0.8px reject failed matches.
    valid = (status.ravel() > 0) & (back_status.ravel() > 0) & (error.ravel() < 15)
    valid &= np.linalg.norm(points - back, axis=2).ravel() < 0.8
    flow = (forward - points).reshape(-1, 2)[valid]
    if len(flow) < 8 or not np.isfinite(flow).all():
        return None
    # Eight tracks give minimum support; q60 tolerates some remaining fixed
    # icons without letting a few moving world features dominate the estimate.
    return float(np.quantile(np.linalg.norm(flow, axis=1), 0.60))


def map_speed(displacement: float | None, elapsed: float) -> float | None:
    """Convert a measured crop displacement to pixels/second; unknown stays unknown."""
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in (displacement, elapsed)):
        return None
    try:
        if not isfinite(displacement) or not isfinite(elapsed) or displacement < 0 or elapsed <= 0:
            return None
        result = displacement / elapsed
        return result if isfinite(result) else None
    except (OverflowError, ValueError):
        return None
