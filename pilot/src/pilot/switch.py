"""Switching to another of the story's three characters (card P75).

This file holds the skill's name, arguments and prompt as the head plans with them, so that the
rules can be written before the skill is built. Until its card is done every call fails `not-built`.
"""

from typing import ClassVar

from pilot.contract import Observation, SkillResult


class _Unbuilt:
    parameters: ClassVar = {}

    def __init__(self, args: dict):
        if not isinstance(args, dict) or set(args) - self.parameters.keys():
            raise ValueError(f"{self.name} accepts only {', '.join(self.parameters)}")
        low, high, default = self.parameters["duration"]
        value = args.get("duration", default)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("duration must be a number")
        self.limit = float(max(low, min(high, value)))
        self.finished = None

    def step(self, observation: Observation) -> SkillResult:
        return self.stop("not-built")

    def stop(self, reason: str = "interrupted") -> SkillResult:
        self.finished = SkillResult(status="failed", reason=reason)
        return self.finished


class SwitchCharacter(_Unbuilt):
    name = "switch_character"
    parameters: ClassVar = {"duration": (4.0, 40.0, 25.0), "to": ("next", "michael", "franklin", "trevor")}
    prompt = (
        "Switch to another of the three story characters with the game's own wheel, never to the "
        "fourth slot. Free roam only, on foot or seated, with no stars. Done 'switched: <name>' once "
        "the game is back; fails switch-refused, wheel-unread or time-limit."
    )
