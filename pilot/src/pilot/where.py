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
        self._walked = True  # the figure has been walked since the verdict was last confirmed

    @property
    def place(self) -> str | None:
        return None if self.asker is None else self.verdict or "unknown"

    def _forget(self) -> None:
        self.verdict = None
        self.confirmed_at = None
        self._candidate = None

    def step(self, observation: Observation, walked: bool = True) -> None:
        """`walked` says the stick is pushing the figure on this tick. A figure that stands is where
        it was: on 13 November the camera turned on the landing, looked back through the open door,
        and the picture of the room was taken for the figure's place."""
        now = observation.time
        self._walked = self._walked or walked
        # The radar is part of the game's own screen. A picture without it is a menu, a map or a
        # scene the game plays: on 13 November the pause map of an apartment, a floor plan the HUD
        # reader did not know for a map, was asked about and called the street.
        on_foot = (
            player_mode(observation) == "foot"
            and (observation.hud is None or observation.hud.screen == "game")
            and observation.reading.minimap != "none"
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
                    if self.verdict is not None and label != self.verdict and not self._walked:
                        label = None
                    elif (
                        self._candidate is not None
                        and self._candidate[0] == label
                        and self._candidate[1] != capture
                    ):
                        self.verdict = label
                        self.confirmed_at = now
                        self._walked = False
                    self._candidate = None if label is None else (label, capture)

        frame = observation.frame
        valid = (
            isinstance(frame, np.ndarray)
            and frame.shape == (720, 1280, 3)
            and frame.dtype == np.uint8
            # A damaged map says nothing about the picture once the judge has seen the figure on foot.
            and (observation.mode == "foot" or not observation.reading.corrupt)
        )
        if on_foot and valid and self._asked is None and now - self._last_ask >= 1:
            self._last_ask = now
            if self.asker.ask(frame, now, where=True):
                self._asked = now
