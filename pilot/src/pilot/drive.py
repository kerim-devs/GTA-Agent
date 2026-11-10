"""Follows the GPS route by car from minimap readings. Placeholder until task P3 lands."""

from __future__ import annotations

from .contract import Command, Reading


class Driver:
    """Turns minimap readings into controller states. Keeps its state between calls."""

    def step(self, reading: Reading, t: float, moving: bool | None = None) -> Command:
        """`t` is the time of the frame in seconds on a monotonic clock. `moving` says whether the map
        moved over the last 0.2 s (None = unknown). Never raises, never returns a value out of range."""
        raise NotImplementedError
