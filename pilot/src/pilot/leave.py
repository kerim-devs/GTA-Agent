"""Going back out of a building to the street (card P72).

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


class LeaveBuilding(_Unbuilt):
    name = "leave_building"
    parameters: ClassVar = {"duration": (5.0, 120.0, 60.0)}
    prompt = (
        "Indoors on foot: go back out the way the figure came in, else look for the way out, else go "
        "round along the walls, then a few steps straight on in the open. Done 'outdoors' (also when "
        "it began outdoors). Fails no-way-out or time-limit."
    )
