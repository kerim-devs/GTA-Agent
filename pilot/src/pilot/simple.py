"""Three steps and nothing else: a car, a destination, the drive there.

`pilot play --task simple` runs with this head and with a registry cut down to what the three steps
need (`only`). The model chooses the step and the destination, from the picture and one line of what
is known; Python carries out what was chosen and decides nothing about the order. Where the model
does not answer in time, the plain order takes its place and the record says so: no car, a car;
no route, a destination; a route, the drive.

No trip, no errands, no police, no fight, no way back from anything: a step that fails is told to
the model in the next question, and it chooses again.
"""

from __future__ import annotations

import json
from dataclasses import replace

from . import chooser
from .head import HeadRequest, HeadResponse, parse_response
from .mission import movement

# What the three steps are carried out with. `look` and `walk_road` belong to the first: a figure
# with no car in reach turns the camera, and after a round of that walks to the road. `drive_on`
# belongs to the third: in a tunnel the map shows no route, and the car follows the road until it
# is back.
SKILLS = ("enter_vehicle", "set_waypoint", "drive_route", "look", "walk_road", "wait", "drive_on")

STEPS = {
    "car": "Get into a car nearby. For a player who is on foot",
    "mark": "Open the map and mark a destination. For a player in a car with no route marked",
    "drive": "Drive along the marked route. For a player in a car with a route marked",
}

# Places of the town as the German map legend prints them, each with what the model is told of it.
PLACES = {
    "Kino": "Drive to the cinema",
    "Ammu-Nation": "Drive to the gun shop",
    "Autowaschanlage": "Drive to the car wash",
    "Friseursalon": "Drive to the hairdresser",
    "Los Santos Customs": "Drive to the car workshop",
    "Binco Bekleidung": "Drive to the clothes shop",
}

LOOKS = 5  # camera turns of 60 degrees with no car in reach before the figure walks to the road
# Drives in a row that lost their route far from the place before the route counts as gone. Kerim,
# 14 November: in a tunnel the way is not shown, the car has to drive on and the way comes back; it
# had opened the map four times in a tunnel instead (20261114-114025, 522 to 558 s).
HIDDEN = 3
HIDDEN_SECONDS = 20


def only(names=SKILLS):
    """Take every other skill out of the registry: a plan that names one is refused as unknown."""
    from .skills import REGISTRY

    for name in [name for name in REGISTRY if name not in names]:
        del REGISTRY[name]


def _call(name, **args):
    return {"name": name, "args": args}


class SimpleHead:
    TIMEOUT = 2.0

    def __init__(self, *, places=PLACES):
        self.places = dict(places)
        self.place = None  # the destination chosen and not reached yet
        self.left = set()  # the place reached last and one the map did not have: not chosen next
        self.misses = 0  # tries at a car in a row that found none
        self.hidden = 0  # drives in a row that lost a route far from its end
        self.asked = self.answered = self.plain = 0

    def state(self, request: HeadRequest, *, tunnel=False):
        mode = movement(request)
        seat = {"vehicle": "The player sits in a car.", "on_foot": "The player is on foot."}.get(
            mode, "It is unclear whether the player sits in a car."
        )
        route = request.minimap.get("route") in {"purple", "yellow"}
        last = request.last_skill or {}
        ended = ""
        if last.get("status") in {"done", "failed"} and last.get("name") in SKILLS[:3]:
            step = {"enter_vehicle": "car", "set_waypoint": "mark", "drive_route": "drive"}[last["name"]]
            how = "succeeded" if last["status"] == "done" else "failed"
            reason = " ".join(str(last.get("reason") or "").split())[:80]
            ended = f" The last step ({step}) {how}" + (f": {reason}." if reason else ".")
        marked = (
            " A route is marked on the map."
            if route
            else " A route is marked, but out of sight for the moment, as in a tunnel."
            if tunnel
            else " No route is marked on the map."
        )
        return mode, route, seat + marked + ended

    def _choose(self, question, options, request, state, fallback):
        self.asked += 1
        selection = chooser.choose(
            question, options, request.jpeg_path, timeout=self.TIMEOUT, prior={"state": state}
        )
        if selection is not None and selection.name in options:
            self.answered += 1
            scores = json.dumps(selection.probabilities, sort_keys=True)
            return selection.name, f"model chose {selection.name}; probabilities={scores}"
        scores = chooser.probabilities()
        heard = (
            "the model was undecided " + json.dumps(scores, sort_keys=True)
            if scores
            else "no answer from the model"
        )
        return fallback, f"{heard}, plain order: {fallback}"

    def decide(self, request: HeadRequest) -> HeadResponse:
        last = request.last_skill or {}
        if last.get("status") == "running":
            # Asked while a step runs, for news of some kind: the step is not begun again.
            return parse_response({"action": "go_on", "plan": [], "sentence": "Weiter."})
        name, status, why = last.get("name"), last.get("status"), str(last.get("reason") or "")
        visible = request.minimap.get("route") in {"purple", "yellow"}
        if visible:
            self.hidden = 0
        # A route lost far from its end is out of sight, not gone: the car drives on along the road.
        tunnel = (
            not visible
            and name == "drive_route"
            and status == "failed"
            and why.startswith("route-lost")
            and self.hidden < HIDDEN
        )
        mode, route, state = self.state(request, tunnel=tunnel)
        if name == "enter_vehicle":
            self.misses = self.misses + 1 if status == "failed" else 0
        refused = name == "set_waypoint" and status == "failed" and "place-not-in-legend" in why
        arrived = name == "drive_route" and status == "done" and why == "arrived"
        if self.place and (refused or arrived):
            # Reached, or not on the map: the next destination is another one. A destination that
            # only failed to be marked, or was lost on the way, stays and is marked again.
            self.left, self.place = {self.place}, None
        plain = "car" if mode != "vehicle" else "drive" if route or tunnel else "mark"
        # A step that has just succeeded is not offered again at once; a drive that only ran out of
        # its time has not succeeded. With the route out of sight the map is not offered.
        done = {"enter_vehicle": "car", "set_waypoint": "mark"}.get(name if status == "done" else None)
        done = "drive" if arrived else "mark" if tunnel else done
        steps = {step: text for step, text in STEPS.items() if step != done}
        if plain not in steps:
            plain = next(iter(steps))
        step, reason = self._choose("What should the player do next?", steps, request, state, plain)
        self.plain += step == plain
        if step == "car":
            plan = [_call("enter_vehicle", kind="car", occupied="allow", duration=12)]
            if self.misses and self.misses % (LOOKS + 1) == 0:
                plan.insert(0, _call("walk_road", duration=15))
            elif self.misses:
                plan.insert(0, _call("look", angle=60, duration=0.6))
            sentence = "Ich hole mir ein Auto."
        elif step == "mark":
            if self.place is None:
                places = {place: text for place, text in self.places.items() if place not in self.left}
                self.place, chosen = self._choose(
                    "What would be fun for the player to do next?", places, request, state, next(iter(places))
                )
                reason += "; destination: " + chosen
            plan = [_call("set_waypoint", place=self.place, instance=0, duration=45)]
            sentence = f"Ich markiere mir ein Ziel: {self.place}."
        elif tunnel:
            self.hidden += 1
            plan = [_call("drive_on", duration=HIDDEN_SECONDS), _call("drive_route", duration=120)]
            sentence = "Die Route ist gerade nicht zu sehen, ich fahre der Straße nach weiter."
        else:
            plan = [_call("drive_route", duration=120)]
            sentence = "Ich fahre zum Ziel." if not self.place else f"Ich fahre zum Ziel: {self.place}."
        return replace(parse_response({"plan": plan, "sentence": sentence}), reason=reason)
