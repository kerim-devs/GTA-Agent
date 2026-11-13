"""Small rule-built action menu with optional local vision selection."""

from __future__ import annotations

import json
import re
import time
from collections import deque
from dataclasses import dataclass, replace

from pilot import chooser
from pilot.head import HeadRequest, HeadResponse, parse_response
from pilot.mission import movement


@dataclass(frozen=True)
class Candidate:
    name: str
    description: str
    response: HeadResponse


def _candidate(name, description, *plan):
    return Candidate(name, description, parse_response({"plan": list(plan), "sentence": description}))


def _call(name, **args):
    return {"name": name, "args": args}


def _stars(request):
    wanted = (request.hud or {}).get("wanted")
    if wanted is None:
        wanted = next(
            (
                event.get("wanted", 0)
                for event in reversed(request.events)
                if event.get("kind") == "wanted_changed"
            ),
            None,
        )
    return wanted


def _buttons(text):
    names = {
        "circle": r"\b(circle|kreis)\b|○|◯",
        "cross": r"\b(cross|kreuz|x)\b|✕|\u00d7",
        "square": r"\b(square|quadrat|viereck)\b|□|▢",
        "triangle": r"\b(triangle|dreieck)\b|△|▲",
        "options": r"\boptions\b",
        "l1": r"\bl1\b",
        "r1": r"\br1\b",
        "l2": r"\bl2\b",
        "r2": r"\br2\b",
        "l3": r"\bl3\b",
        "r3": r"\br3\b",
        "up": r"\b(up|dpad_up|steuerkreuz oben)\b",
        "down": r"\b(down|dpad_down|steuerkreuz unten)\b",
        "left": r"\b(left|dpad_left|steuerkreuz links)\b",
        "right": r"\b(right|dpad_right|steuerkreuz rechts)\b",
        "touchpad": r"\btouchpad\b",
    }
    return [name for name, pattern in names.items() if re.search(pattern, text, re.I)]


def _blips(request):
    return {
        item.get("color")
        for item in request.minimap.get("blips", [])
        if isinstance(item, dict) and not item.get("border")
    }


def _failed_skills(request):
    failures = [event.get("skill", event) for event in request.events if event.get("kind") == "skill_failed"]
    if (request.last_skill or {}).get("status") == "failed":
        failures.append(request.last_skill)
    return {
        skill.get("name") if isinstance(skill, dict) else skill
        for skill in failures
        if isinstance(skill, (dict, str))
    }


class LocalHead:
    """A MissionHead fallback. Owns no goal and never waits beyond 1.5 seconds."""

    def __init__(self, *, timeout=1.5):
        self.timeout = min(1.5, max(0, timeout))
        self._health: float | None = None
        self._health_fell = False

    def candidates(self, request: HeadRequest) -> tuple[Candidate, ...]:
        choices = []

        def add(name, description, *plan):
            choices.append(_candidate(name, description, *plan))

        buttons = _buttons(request.help)
        stuck = any(event.get("kind") in {"stuck", "reflex_stuck"} for event in request.events)
        if stuck:
            buttons = _buttons(" ".join((request.help, request.subtitle, request.banner)))
            # Circle is the safe back button even if footer OCR missed its glyph.
            for button in ["circle", *(button for button in buttons if button != "circle")][:6]:
                add(
                    f"press_{button}",
                    f"Press {button} once to leave this screen",
                    _call("press", button=button, count=1, duration=0.1),
                )
            return tuple(choices)

        mode = movement(request)
        colors = _blips(request)
        target = next((color for color in ("yellow", "blue") if color in colors), None)
        objective = request.objective.strip()
        scene = (request.hud or {}).get("screen") == "cutscene"
        vehicle = any(
            obj.get("kind") in {"car", "truck", "bus", "motorcycle", "vehicle"} for obj in request.objects
        )
        if mode == "on_foot" and not scene:
            if not objective:
                add("road", "Walk along the road", _call("walk_road", duration=8))
            if target:
                add("target", "Walk to the marked target", _call("walk_to", color=target))
            if objective and buttons:
                add("prompt", "Perform the displayed button action", _call("do_prompt"))
            health_fell = self._health_fell or any(
                event.get("kind") in {"health_drop", "health_dropped"}
                or (event.get("kind") == "health_changed" and event.get("delta", 0) < 0)
                for event in request.events
            )
            fight_objective = bool(
                re.search(
                    r"\b(kill|eliminate|take out|shoot|töte|erledige|schalte|erschieß)",
                    objective,
                    re.I,
                )
            )
            if "red" in colors and (fight_objective or health_fell):
                add("fight", "Fight the nearby hostile markers", _call("fight", duration=10))
            if vehicle:
                add("vehicle", "Enter a vehicle in view", _call("enter_vehicle"))
            if not objective:
                if buttons:
                    add("prompt", "Perform the displayed button action", _call("do_prompt"))
                add(
                    "look",
                    "Look around and walk ahead",
                    _call("look", angle=90),
                    _call("walk", duration=1, y=-0.5),
                )
            elif not choices:
                # No grounded target/action: a short look gathers another view.
                add(
                    "look",
                    "Look around and walk ahead",
                    _call("look", angle=90),
                    _call("walk", duration=1, y=-0.5),
                )
        elif mode == "vehicle" and not scene:
            if request.minimap.get("route") in {"yellow", "purple"}:
                add("route", "Follow the visible route", _call("drive_route", duration=20))
            last = request.last_skill or {}
            ended = (
                last.get("name") == "drive_route"
                and last.get("status") == "done"
                and last.get("reason") in {"arrived", "route-gone"}
            ) or any(
                event.get("kind") in {"route_ended", "arrived", "at_destination"} for event in request.events
            )
            if ended:
                add("exit", "Get out at the destination", _call("press", button="triangle", count=1))
            # Unknown wanted state is not permission to open the map either.
            if _stars(request) == 0:
                add(
                    "mission",
                    "Set a mission waypoint and follow its route",
                    _call("set_waypoint", target="mission"),
                    _call("drive_route", duration=20),
                )
            add("wait", "Wait three seconds", _call("wait", duration=3))
        elif buttons and not scene:
            for button in buttons[:5]:
                add(f"press_{button}", f"Press {button} once", _call("press", button=button, count=1))
        if scene:
            add("scene", "Wait for the scene for three seconds", _call("wait", duration=3))
        if not choices:
            # A second, not a tenth: every wait that ends asks the head again, and a view that stays
            # unreadable (a cutscene with no HUD) asked it and wrote a picture ten times a second.
            # News of any kind interrupts the wait.
            add("observe", "Wait briefly for a readable view", _call("wait", duration=1))
        return tuple(choices[:6])

    def decide(self, request: HeadRequest) -> HeadResponse:
        started = time.monotonic()
        health = (request.hud or {}).get("health")
        self._health_fell = (
            isinstance(health, (float, int)) and self._health is not None and health < self._health
        )
        self._health = health if isinstance(health, (float, int)) else None
        failed_skills = _failed_skills(request)
        options = [
            candidate
            for candidate in self.candidates(request)
            if not any(call.name in failed_skills for call in candidate.response.plan)
        ]
        if not options:
            options = [_candidate("observe", "Wait briefly and reassess", _call("wait", duration=1))]
        selection = chooser.choose(
            "What should the player do next?",
            {candidate.name: candidate.description for candidate in options},
            request.jpeg_path,
            timeout=max(0, self.timeout - (time.monotonic() - started)),
            prior={"objective": request.objective, "help": request.help},
        )
        selected = next(
            (option for option in options if selection is not None and option.name == selection.name),
            options[0],
        )
        scores = selection.probabilities if selection is not None else chooser.probabilities()
        reason = (
            f"local model chose {selected.name}; probabilities="
            + json.dumps(selection.probabilities, sort_keys=True)
            if selection is not None
            else f"local fallback chose {selected.name}; probabilities="
            + (json.dumps(scores, sort_keys=True) if scores else "unavailable")
        )
        return replace(selected.response, reason=reason)


class ErrandChooser:
    """P70 callable: weighted described candidates in, original candidate or None out.

    Supply the current HeadRequest with observe() before asking Goals. Model choices
    are recorded automatically; call record() only for the final seeded fallback.
    """

    def __init__(self, *, timeout=1.5):
        self.timeout = min(1.5, max(0, timeout))
        self.request: HeadRequest | None = None
        self.recent = deque(maxlen=3)

    def observe(self, request: HeadRequest):
        self.request = request

    @staticmethod
    def _field(candidate, key):
        return candidate[key] if isinstance(candidate, dict) else getattr(candidate, key)

    def record(self, candidate):
        self.recent.append(self._field(candidate, "name"))

    def __call__(self, candidates):
        if self.request is None:
            return None
        eligible = [
            candidate for candidate in candidates if self.recent.count(self._field(candidate, "name")) < 2
        ][:6]
        if not eligible:
            return None
        options = {
            self._field(candidate, "name"): self._field(candidate, "description") for candidate in eligible
        }
        selection = chooser.choose(
            "What would be fun for the player to do next?",
            options,
            self.request.jpeg_path,
            timeout=self.timeout,
            prior={"objective": self.request.objective, "help": self.request.help},
        )
        if selection is None:
            return None
        chosen = next(
            (candidate for candidate in eligible if self._field(candidate, "name") == selection.name), None
        )
        if chosen is not None:
            self.record(chosen)
        return chosen
