"""Using a place the figure stands in, and doing what the game's help text asks for (card P71).

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


class UsePlace(_Unbuilt):
    name = "use_place"
    parameters: ClassVar = {
        "duration": (5.0, 120.0, 60.0),
        "spend": ("yes", "no"),
        "choice": ("random", "first"),
    }
    prompt = (
        "In a shop, at its chair, counter or rack: find the game's help prompt, press its button, take "
        "one entry of the menu that opens (spend=no looks and buys nothing) and back out of the menu. "
        "Done 'used: <prompt>'. Fails no-prompt (nothing to use here), menu-unread, too-dear or time-limit."
    )
    opens: ClassVar = ("interaction_menu",)


class DoPrompt(_Unbuilt):
    name = "do_prompt"
    parameters: ClassVar = {"duration": (0.2, 10.0, 3.0)}
    prompt = (
        "Press the button the game's help text in the top left asks for, once, as a player would. "
        "Done 'pressed: <button>'. Fails no-prompt when the help text names no button it knows, and "
        "never opens the phone, the map or a menu of its own."
    )
