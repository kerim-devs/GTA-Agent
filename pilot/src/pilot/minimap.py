"""Reads the minimap from the HUD crop. Placeholder until task P2 lands."""

from __future__ import annotations

import numpy as np

from .contract import Reading


def read(crop: np.ndarray) -> Reading:
    """Pure (no state between calls), never raises on any 170x260x3 uint8 input, under 3 ms on average."""
    raise NotImplementedError
