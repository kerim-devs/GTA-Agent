"""Smallest valid reader: sees nothing. Shows the shape of an implementation."""
import numpy as np

from contract import Reading


def read(crop: np.ndarray) -> Reading:
    return Reading(minimap="none", route="none", bearing=None, far_bearing=None, arrow=None, corrupt=False, confidence=0.0)
