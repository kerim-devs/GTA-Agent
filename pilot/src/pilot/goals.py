"""Errand controller and observation guards shared with the mission head."""

import re

from .errands import (
    LIMITS,  # noqa: F401
    Errands,
)
from .head import HeadRequest

HELD = "dead-or-held"
UNREADABLE = "map-unreadable"
STALLED = ("no-progress", "route-lost-far")
EXIT_TRIES = 3  # presses of the exit before the car is taken to be one the figure cannot leave
AWAY = 12.0  # seconds after leaving a car in which no vehicle is taken, so that it is not taken again
WALK_AWAY = 10.0


def leave_vehicle():
    """Out of a car that will not move, and away from it: the vehicle entry takes the nearest standing one."""
    return [
        call("press", button="triangle", duration=0.1),
        call("wait", duration=2),
        call("walk_road", duration=WALK_AWAY),
    ]


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
FOOT_ONLY = {"walk", "walk_road", "walk_to", "walk_to_point", "face", "punch", "melee", "fight"}
VEHICLE_ONLY = {"drive_route", "get_away", "drive_to_blip"}


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


class Goals(Errands):
    """Session-owned errand policy; chooser receives name/weight/description offers."""
