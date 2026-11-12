"""A bounded free-roam round. Progress needs observations, not a new head event."""

import copy
import random
import secrets
import time
from dataclasses import dataclass, field

from .head import HeadRequest, parse_response

# Limits cover retries as well as time spent waiting for a head answer.
LIMITS = {
    "vehicle": (90, 3),
    "drive": (240, 3),
    "fight": (90, 4),
    "escape": (180, 4),
    "road": (90, 4),
}
TITLES = {
    "vehicle": "ein Fahrzeug nehmen",
    "drive": "weit fahren und ankommen",
    "fight": "auf der Straße jemanden schlagen",
    "escape": "der Polizei entkommen",
    "road": "eine Straße finden",
}
SUCCESSOR = {"vehicle": "drive", "drive": "fight", "fight": "escape", "escape": "vehicle", "road": "vehicle"}


# Skills that fit one way of moving only. On foot the stick walks the figure, a minimap blip is
# followed on a flat map and the face buttons strike; seated, the same pad steers and accelerates
# the vehicle. drive_route is the converse: its throttle and wheel mean nothing to a figure on foot.
# enter_vehicle crosses from one to the other by design, and set_waypoint, look, press, wait,
# shoot and level_camera do the same thing in either.
FOOT_ONLY = {"walk", "walk_road", "walk_to", "face", "punch", "melee", "fight"}
VEHICLE_ONLY = {"drive_route"}


def call(name, **args):
    return {"name": name, "args": args}


def own_stop(last: dict | None) -> bool:
    """The conductor stopped this skill for the goal; that is no failure of the skill."""
    return bool(last) and last.get("status") == "failed" and str(last.get("reason") or "").startswith("goal_")


def occupancy(mode: str, events) -> str:
    """Where the figure sits: the latest change the events report outranks the mode named before it."""
    seat = mode
    for event in events:
        if event.get("kind") == "vehicle_exit":
            seat = "on_foot"
        elif event.get("kind") == "vehicle_enter":
            seat = "vehicle"
    return seat


def fits(skill: str, seat: str) -> bool:
    """A mode nobody could read says nothing against the skill."""
    if skill in FOOT_ONLY:
        return seat != "vehicle"
    if skill in VEHICLE_ONLY:
        return seat != "on_foot"
    return True


def interruption(request: HeadRequest, goal: dict | None = None) -> str | None:
    """Shared by the head and the tick loop, before another controller command."""
    hud = request.hud or {}
    events = request.events
    kinds = {event.get("kind") for event in events}
    screen = hud.get("screen")
    event_screens = {event.get("screen") for event in events if event.get("kind") == "screen"}
    if event_screens & {"wasted", "busted"}:
        return "death_or_arrest"
    if screen in {"wasted", "busted", "dead", "arrested", "death", "arrest"} or kinds & {
        "wasted",
        "busted",
        "death",
        "arrest",
        "dead",
        "arrested",
    }:
        return "death_or_arrest"
    if request.objective.strip():
        return "objective"
    health = hud.get("health")
    if (health is not None and health < 1 / 3) or (health is None and "low_health" in kinds):
        return "low_health"
    wanted = hud.get("wanted")
    if wanted is None:
        wanted = next((e.get("wanted", 0) for e in reversed(events) if e.get("kind") == "wanted_changed"), 0)
    if wanted and (goal or {}).get("name") != "escape":
        return "stars"
    if goal and request.time is not None and request.time >= goal["deadline"]:
        return "limit"
    return None


@dataclass
class Goal:
    name: str
    started: float
    seed: int
    direction: str
    attempts: int = 0
    step: str = ""
    seen_wanted: bool = False
    seen_route: bool = False
    last_result: dict | None = field(default=None, repr=False)

    def data(self):
        return {
            "name": self.name,
            "started": self.started,
            "deadline": self.started + LIMITS[self.name][0],
            "seed": self.seed,
            "direction": self.direction,
            "attempts": self.attempts,
        }


class Goals:
    # What one decision may change. The conductor can drop the answer it was made for as out of
    # date, and then the state it consumed has to come back or the next one runs short.
    STATE = ("active", "next", "abandoned", "history", "transition", "road_found")

    def __init__(self, seed=None, clock=time.monotonic):
        self.seed = secrets.randbits(32) if seed is None else seed
        self.random = random.Random(self.seed)
        self.clock = clock
        self.active: Goal | None = None
        self.next = "vehicle"
        self.abandoned: str | None = None
        self.history: list[dict] = []
        self.transition = ""
        self.road_found = False
        self._undo = None

    def mark(self):
        self._undo = (copy.deepcopy({key: getattr(self, key) for key in self.STATE}), self.random.getstate())

    def undo(self):
        """Take back everything the last decision consumed."""
        if self._undo is None:
            return
        state, generator = self._undo
        for key, value in state.items():
            setattr(self, key, value)
        self.random.setstate(generator)
        self._undo = None

    def now(self, request):
        return self.clock() if request.time is None else request.time

    def end(self, request, reason, *, reached=False):
        goal = self.active
        if goal is None:
            return
        self.transition = f"{goal.name} {'reached' if reached else 'gave_up'}: {reason}"
        self.history.append(
            {
                **goal.data(),
                "time": self.now(request),
                "outcome": "reached" if reached else "gave_up",
                "reason": reason,
            }
        )
        self.next = SUCCESSOR[goal.name]
        self.abandoned = None if reached else goal.name
        self.active = None

    def guard(self, request):
        reason = interruption(request, self.active.data() if self.active else None)
        if reason and self.active:
            self.end(request, reason)
        return reason

    def _start(self, request, mode, cars, wanted):
        name = self.next
        if wanted:
            name = "escape"
        elif mode == "vehicle":
            name = "fight" if name == "fight" else "drive"
        elif name == "fight":
            pass
        elif name == "escape":
            # No stars yet: stay on the street until wanted is observed, bounded by its limit.
            pass
        else:
            name = "vehicle" if cars or self.road_found else "road"
        if name == self.abandoned:
            name = "fight" if mode == "vehicle" else ("road" if name != "road" else "vehicle")
        self.active = Goal(
            name, self.now(request), self.seed, self.random.choice(("north", "east", "south", "west"))
        )
        self.history.append(
            {
                **self.active.data(),
                "time": self.now(request),
                "outcome": "started",
                "reason": self.transition or "round start",
            }
        )
        return self.active

    def decide(self, request, mode, *, escape_plan=None, recovery_plan=None, keep_heading=False):
        """Called only for free roam or the existing wanted rules."""
        cars = any(o.get("kind") in {"car", "truck", "motorcycle"} for o in request.objects)
        wanted = (request.hud or {}).get("wanted")
        if wanted is None:
            wanted = next(
                (e.get("wanted", 0) for e in reversed(request.events) if e.get("kind") == "wanted_changed"),
                None,
            )
        seat = occupancy(mode, request.events)
        goal = self.active or self._start(request, seat, cars, wanted)
        last = request.last_skill or {}
        working = last.get("name") if last.get("status") == "running" else None
        misfit = working is not None and not fits(working, seat)
        running = (
            goal.attempts > 0
            and not misfit
            and (
                last.get("status") in {"running", "queued"}
                or bool(last.get("queue"))
                or bool(last.get("pending"))
            )
        )
        fresh = last != goal.last_result
        if fresh:
            goal.last_result = dict(last)
        if wanted:
            goal.seen_wanted = True
        if request.minimap.get("route") in {"purple", "yellow"}:
            goal.seen_route = True
        reached = None
        if (
            goal.name == "vehicle"
            and seat == "vehicle"
            and not (last.get("name") == "enter_vehicle" and last.get("status") == "running")
        ):
            reached = "vehicle observed"
        elif (
            goal.name == "drive"
            and goal.attempts > 0
            and (goal.seen_route or last.get("route_seen"))
            and fresh
            and last.get("name") == "drive_route"
            and last.get("status") == "done"
            and last.get("reason") in {"arrived", "route-gone"}
        ):
            reached = "route arrival observed"
        elif (
            goal.name == "fight"
            and goal.attempts > 0
            and fresh
            and last.get("name") == "punch"
            and last.get("status") == "done"
        ):
            reached = "punch attempts completed (contact is not measured)"
        elif (
            goal.name == "road"
            and goal.attempts > 0
            and (seat == "vehicle" or cars or last.get("road_reached"))
        ):
            reached = (
                "road observed under player"
                if last.get("road_reached")
                else "vehicle seen while seeking a road"
            )
            self.road_found = True
        elif goal.name == "escape" and goal.seen_wanted and wanted == 0:
            reached = "wanted cleared"
        if reached:
            self.end(request, reached, reached=True)
            goal = self._start(request, seat, cars, wanted)
            running = False
        if self.now(request) >= goal.data()["deadline"] or (
            not running and goal.attempts >= LIMITS[goal.name][1]
        ):
            self.end(request, "limit")
            if goal.name == "escape" and wanted and escape_plan is not None:
                return parse_response(
                    {
                        "plan": escape_plan,
                        "sentence": "Die Flucht ist weiter nötig, ich folge den Polizeiregeln.",
                        "reason": self.transition,
                        "step": "escape rules",
                    }
                )
            goal = self._start(request, seat, cars, wanted)
            running = False
        if running:
            return self._reply(
                goal, [], "go_on", self.transition or "kept: running skill and queue still serve this goal"
            )

        failed = last.get("status") == "failed" and fresh and not own_stop(last)
        if failed and recovery_plan is not None:
            plan = recovery_plan
        elif goal.name == "escape" and wanted and escape_plan is not None:
            plan = escape_plan
        elif goal.name == "vehicle":
            plan = (
                [call("enter_vehicle", duration=25, kind="any")] if cars else [call("walk_road", duration=15)]
            )
        elif goal.name == "drive":
            if seat != "vehicle":
                plan = (
                    [call("enter_vehicle", duration=25, kind="any")]
                    if cars
                    else [call("walk_road", duration=15)]
                )
            elif request.minimap.get("route") in {"purple", "yellow"}:
                plan = [call("drive_route", duration=120)]
            else:
                plan = [
                    call(
                        "set_waypoint", target="away", duration=45, direction=goal.direction, distance="far"
                    ),
                    call("drive_route", duration=120),
                ]
        elif goal.name == "fight":
            if seat == "vehicle":
                plan = [call("press", button="triangle", duration=0.1), call("wait", duration=2)]
            elif any(o.get("kind") == "person" for o in request.objects):
                plan = [call("punch", duration=20, hits=3)]
            else:
                plan = [call("look", duration=0.8, angle=55), call("walk_road", duration=15)]
        elif goal.name == "escape":
            plan = (
                [call("walk", duration=5, x=0, y=-1, sprint=True)]
                if seat == "on_foot"
                else [call("drive_route", duration=60)]
            )
        else:
            plan = [call("walk_road", duration=15)]
        if failed and not keep_heading and plan[0]["name"] == last.get("name"):
            plan.insert(0, call("look", duration=1.2, angle=180))
        goal.attempts += 1
        goal.step = " → ".join(item["name"] for item in plan)
        if misfit:
            misfit_reason = f"step ended: {working} does not fit the figure"
            misfit_reason += " seated" if seat == "vehicle" else " on foot"
        reason = self.transition or (
            "retry: observed skill failure" if failed else misfit_reason if misfit else "start next goal step"
        )
        self.transition = ""
        return self._reply(goal, plan, "replace", reason)

    @staticmethod
    def _reply(goal, plan, action, reason):
        return parse_response(
            {
                "plan": plan,
                "sentence": f"Mein Ziel bleibt: {TITLES[goal.name]}."
                if action == "go_on"
                else f"Mein Ziel: {TITLES[goal.name]}.",
                "action": action,
                "goal": goal.data(),
                "step": goal.step,
                "reason": reason,
            }
        )
