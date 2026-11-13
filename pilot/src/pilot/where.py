"""A nonblocking, short-lived sense of the player's surroundings."""

from __future__ import annotations

import math

import numpy as np

from .ahead import PLACES
from .contract import Observation, player_mode


class Sense:
    def __init__(self, asker):
        self.asker = asker
        self.verdict: str | None = None
        self.confirmed_at: float | None = None
        self._asked: float | None = None
        self._last_ask = -math.inf
        self._candidate: tuple[str, float] | None = None
        self._away_since: float | None = None

    @property
    def place(self) -> str | None:
        return None if self.asker is None else self.verdict or "unknown"

    def _forget(self) -> None:
        self.verdict = None
        self.confirmed_at = None
        self._candidate = None

    def step(self, observation: Observation) -> None:
        now = observation.time
        on_foot = player_mode(observation) == "foot" and (
            observation.hud is None or observation.hud.screen == "game"
        )
        if on_foot:
            self._away_since = None
        elif self._away_since is None:
            self._away_since = now
        if (self.confirmed_at is not None and now - self.confirmed_at >= 5) or (
            self._away_since is not None and now - self._away_since >= 2
        ):
            self._forget()

        if self.asker is None:
            return
        if self._asked is not None:
            answer = self.asker.answer(self._asked)
            if answer is not None or now - self._asked > 2:
                capture, self._asked = self._asked, None
                shares = answer.where if answer is not None and not answer.error else None
                label = None
                if on_foot and now - capture <= 2 and shares is not None:
                    if len(shares) == len(PLACES) and all(math.isfinite(x) for x in shares):
                        strongest = max(shares)
                        if strongest >= 0.6 and shares.count(strongest) == 1:
                            label = PLACES[shares.index(strongest)]
                if label is None:
                    self._candidate = None
                else:
                    if (
                        self._candidate is not None
                        and self._candidate[0] == label
                        and self._candidate[1] != capture
                    ):
                        self.verdict = label
                        self.confirmed_at = now
                    self._candidate = (label, capture)

        frame = observation.frame
        valid = (
            isinstance(frame, np.ndarray)
            and frame.shape == (720, 1280, 3)
            and frame.dtype == np.uint8
            and not observation.reading.corrupt
        )
        if on_foot and valid and self._asked is None and now - self._last_ask >= 1:
            self._last_ask = now
            if self.asker.ask(frame, now, where=True):
                self._asked = now
