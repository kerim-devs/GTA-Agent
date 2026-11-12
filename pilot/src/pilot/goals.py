"""A bounded free-roam round. Progress needs observations, not a new head event."""

import copy
import random
import re
import secrets
import time
from dataclasses import dataclass, field

from .head import HeadRequest, parse_response
from .legend import kind_of

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


# A trip nobody asked for goes to a shop or a pastime. A mission is chosen when an objective asks for
# one, and an entry the legend prints that is none of these (Chinesen) is of no known sort.
TRIP_KINDS = ("shop", "pastime")
# What set_waypoint reports in `reason` (legend.py): where it went and what it read on the way.
WAYPOINT_SET = re.compile(
    r"^waypoint set: (.+?) \((?:(\d+(?:\.\d+)?)m|distance not read)\); gameplay observed"
)
PLACE_ASKED = re.compile(r"^(place-not-in-legend|legend-selection-skips-the-place): (.+?); gameplay observed")
PLACES_TAIL = re.compile(r"; places: ?(.*)$", re.S)


def read_places(reason: str | None) -> list[str] | None:
    """The destinations a set_waypoint read in the legend; None where its reason names no list."""
    found = PLACES_TAIL.search(reason or "")
    if found is None:
        return None
    return [name.strip() for name in re.split(r",\s*", found.group(1)) if name.strip()]


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
    # Where a drive goal is going, as set_waypoint reported it, and what it was turned away from.
    place: str | None = None
    distance: float | None = None
    tried: set = field(default_factory=set, repr=False)
    nothing: bool = False

    def data(self):
        return {
            "name": self.name,
            "started": self.started,
            "deadline": self.started + LIMITS[self.name][0],
            "seed": self.seed,
            "direction": self.direction,
            "attempts": self.attempts,
            "place": self.place,
            "distance": self.distance,
        }


class Goals:
    # What one decision may change. The conductor can drop the answer it was made for as out of
    # date, and then the state it consumed has to come back or the next one runs short.
    STATE = (
        "active",
        "next",
        "abandoned",
        "history",
        "transition",
        "road_found",
        "known",
        "visited",
        "hint",
        "learned",
    )

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
        # The places a set_waypoint has named, with their sort; where the pilot has been to, in the
        # order of going, across goals; the list the last failure named; the last result learned from.
        self.known: dict[str, str] = {}
        self.visited: list[str] = []
        self.hint: list[str] | None = None
        self.learned: dict | None = None
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
        # A place counts as been to when the trip ended in arrival or ran out its time on the way;
        # a trip cut short by stars or by health says nothing about the place.
        if goal.name == "drive" and goal.place and (reached or reason == "limit"):
            if goal.place not in self.visited:
                self.visited.append(goal.place)
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
        if name == "drive":
            # The legend differs from place to place; a list from an earlier trip may not hold here.
            self.hint = None
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

    def learn(self, last):
        """Take the places a finished set_waypoint named, once for each result."""
        if not last or last.get("name") != "set_waypoint" or last == self.learned:
            return
        self.learned = dict(last)
        reason = last.get("reason") or ""
        names = read_places(reason)
        if names:
            self.known.update({name: kind_of(name) for name in names})
        if last.get("status") == "done":
            self.hint = None
        elif last.get("status") == "failed" and not own_stop(last):
            asked = PLACE_ASKED.match(reason)
            if asked:
                if asked.group(1) == "place-not-in-legend":
                    self.known.pop(asked.group(2), None)
                # What this legend holds, as the failure read it, is where the next try looks.
                self.hint = names

    def _read(self, goal, last):
        """What a result of set_waypoint means for the trip this goal is."""
        if goal.name != "drive" or last.get("name") != "set_waypoint":
            return
        reason = last.get("reason") or ""
        if last.get("status") == "done":
            found = WAYPOINT_SET.match(reason)
            if found:
                goal.place = found.group(1)
                goal.distance = float(found.group(2)) if found.group(2) else None
        elif last.get("status") == "failed" and not own_stop(last):
            asked = PLACE_ASKED.match(reason)
            if asked:
                goal.tried.add(asked.group(2))
                names = read_places(reason)
                if names is not None and not any(kind_of(name) in TRIP_KINDS for name in names):
                    goal.nothing = True

    def _place(self, tried):
        """A shop or pastime the pilot has not been to: the list the last failure named first."""
        pool = self.hint if self.hint is not None else list(self.known)
        options = sorted(n for n in pool if kind_of(n) in TRIP_KINDS and n not in tried)
        if not options:
            return None
        fresh = [n for n in options if n not in self.visited]
        if not fresh:
            # Every one of them has been visited: they are all open again.
            self.visited = [n for n in self.visited if n not in options]
            fresh = options
        return self.random.choice(fresh)

    def trip(self, goal=None, *, follow=120):
        """The calls of a trip nothing asked for: a place from the legend, else a point on the map.

        A goal asks for the place alone and follows the waypoint in a second step, so that the
        head sees where set_waypoint went; the rules' own route asks for both at once."""
        follow_up = [] if goal is not None else [call("drive_route", duration=follow)]
        if goal is None or not goal.nothing:
            place = self._place(goal.tried if goal else set())
            if place:
                return [call("set_waypoint", place=place, duration=45), *follow_up]
            if not self.known and self.hint is None:
                # The first call asks by kind; the legend answers with the places it holds.
                kind = self.random.choice(TRIP_KINDS)
                return [call("set_waypoint", kind=kind, duration=45), *follow_up]
        return [
            call(
                "set_waypoint",
                target="away",
                duration=45,
                direction=goal.direction if goal else "any",
                distance="far",
            ),
            call("drive_route", duration=follow),
        ]

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
            self.learn(last)
            self._read(goal, last)
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
        # A waypoint that was set is followed without a new try: it is the second half of one trip.
        trip_on = (
            goal.name == "drive"
            and fresh
            and last.get("name") == "set_waypoint"
            and last.get("status") == "done"
            and WAYPOINT_SET.match(last.get("reason") or "") is not None
        )
        # Seated in a drive goal a failure is answered by the goal: the next place, and not the
        # rules' point on the map.
        if failed and recovery_plan is not None and not (goal.name == "drive" and seat == "vehicle"):
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
            elif trip_on or request.minimap.get("route") in {"purple", "yellow"}:
                plan = [call("drive_route", duration=120)]
            else:
                plan = self.trip(goal)
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
        # Another place is not the same call again, and needs no look before it.
        if failed and not keep_heading and plan[0]["name"] == last.get("name") != "set_waypoint":
            plan.insert(0, call("look", duration=1.2, angle=180))
        if not trip_on:
            goal.attempts += 1
        goal.step = " → ".join(item["name"] for item in plan)
        reason = self.transition
        if not reason:
            if failed:
                reason = "retry: observed skill failure"
            elif misfit:
                reason = f"step ended: {working} does not fit the figure"
                reason += " seated" if seat == "vehicle" else " on foot"
            elif trip_on:
                reason = "second half of a trip: follow the waypoint that was set"
            else:
                reason = "start next goal step"
        self.transition = ""
        return self._reply(goal, plan, "replace", reason)

    @staticmethod
    def title(goal):
        """What the sentence names: the place a drive goes to, once set_waypoint has said which."""
        if goal.name == "drive" and goal.place:
            far = f", {goal.distance:g} m entfernt" if goal.distance is not None else ""
            return goal.place + far
        return TITLES[goal.name]

    @classmethod
    def _reply(cls, goal, plan, action, reason):
        return parse_response(
            {
                "plan": plan,
                "sentence": f"Mein Ziel bleibt: {cls.title(goal)}."
                if action == "go_on"
                else f"Mein Ziel: {cls.title(goal)}.",
                "action": action,
                "goal": goal.data(),
                "step": goal.step,
                "reason": reason,
            }
        )
