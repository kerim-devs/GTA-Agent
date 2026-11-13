"""The capability bench: a catalogue that names every capability and what counts as done, a judge that
decides a recorded session against it, an append-only ledger and a board that shows where it hurts.

Nothing here talks to the console. The loop that does (`bench_run.py`) goes through two small functions
that tests replace. A new capability is one entry in CATALOGUE (see lab/bench/README.md); its proof is a
tuple of the named pieces of `bench_proofs.py`, so a new proof is a new piece and one line in the entry.
"""

from __future__ import annotations

import argparse
import html
import itertools
import json
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import bench_proofs as proofs
from .bench_proofs import Evidence, Session, Try, as_numbers, read_jsonl

DEFAULT_LEDGER = Path("/Users/kerim/recordings/pilot/bench.jsonl")
CAUSES = ("see", "decide", "act", "proof", "world", "tech", "unclear")
OUTCOMES = ("ok", "failed", "not_counted")
REPO = Path(__file__).resolve().parents[3]


def step(name: str, **args: Any) -> dict:
    return {"name": name, "args": args}


def P(name: str, **params: Any) -> tuple[str, dict]:  # noqa: N802
    """One named proof piece with its parameters, as an entry lists it."""
    return (name, params)


@dataclass(frozen=True)
class Capability:
    id: str
    group: str
    title: str
    german: str  # the board is read by Kerim; the catalogue's German titles are the only German in the code
    start: tuple[str, ...]  # names in START_STATES
    plan: tuple[dict, ...]  # the head's plan that tries it; empty for an opening or a harvested capability
    seconds: int  # what a try gets
    proof: tuple[tuple[str, dict], ...]  # named pieces, all of which have to hold
    mark: int = 9  # successes in the last ten counted tries that make it green
    skills: tuple[str, ...] = ()  # whose verdict is the skill's; defaults to the plan's skills
    done_reasons: tuple[str, ...] = ()  # when set, a skill that is done for another reason has not done it
    opening: bool = False  # tried as the session's own opening, not as the head's plan
    vary: tuple[tuple[int, str, tuple], ...] = ()  # (plan step, argument, values) that change try by try
    scramble: bool = False  # the loop presses the touchpad first so that the view differs from try to try
    level: bool = (
        True  # the session opens with the far view and the levelled camera; off where the map is the subject
    )
    ends: tuple[tuple[str, bool], ...] = ()  # start states a try is expected to leave; only `--dry` reads it
    built: bool = True
    harvested: bool = False  # cannot be staged; every session is searched for its moments

    @property
    def skill_names(self) -> tuple[str, ...]:
        return self.skills or tuple(dict.fromkeys(s["name"] for s in self.plan))

    @property
    def plan_names(self) -> tuple[str, ...]:
        return tuple(s["name"] for s in self.plan) or self.skill_names

    @property
    def runnable(self) -> bool:
        return self.built and not self.harvested and bool(self.plan or self.opening)

    def unmeasured(self) -> list[str]:
        """What the card's "done when" asks for that no log can show: the entry's `unmeasured` pieces."""
        return [
            params.get("missing") or params.get("what", "")
            for name, params in self.proof
            if name == "unmeasured"
        ]

    def describe_proof(self) -> str:
        return proofs.describe(self.proof)


def plan_for(cap: Capability, number: int) -> tuple[dict, ...]:
    """The plan of the `number`-th try of a capability: its steps with the arguments that vary."""
    steps = [{"name": s["name"], "args": dict(s["args"])} for s in cap.plan]
    for index, argument, values in cap.vary:
        steps[index]["args"][argument] = values[number % len(values)]
    return tuple(steps)


# ---- the start states a capability needs, read from the first seconds of a session
@dataclass(frozen=True)
class StartState:
    check: Callable[..., bool | None]  # (session, from, to, end=bool) -> yes / no / not clear
    producer: str | None  # the capability whose try makes this state, None where nothing can
    text: str


def _mode_is(want: str):
    def check(session: Session, t0: float, t1: float, end: bool = False):
        return None if (mode := session.mode_over(t0, t1)).mode is None else mode.mode == want

    return check


def _route_there(session: Session, t0: float, t1: float, end: bool = False):
    rows = [read for read in map(proofs.minimap_read, session.ticks(t0, t1)) if read]
    if len(rows) < proofs.MIN_MINIMAP:
        return None
    return sum(r.get("route") in ("purple", "yellow") for r in rows) / len(rows) >= 0.6


def _route_metres(session: Session, t0: float, t1: float, end: bool) -> float | None:
    """The route distance the game prints on the vehicle map: the first reading just after the start, or
    the last one in the final seconds."""
    span = (max(t0, t1 - 6.0), t1) if end else (t0, t0 + 3.0)
    readings = [
        r["reading"]["gps_distance"]
        for r in session.ticks(*span)
        if isinstance((r.get("reading") or {}).get("gps_distance"), (int, float))
    ]
    if not readings:
        return None
    return readings[-1] if end else readings[0]


def _far_route(session: Session, t0: float, t1: float, end: bool = False):
    metres = _route_metres(session, t0, t1, end)
    return None if metres is None else metres >= 150


def _near_route(session: Session, t0: float, t1: float, end: bool = False):
    metres = _route_metres(session, t0, t1, end)
    return None if metres is None else metres <= 600


def _yellow_blip(session: Session, t0: float, t1: float, end: bool = False):
    rows = [read for read in map(proofs.minimap_read, session.ticks(t0, t1)) if read]
    if len(rows) < proofs.MIN_MINIMAP:
        return None
    seen = sum(any(b.get("color") == "yellow" for b in r.get("blips", [])) for r in rows)
    return seen / len(rows) >= 0.6


def _game_screen(session: Session, t0: float, t1: float, end: bool = False):
    screens = (
        session.screens(max(t0, t1 - 0.5), t1, 0.25) if end else session.screens(t0, min(t1, t0 + 0.5), 0.25)
    )
    if not screens:
        return None
    return all(screen == "game" for _, screen in screens)


START_STATES: dict[str, StartState] = {
    "foot": StartState(_mode_is("foot"), "car.leave", "the figure on foot"),
    "vehicle": StartState(_mode_is("vehicle"), "foot.enter", "the figure in a vehicle"),
    "route": StartState(_route_there, "map.place", "a route on the minimap"),
    # A try that follows or arrives needs a destination that a drive of 30 or 60 s can get nearer to or reach.
    "route_far": StartState(_far_route, "map.place", "a route of at least 150 m"),
    "route_near": StartState(_near_route, "map.place", "a route of at most 600 m"),
    "yellow_target": StartState(
        _yellow_blip, None, "a yellow blip on the minimap; nothing in the catalogue makes one"
    ),
    "game": StartState(_game_screen, None, "the game's own screen, no menu"),
    "behind": StartState(lambda *_, **__: None, None, "the route behind the vehicle; not readable"),
}


def state_of(session: Session, *, end: bool = False) -> dict[str, bool | None]:
    """Every start state over the first (or the last) seconds of a session."""
    if not session.play:
        return {name: None for name in START_STATES}
    if end:
        t0, t1 = max(session.start, session.end - proofs.END_STRETCH), session.end
    else:
        t0, t1 = session.start, session.start + proofs.START_STRETCH
    return {name: state.check(session, t0, t1, end=end) for name, state in START_STATES.items()}


def meets(state: dict[str, bool | None], needed: tuple[str, ...]) -> bool:
    return all(state.get(name) is True for name in needed)


def objective_on_screen(session: Session) -> dict:
    """Whether the game showed an objective during the session: the head's requests carry the text the
    reader found. None where no request was made."""
    texts = [str(r["objective"]).strip() for r in session.requests if "objective" in r]
    if not texts:
        return {"on_screen": None, "text": ""}
    shown = [t for t in texts if t]
    return {"on_screen": bool(shown), "text": shown[0][:120] if shown else "", "at_start": bool(texts[0])}


def mission_signs(session: Session) -> dict:
    """Whether a mission is active at the end of a session, as far as the logs can tell: an objective text
    that the head's last request read in the last ten seconds, and a yellow route on the minimap (the
    mission's own colour). A purple route or a blip alone proves nothing: a waypoint of the player's looks
    the same. None where the log has no reading."""
    recent = [r for r in session.requests if "objective" in r and session.end - r["t"] <= 10]
    objective = None if not recent else bool(str(recent[-1]["objective"]).strip())
    rows = [
        read
        for read in map(
            proofs.minimap_read,
            session.ticks(max(session.start, session.end - proofs.END_STRETCH), session.end),
        )
        if read
    ]
    yellow = (
        None
        if len(rows) < proofs.MIN_MINIMAP
        else sum(r.get("route") == "yellow" for r in rows) / len(rows) >= 0.6
    )
    return {"objective": objective, "yellow_route": yellow, "active": bool(objective) or bool(yellow)}


CATALOGUE: dict[str, Capability] = {
    c.id: c
    for c in (
        Capability(
            "foot.view",
            "foot",
            "Set the far view",
            "Sicht einstellen",
            ("foot",),
            (),
            45,
            (P("view_far_at_end"),),
            skills=("set_far_view",),
            opening=True,
            scramble=True,
        ),
        Capability(
            "foot.walk",
            "foot",
            "Walk along the road",
            "Laufen",
            ("foot",),
            (step("walk_road", duration=20),),
            28,
            (P("moving_on_most_ticks", seconds=20, share=0.5, hold=3.0),),
        ),
        Capability(
            "foot.walk_to",
            "foot",
            "Walk to a point",
            "Zu einem Punkt laufen",
            ("foot", "yellow_target"),
            (step("walk_to", duration=10, color="yellow", sprint=False),),
            18,
            (P("within_metres_of_blip", metres=10),),
        ),
        Capability(
            "foot.roadside",
            "foot",
            "Stay at the roadside",
            "Am Straßenrand bleiben",
            ("foot",),
            (),
            28,
            (
                P(
                    "unmeasured",
                    what="never standing or waiting on the carriageway",
                    missing=(
                        "no roadside skill and no road position in any log: the road reader would have to "
                        "write where the figure stands relative to the carriageway per tick"
                    ),
                ),
            ),
            built=False,
        ),
        Capability(
            "foot.enter",
            "foot",
            "Get into a vehicle",
            "Einsteigen",
            ("foot",),
            (step("enter_vehicle", duration=20, kind="any"),),
            28,
            (
                P("seated_within", seconds=20),
                P("seated_at_end", step=0),  # when the skill ended, not when the session did
                P(
                    "unmeasured",
                    what="the vehicle stood still and had no driver",
                    missing=(
                        "speed and occupancy of the vehicle that was entered are in no log: the vehicle "
                        "reader or cli play would have to write the chosen vehicle's box per tick"
                    ),
                ),
            ),
            ends=(("vehicle", True), ("foot", False)),
        ),
        Capability(
            "car.leave",
            "car",
            "Get out of a vehicle",
            "Aussteigen",
            ("vehicle",),
            (step("press", button="triangle", duration=1),),
            8,
            (P("on_foot_at_end"),),
            ends=(("foot", True), ("vehicle", False), ("route", False)),
        ),
        Capability(
            "car.follow",
            "car",
            "Follow the route",
            "Der Route folgen",
            ("vehicle", "route", "route_far"),
            (step("drive_route", duration=30),),
            38,
            (P("distance_fell", metres=100, within=30), P("never_held", seconds=5, within=30)),
        ),
        Capability(
            "car.arrive",
            "car",
            "Arrive",
            "Ankommen",
            ("vehicle", "route", "route_far", "route_near"),
            (step("drive_route", duration=60),),
            66,
            (P("arrived", metres=30),),
            done_reasons=("route-gone", "arrived"),
        ),
        Capability(
            "car.free",
            "car",
            "Get free",
            "Sich befreien",
            ("vehicle",),
            (),
            10,
            (
                P(
                    "unmeasured",
                    what="moving again within 10 s of being held",
                    missing=(
                        "no independent movement field and no record of when a recovery began: the "
                        "driver would have to log its recoveries with a start time"
                    ),
                ),
            ),
            harvested=True,
        ),
        Capability(
            "car.turn",
            "car",
            "Turn around",
            "Wenden",
            ("vehicle", "route", "behind"),
            (),
            15,
            (
                P(
                    "unmeasured",
                    what="heading along the route within 15 s",
                    missing="no turn skill and no route-relative heading in the play log",
                ),
            ),
            built=False,
        ),
        Capability(
            "map.open_close",
            "map",
            "Open and close the map",
            "Karte auf und zu",
            ("game",),
            (
                step("press", button="options", duration=0.2),
                step("wait", duration=2),
                step("press", button="circle", duration=0.2),
            ),
            8,
            (P("map_opened"), P("game_back")),
            skills=("press",),
            level=False,
        ),
        Capability(
            "map.place",
            "map",
            "Choose a place from the legend",
            "Ort aus der Liste wählen",
            ("game",),
            (step("set_waypoint"),),
            52,
            (P("game_back"), P("waypoint_changed")),
            # The places the legend showed at the console on 12 November; consecutive tries name
            # different ones, because a waypoint set again on the same place proves nothing.
            vary=(
                (
                    0,
                    "place",
                    ("Ammu-Nation", "Beekers Garage", "Los Santos Customs", "Ammu-Nation mit Schießstand"),
                ),
            ),
            level=False,
            ends=(("route", True),),
        ),
        Capability(
            "map.mission",
            "map",
            "Choose a mission",
            "Missionsziel wählen",
            ("game",),
            (step("set_waypoint", kind="mission"),),
            52,
            (P("game_back"), P("waypoint_changed")),
            vary=((0, "instance", (0, 1, 2)),),
            level=False,
            ends=(("route", True),),
        ),
        Capability(
            "goal.keep",
            "goal",
            "Keep a goal",
            "Ein Ziel halten",
            ("game",),
            (),
            60,
            (
                P(
                    "unmeasured",
                    what="a goal ends by its own condition or a listed event, not by a replaced plan",
                    missing=(
                        "no goal id, end condition or replaced-plan marker in the play log, and no fixed "
                        "plan that holds a goal: the conductor would have to log goals with their end"
                    ),
                ),
            ),
        ),
        Capability(
            "incident.menu",
            "incident",
            "Close a foreign menu",
            "Fremdes Menü schließen",
            (),
            (),
            5,
            (
                P(
                    "unmeasured",
                    what="the game is back within 5 s",
                    missing="the reflex's result and attempt are not logged: the conductor would have to",
                ),
            ),
            harvested=True,
        ),
        Capability(
            "incident.down",
            "incident",
            "Carry on after death or arrest",
            "Nach Tod oder Verhaftung weiter",
            (),
            (),
            30,
            (
                P(
                    "unmeasured",
                    what="playing again within 30 s of the respawn",
                    missing="no respawn timestamp or resumed-control marker in the logs",
                ),
            ),
            harvested=True,
        ),
        Capability(
            "incident.wanted",
            "incident",
            "Lose the stars",
            "Sterne loswerden",
            (),
            (),
            180,
            (
                P(
                    "unmeasured",
                    what="no stars within 3 minutes",
                    missing="the escape's result and attempt are not logged: the conductor would have to",
                ),
            ),
            harvested=True,
        ),
        Capability(
            "chain.basic",
            "chain",
            "The basic chain",
            "Grundkette",
            ("foot",),
            (
                step("enter_vehicle", duration=20, kind="any"),
                step("set_waypoint", kind="shop"),
                step("drive_route", duration=60),
                step("press", button="triangle", duration=1),
            ),
            150,
            (
                P("seated_within", seconds=20, step=0),
                P("game_back", step=1),
                P("waypoint_changed", step=1),
                P("arrived", metres=30, step=2),
                P("on_foot_at_end"),
            ),
            done_reasons=("route-gone", "arrived"),
            ends=(("foot", True), ("vehicle", False), ("route", False)),
        ),
    )
}


# ---- the reasons a skill can end on, and the part of the pilot each points at
# A rule is a prefix of the reason; the longest matching prefix wins. The values are the causes, or None
# where the reason says what happened but not whose fault it was (a time limit, a success): the log
# decides then. tests/test_bench.py scans the skills' code for reasons and fails on one no rule covers.
CAUSE_RULES: dict[str, str | None] = {
    # a reader had the picture wrong or nothing
    "map-unreadable": "see",
    "map unreadable": "see",
    "route-lost-far": "see",  # the route went from the map with the destination far away
    "route-lost-unknown": "see",
    "waiting to see a": "see",
    "minimap-unreadable": "see",
    "minimap unreadable": "see",
    "nothing found": "see",
    "detections lost after entry press": "see",
    "map-picture-missing-or-damaged": "see",
    "interactive-map-or-cursor-unverified": "see",
    "player-marker-unreadable": "see",
    "target-not-uniquely-trackable": "see",
    "target-tracking-unverified": "see",
    "map-texture-unverified": "see",
    "map-shift-unverified": "see",
    "sea-or-distance-unverified": "see",
    "target person lost": "see",
    "no person found": "see",
    "blip-gone": "see",
    "blip lost": "see",  # walk_to_point: the target went from the map far from the figure
    "no matching blip": "see",
    "blip-bearing-undefined": "see",
    "waypoint-unproven-on-a-later-page": "see",
    "return-unverified": "see",
    "map-check-failed:": "see",
    "no-visible-": "see",
    "place-not-in-legend:": "see",
    "picture-error:": "see",
    "view-unknown": "see",
    "no-figure": "see",
    "hud-unread": "see",
    "no-hud": "see",  # get_away: the stars cannot be read
    "menu-not-map; inspect the screen": "see",
    # the wrong target or skill, a plan replaced, a start nobody checked
    "interrupted": "decide",
    "replaced": "decide",
    "already in a vehicle": "decide",
    "not on foot": "decide",
    "not-on-foot": "decide",
    "rider": "decide",
    "wrong-screen-while-exiting": "decide",
    "wrong-screen:": "decide",
    "wrong-screen-during-input:": "decide",
    "start-screen-unverified": "decide",
    "existing-waypoint-at-target": "decide",
    "player is in a vehicle": "decide",
    "person already on the ground": "decide",
    "selection-changed-before-waypoint": "decide",
    "place-instance-not-present": "decide",
    "goal_": "decide",
    "not-built": "decide",  # a skill planned before its card was done
    "switch-refused": "decide",  # switch_character: planned with stars, an objective, or no map
    "switched:": None,  # switch_character's done: the game is back with another figure
    "wheel-unread": "see",  # switch_character: the wanted slot's highlight was not read; nothing switched
    "online-slot-seen": "see",  # switch_character: the lower slot read as highlighted; let go on a story slot
    "no-prompt": "decide",  # do_prompt, use_place: planned where the game offers nothing
    "refused:": "decide",  # do_prompt: the offer is one the pilot never takes (a bed, a purchase, Online)
    "no-effect": "act",  # do_prompt: the button went down and the help text stayed
    "pressed:": None,  # do_prompt's done: the offer was taken
    "used:": None,  # use_place's done: the place's menu was opened and left
    "menu-unread": "see",  # use_place: the rows or prices of the menu could not be read
    # seen and decided rightly and the movement did not do it
    "failed-recovery": "act",
    "blocked": "act",
    "stuck": "act",
    "in a building again and again": "act",  # walk_to_point: taken out three times, and in again
    "vehicle out of reach": "act",
    "door locked or blocked": "act",
    "entry press had no effect": "act",
    "could not reach it": "act",
    "gameplay returned without a waypoint": "act",
    "waypoint-not-visible-after-cross": "act",
    "cursor-did-not-approach-target": "act",
    "cursor-move-limit": "act",
    "map-unmoved-after-alternate": "act",
    "map-shift-wrong-direction": "act",
    "map-move-limit": "act",
    "melee-target-too-far": "act",
    "target-out-of-range": "act",
    "place-unread": "see",
    "legend-selection-did-not-move": "act",
    "legend-selection-skips-the-place": "act",
    "five-presses": "act",
    "map-did-not-open": "act",
    "menu-not-map": "act",
    "time-limit:": "act",  # the waypoint skills name the phase they were pressing in
    "still-in-lane": "act",
    "leaving lane": "act",
    "no-progress": "act",  # the car moved and the destination came no nearer
    "dead-or-held": "act",
    "vehicle-held": "act",  # get_away: the driver's recoveries are spent
    # the game came between
    "death_or_arrest": "world",
    "objective": "world",
    "low_health": "world",
    "stars": "world",
    "gameplay interrupted": "world",
    "no longer on foot": "world",  # walk_to_point: taken into a vehicle, or a screen without a map
    "health-depleted": "world",
    "health-still-low": "world",
    "health below 30%": "world",
    "screen-": "world",
    "on-foot": "world",  # get_away: no longer seated
    "water": "world",  # get_away: the arrow stands on water
    "guard-let-go": "world",  # the guard ended the skill it had started for a threat
    "pad_refused": "world",  # a hand on the controller: the bridge refused the pilot's pad
    # the bridge, the stream, gaps in the frames
    "clock-reversed": "tech",
    "clock-stalled": "tech",
    "clock-invalid": "tech",
    "invalid-clock": "tech",
    "invalid observation": "tech",
    "invalid-observation-time": "tech",
    "invalid-time": "tech",  # drive_to_blip: the clock of an observation was not a time
    "no-frame": "tech",
    "nothing readable for": "tech",  # walk_to_point: damaged or repeated pictures for seconds on end
    "no detections delivered at all": "tech",
    "no-detections": "tech",
    "picture-unchanged-after-input": "tech",
    "person detector unavailable or stale": "tech",
    "skill-error:": "tech",
    # what the reason alone does not say; the log decides (see `cause`)
    "time-limit": None,
    "route-back": None,
    "stars-lit": "world",
    "time limit": None,
    "route-gone": None,
    "arrived": None,
    "reached": None,  # drive_to_blip: stopped on the marker
    "entered": None,  # walk_to with enter: the figure is inside
    "outdoors": None,  # leave_building: the figure is outside and clear of the door
    "leaving building": None,
    "clearing doorway": None,
    "looking for entrance": None,
    "standing off the wall": None,
    "no-way-out": "act",  # leave_building: the remembered way, the model's door and the walls are spent
    "street": None,  # descend: the figure is down and clear of the foot of the stairs
    "descending stairs": None,
    "clearing stairs": None,
    "no-stairs": "act",  # descend: no view showed stairs and the landing's edges are spent
    "in-room": "decide",  # descend: called in a room; the building is left first
    "entered-room": "act",  # descend: the figure walked through a door instead of down
    "entered vehicle": None,
    "vehicle drove away or was lost": None,
    "levelled": None,
    "combat-timeout": None,
    "waypoint set": None,
    "limit": None,
    "punch time limit reached": None,
    "target person remained on the ground": None,
    "aligned": None,
    "no-red-blips": None,
    "far; presses": None,
    "road-side (map band; kerb unverified)": None,
    "delivered": None,
    "done": None,
}


def reason_rule(reason: str) -> tuple[bool, str | None]:
    """(known, cause): the longest rule that is a prefix of the reason."""
    text = (reason or "").strip()
    best = max((rule for rule in CAUSE_RULES if text.startswith(rule)), key=len, default=None)
    return (False, None) if best is None else (True, CAUSE_RULES[best])


# ---- the skill's own verdict
@dataclass(frozen=True)
class Verdict:
    ok: bool | None
    reason: str
    at: float | None = None


def reason_stem(reason: str) -> str:
    return reason.split(";", 1)[0].strip()


def skill_verdict(run: Try, cap: Capability) -> Verdict:
    """What the skill said at its end: the last done or failed of each skill the capability names, from
    the play log, the head's requests and the conductor's opening_failed rows. All done is done."""
    session = run.session
    last: dict[str, tuple[float, bool, str]] = {}

    def see(t: float, skill: dict) -> None:
        name = skill.get("name")
        if name in cap.skill_names and skill.get("status") in ("done", "failed"):
            if name not in last or t >= last[name][0]:
                last[name] = (t, skill["status"] == "done", str(skill.get("reason") or "done"))

    for row in session.play:
        see(row["t"], row.get("skill") or {})
    for request in session.requests:
        see(request["t"], request.get("last_skill") or {})
        for event in request.get("events", []):
            see(request["t"], event.get("skill") or {})
    for failure in session.opening_failures:
        if failure["t"] is not None:
            see(failure["t"], {"name": failure["name"], "status": "failed", "reason": failure["reason"]})
    if any(name not in last for name in cap.skill_names):
        return Verdict(None, "terminal skill result missing")
    failed = [item for item in last.values() if not item[1]]
    if failed:
        t, _, reason = min(failed)
        return Verdict(False, reason, t)
    t, _, reason = max(last.values())
    if cap.done_reasons and reason_stem(reason) not in cap.done_reasons:
        return Verdict(False, reason, t)
    return Verdict(True, reason, t)


def outcome(skill: bool | None, proof: bool | None) -> tuple[str, str | None]:
    """The table of the card: both yes is ok; one yes and one no is failed for a cause of `proof`; both no
    is failed and the cause is left to `cause`; anything not known is not counted."""
    if skill is None or proof is None:
        return "not_counted", None
    if skill and proof:
        return "ok", None
    return "failed", "proof" if skill != proof else None


# ---- the cause of a failure
def stale_seconds(session: Session) -> float:
    """The longest stretch of ticks whose frame was not fresh."""
    longest, start = 0.0, None
    for row in session.play:
        if row.get("fresh") is False:
            start = row["t"] if start is None else start
            longest = max(longest, row["t"] - start)
        else:
            start = None
    return longest


def world_evidence(session: Session, t0: float, t1: float) -> str | None:
    """What the game did in the stretch, where the logs show it: health falling, stars, a banner of a
    death, an arrest or a failed mission, an event of the conductor; the judge's answers count when three
    in a row agree."""
    huds = [(r["t"], r.get("hud") or {}) for r in session.requests if t0 <= r["t"] <= t1]
    health = [h["health"] for _, h in huds if isinstance(h.get("health"), (int, float))]
    for _, hud in huds:
        if hud.get("screen") in ("wasted", "busted", "failed"):
            return f"the HUD showed {hud['screen']}"
        if (hud.get("wanted") or 0) > 0:
            return "stars were lit"
    if any(b < a - 0.1 for a, b in itertools.pairwise(health)):
        return "health fell"
    for request in session.requests:
        if t0 <= request["t"] <= t1:
            for event in request.get("events", []):
                if event.get("kind") in ("death", "arrest", "wasted", "busted", "failure", "mission_ended"):
                    return f"the conductor reported {event['kind']}"
    for key, needed, text in (("banner", 2, "a banner was on the screen"), ("wanted", 3, "stars were lit")):
        run_length = 0
        for t, answers in session.judgments:
            if t0 <= t <= t1 and (answers.get(key) or {}).get("value") is True:
                run_length += 1
                if run_length >= needed:
                    return f"the judge saw it: {text}"
            else:
                run_length = 0
    return None


VEHICLE_KINDS = {"car", "truck", "bus", "motorcycle"}


def cause(reason: str, run: Try, cap: Capability, proof: Evidence) -> str:
    """The part of the pilot at fault, for a failure on which skill and proof agree it failed."""
    session = run.session
    window = proofs.Window(run.t0, session.end)
    if stale_seconds(session) >= 2.0 or any((r.get("status") or 200) >= 400 for r in session.play):
        return "tech"
    _known, mapped = reason_rule(reason)
    if mapped in ("tech", "see", "decide"):
        return mapped
    if world_evidence(session, window.t0, window.t1):
        return "world"
    if mapped:
        return mapped
    # A time limit and the reasons that say only how it ended: the log shows what was going on.
    numbers = proof.numbers
    requests = [r for r in session.requests if window.t0 <= r["t"] <= window.t1]
    entry = any(s["name"] == "enter_vehicle" for s in cap.plan)
    if entry and requests and all("objects" in r for r in requests):
        vehicles = [o for r in requests for o in r["objects"] if o.get("kind") in VEHICLE_KINDS]
        if not vehicles:
            return "see"  # no vehicle was ever detected
        return "act"  # a vehicle was in the picture and the figure did not get in
    distances = [d for _, d in proofs._distances(run, window.t0, window.t1)]
    if len(distances) > 1:
        return (
            "act" if min(distances) < distances[0] - 1 else "decide"
        )  # approached and not there / never moved
    if cap.id.startswith("map.") and (numbers.get("waypoint_changed") or {}).get("blip_after_share") == 0.0:
        return "act"  # the map was handled and no waypoint came out of it
    return "unclear"


LOOK_FIRST = {
    "see": (
        "compare what the readers logged at that second with the picture: minimap class, blips, "
        "detections and the judge's answers"
    ),
    "decide": (
        "read what the head or the plan asked for at that second and why the skill was replaced or refused"
    ),
    "act": (
        "watch the video from a few seconds before: the pad was sent, then see what the figure or the "
        "cursor did"
    ),
    "proof": (
        "skill and proof disagree: look at the picture at that second to see which of the two was right, "
        "then mark the try"
    ),
    "world": "something in the game came between (stars, health, a banner): look at the HUD at that second",
    "tech": "the bridge or the stream: look for stale frames and errors in the play log around that second",
    "unclear": "the log does not say whose fault it was: look at the picture and mark the try with a cause",
}


def failure_moment(row: dict, run: Try, cap: Capability, proof: Evidence, verdict: Verdict) -> dict | None:
    """The second of the session where a failure went wrong, and how it was found: the failing piece's own
    moment; where the proof says it happened and the skill failed, the second from which it held; else
    the second the skill said it failed."""
    if row["outcome"] != "failed":
        return None
    if proof.moment is not None and proof.ok is False:
        t, how = proof.moment
        return {"t": round(float(t), 2), "how": f"proof: {how}"}
    if proof.ok:
        for name, _params in cap.proof:
            if name in proofs.SINCE:
                found = proofs.SINCE[name](run)
                if found:
                    return {"t": round(float(found[0]), 2), "how": f"proof: {found[1]}"}
    if verdict.at is not None:
        return {"t": round(float(verdict.at), 2), "how": "the second the skill ended and said it failed"}
    return {
        "t": round(float(run.session.end), 2),
        "how": "the end of the session; nothing narrower is in the log",
    }


# ---- version, judging, the ledger
def version() -> dict:
    """The commit and whether the code of the pilot is dirty; the tree's own bench output is not code."""

    def git(*args: str) -> str:
        return subprocess.check_output(
            ["git", "-C", str(REPO), *args], text=True, stderr=subprocess.DEVNULL
        ).strip()

    try:
        return {
            "commit": git("rev-parse", "HEAD"),
            "dirty": bool(git("status", "--porcelain", "--", "pilot/src")),
        }
    except (OSError, subprocess.CalledProcessError):
        return {"commit": "unknown", "dirty": None}


def judge(
    folder: Path,
    capability: str,
    *,
    code: dict | None = None,
    session: Session | None = None,
    started: str | None = None,
) -> dict:
    """One ledger row for the session in `folder` as a try of `capability`."""
    cap = CATALOGUE[capability]
    own = session is None
    session = session or Session(folder)
    try:
        run = Try(session, cap.skill_names, cap.plan_names)
        start = state_of(session)
        held = meets(start, cap.start)
        verdict = skill_verdict(run, cap)
        proof = proofs.run_pieces(run, cap.proof)
        status, why = outcome(verdict.ok, proof.ok)
        exclusion = ""
        if not cap.built:
            status, why, exclusion = "not_counted", None, "not built"
        elif not session.play:
            status, why, exclusion = "not_counted", None, "no ticks in play.jsonl"
        elif not held:
            unclear = [name for name in cap.start if start.get(name) is None]
            status, why = "not_counted", None
            exclusion = "start state not established: " + ", ".join(
                f"{name} {'unclear' if start.get(name) is None else 'no'}"
                for name in cap.start
                if start.get(name) is not True
            )
            if unclear and len(unclear) == len([n for n in cap.start if start.get(n) is not True]):
                exclusion += " (the class of the minimap and the judge do not agree, or the stretch is thin)"
        elif verdict.ok is None or proof.ok is None:
            exclusion = proof.missing or "terminal skill result missing: cli/head logger"
        if status == "failed" and why is None:
            why = cause(verdict.reason, run, cap, proof)
        elif status == "failed" and why == "proof" and not verdict.ok:
            # The skill failed and the proof says it happened. When the skill's own reason is a reading
            # that failed, the pilot did not see what was there: that is `see`, not a wrong proof.
            if reason_rule(verdict.reason)[1] == "see":
                why = "see"
        stamp = datetime.now(UTC).isoformat()
        meta_path = Path(folder) / "meta.json"
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        row = {
            "capability": capability,
            "time": started or meta.get("started", stamp),
            "judged_at": stamp,
            **(code or {"commit": "unknown", "dirty": None}),
            "judged_with": version(),
            "session": str(Path(folder).resolve()),
            "start_state": {"held": held, "observed": start},
            "outcome": status,
            "cause": why,
            "skill_reason": verdict.reason,
            "skill_ok": verdict.ok,
            "seconds": round(session.end - session.start, 3) if session.play else 0,
            "proof": {
                "ok": proof.ok,
                "numbers": as_numbers(proof.numbers),
                "missing": proof.missing if proof.ok is None else "",
                "parts": dict(proof.parts),
                # every piece that could be measured held, and one could not: a success nobody can certify
                "partial": proof.ok is None and any(ok for _, ok in proof.parts),
            },
            "objective": objective_on_screen(session),
            "exclusion": exclusion,
        }
        row["moment"] = failure_moment(row, run, cap, proof, verdict)
        return row
    finally:
        if own:
            session.close()


def append(path: Path, row: dict) -> None:
    """The one way into a ledger: a line at the end. Nothing is ever rewritten."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")


def marks_path(ledger: Path) -> Path:
    return ledger.with_name(ledger.stem + ".marks.jsonl")


def apply_marks(rows: list[dict], marks: list[dict]) -> list[dict]:
    """The rows as the board counts them: the latest judgement of each try, then the reviewer's marks.
    A rejudged session appends a row; only the newest of a (session, capability, event) is counted."""
    latest = {}
    for row in rows:
        latest[(row["session"], row["capability"], row.get("event_start"))] = row
    result = []
    for original in latest.values():
        row = dict(original)
        for mark in marks:
            if mark["session"] == row["session"] and (
                not mark.get("capability") or mark["capability"] == row["capability"]
            ):
                row.update(outcome=mark["outcome"], cause=mark["cause"], marked=True, mark_note=mark["note"])
        result.append(row)
    return result


IMPORT_STEPS = {
    "leave": "car.leave",
    "walk": "foot.walk",
    "enter": "foot.enter",
    "place": "map.place",
    "waypoint": "map.place",
    "drive": "car.follow",
    "view": "foot.view",
}


def import_basics(source: Path, ledger: Path, *, harvest_too: bool = True) -> list[dict]:
    """Take over the tries a list names (cycle, step, folder per line, as lab/live/basics.sh writes it).
    A session already in the ledger for a capability is not imported twice."""
    seen = {(r["session"], r["capability"]) for r in read_jsonl(ledger)}
    added = []
    for line in source.read_text().splitlines():
        fields = line.split("\t")
        if len(fields) < 3 or fields[1] not in IMPORT_STEPS:
            continue
        folder = Path(fields[2])
        if not folder.is_absolute():
            folder = source.parent / folder
        capability = IMPORT_STEPS[fields[1]]
        if (str(folder.resolve()), capability) in seen:
            continue
        row = judge(folder, capability)
        row["source"] = {"file": str(source), "cycle": fields[0], "step": fields[1]}
        append(ledger, row)
        added.append(row)
        seen.add((row["session"], capability))
    if harvest_too:
        for session in dict.fromkeys(r["session"] for r in added):
            for incident in harvest(Path(session)):
                if (incident["session"], incident["capability"], incident["event_start"]) not in {
                    (r["session"], r["capability"], r.get("event_start")) for r in read_jsonl(ledger)
                }:
                    append(ledger, incident)
    return added


def rejudge(ledger: Path) -> int:
    """Judge every try of the ledger again with the proofs as they are now and append the rows: the
    board counts the newest row of each try, so a repaired proof shows without a line being changed."""
    count = 0
    for key in dict.fromkeys(
        (r["session"], r["capability"]) for r in read_jsonl(ledger) if r.get("event_start") is None
    ):
        session, capability = key
        if not Path(session).is_dir() or capability not in CATALOGUE:
            continue
        old = next(
            r
            for r in reversed(read_jsonl(ledger))
            if (r["session"], r["capability"]) == key and r.get("event_start") is None
        )
        row = judge(
            Path(session),
            capability,
            code={"commit": old.get("commit", "unknown"), "dirty": old.get("dirty")},
            started=old.get("time"),
        )
        row["source"] = old.get("source", {})
        row["revision"] = True
        append(ledger, row)
        count += 1
    return count


def harvest(folder: Path, *, code: dict | None = None) -> list[dict]:
    """Moments in a session that are tries of the capabilities that cannot be staged: a menu opened, a
    death, stars, a vehicle held. Each is kept with its own event second. They are never counted today:
    the logs hold no result of the reflex or the escape to set against the proof."""
    session = Session(folder)
    try:
        events: list[tuple[str, float, int]] = []
        previous: dict = {}
        requests = session.requests
        for index, request in enumerate(requests):
            hud = request.get("hud") or {}
            screen = hud.get("screen")
            if screen in ("pause", "map", "menu") and previous.get("screen") == "game":
                if (request.get("last_skill") or {}).get("name") != "set_waypoint":
                    events.append(("incident.menu", request["t"], index))
            if screen in ("wasted", "busted") and previous.get("screen") not in ("wasted", "busted"):
                events.append(("incident.down", request["t"], index))
            if (hud.get("wanted") or 0) > 0 and previous.get("wanted") == 0:
                events.append(("incident.wanted", request["t"], index))
            previous = hud
        records = []
        for capability, onset, index in events:
            deadline = onset + CATALOGUE[capability].seconds
            tail = [r for r in requests[index + 1 :] if r["t"] <= deadline]
            resolved = None
            if capability == "incident.menu":
                resolved = next((r["t"] for r in tail if (r.get("hud") or {}).get("screen") == "game"), None)
            elif capability == "incident.wanted":
                resolved = next((r["t"] for r in tail if (r.get("hud") or {}).get("wanted") == 0), None)
            records.append(
                {
                    "capability": capability,
                    "time": datetime.now(UTC).isoformat(),
                    **(code or {"commit": "unknown", "dirty": None}),
                    "session": str(Path(folder).resolve()),
                    "event_start": onset,
                    "start_state": {"held": True, "observed": {"harvested": True}},
                    "outcome": "not_counted",
                    "cause": None,
                    "skill_reason": "recovery handler terminal result missing",
                    "skill_ok": None,
                    "seconds": round((resolved or min(deadline, session.end)) - onset, 3),
                    "proof": {
                        "ok": None,
                        "numbers": {"onset": onset, "resolved": resolved},
                        "missing": CATALOGUE[capability].unmeasured()[0],
                    },
                    "objective": {"on_screen": None, "text": ""},
                    "exclusion": "recovery handler result and attempt id missing: conductor play/head logger",
                    "moment": None,
                }
            )
        return records
    finally:
        session.close()


# ---- the board
def board_data(rows: list[dict]) -> dict:
    capabilities = []
    ranking: Counter = Counter()
    by_commit: dict = defaultdict(list)
    failures = [r for r in rows if r["outcome"] == "failed"]
    for cap in CATALOGUE.values():
        selected = [r for r in rows if r["capability"] == cap.id]
        counted = [r for r in selected if r["outcome"] != "not_counted"]
        recent = counted[-10:]
        failed = [r for r in counted if r["outcome"] == "failed"]
        wins = sum(r["outcome"] == "ok" for r in recent)
        unmeasured = cap.unmeasured()
        silent = bool(selected) and all(r["proof"].get("ok") is None for r in selected)
        reason = next((r["proof"]["missing"] for r in reversed(selected) if r["proof"].get("missing")), "")
        if not cap.built:
            label, why = "not built", unmeasured[0] if unmeasured else ""
        elif unmeasured or silent:
            label, why = "not measurable", (unmeasured[0] if unmeasured else reason)
        elif len(recent) < 10:
            label, why = "too few tries", ""
        else:
            label, why = ("green" if wins >= cap.mark else "red"), ""
        capabilities.append(
            {
                "id": cap.id,
                "title": cap.title,
                "german": cap.german,
                "state": label,
                "reason": why,
                "last10": [wins, len(recent)],
                "all": [sum(r["outcome"] == "ok" for r in counted), len(counted)],
                "excluded": len(selected) - len(counted),
                "unverified": sum(
                    r["outcome"] == "not_counted"
                    and r["proof"].get("partial")
                    and r.get("skill_ok") is True
                    and r["start_state"].get("held")
                    for r in selected
                ),
                "silent_failures": sum(
                    r["outcome"] == "not_counted"
                    and r.get("skill_ok") is False
                    and r["proof"].get("ok") is None
                    and r["start_state"].get("held")
                    for r in selected
                ),
                "median_seconds": round(statistics.median(r["seconds"] for r in counted), 3)
                if counted
                else None,
                "causes": dict(Counter(r["cause"] for r in failed)),
                "top_reasons": Counter(reason_stem(r["skill_reason"]) for r in failed).most_common(3),
                "newest_failures": [r["session"] for r in failed[-3:][::-1]],
                "marked": sum(bool(r.get("marked")) for r in selected),
            }
        )
        for row in failed:
            ranking[(cap.id, row["cause"], reason_stem(row["skill_reason"]))] += 1
        for row in counted:
            by_commit[(cap.id, row["commit"], row["dirty"])].append(row)
    return {
        "capabilities": capabilities,
        "ranking": [
            {"capability": key[0], "cause": key[1], "reason": key[2], "count": count}
            for key, count in sorted(ranking.items(), key=lambda pair: (-pair[1], str(pair[0])))
        ],
        "commits": [
            {
                "capability": key[0],
                "commit": key[1],
                "dirty": key[2],
                "ok": sum(r["outcome"] == "ok" for r in value),
                "counted": len(value),
            }
            for key, value in by_commit.items()
        ],
        "exclusions": [
            {"capability": key[0], "why": key[1], "count": count}
            for key, count in sorted(
                Counter(
                    (r["capability"], r.get("exclusion") or "the proof could not say")
                    for r in rows
                    if r["outcome"] == "not_counted"
                ).items(),
                key=lambda pair: (-pair[1], pair[0]),
            )
        ],
        "unclear": sum(r["cause"] == "unclear" for r in failures),
        "failures": len(failures),
        "total": len(rows),
        "counted": sum(r["outcome"] != "not_counted" for r in rows),
        "not_counted": sum(r["outcome"] == "not_counted" for r in rows),
    }


def sheet(folder: Path, output: Path) -> Path | None:
    """Four frames of a session, the last decodable frame among them, as one JPEG beside the ledger."""
    import hashlib

    import cv2
    import numpy as np

    video = Path(folder) / "video.mp4"
    if not video.exists():
        return None
    target = output / (hashlib.sha256(str(folder).encode()).hexdigest()[:16] + ".jpg")
    if target.exists():
        return target
    capture = cv2.VideoCapture(str(video))
    try:
        count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if count < 4:
            return None
        tiles = []
        for index in sorted({0, (count - 1) // 3, 2 * (count - 1) // 3, count - 1}):
            tile = None
            for back in range(0, 8):  # the last frames of a video are sometimes not decodable
                capture.set(cv2.CAP_PROP_POS_FRAMES, max(index - back, 0))
                ok, frame = capture.read()
                if ok:
                    tile = cv2.resize(frame, (320, 180), interpolation=cv2.INTER_AREA)
                    break
            tiles.append(tile if tile is not None else np.zeros((180, 320, 3), np.uint8))
        while len(tiles) < 4:
            tiles.append(tiles[-1])
        grid = np.vstack([np.hstack(tiles[:2]), np.hstack(tiles[2:4])])
        output.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(target), grid, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return target
    finally:
        capture.release()


def board_markdown(data: dict) -> str:
    share = f"{data['unclear'] / data['failures']:.1%}" if data["failures"] else "undefined"
    lines = [
        "# Capability bench",
        "",
        f"{data['total']} tries, {data['counted']} counted, {data['not_counted']} not counted; "
        f"{data['failures']} counted failures, of which {data['unclear']} unclear ({share}).",
        "",
        "A try is not counted where the start state did not hold or where the proof cannot say. Code "
        "versions of tries judged from old logs are unknown. `unverified` counts tries whose skill said "
        "done and whose proof could not be measured; `failed, proof silent` counts tries whose skill said "
        "failed and whose proof could not say (a waypoint that stands where it stood before, for one), "
        "which are not counted but are not successes either.",
        "",
        "| Capability | State | Last ten | All | Median s | Not counted | Unverified | Failed, proof silent "
        "| Causes | Reasons |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for cap in data["capabilities"]:
        lines.append(
            f"| {cap['id']} ({cap['german']}) | {cap['state']} | {cap['last10'][0]}/{cap['last10'][1]} | "
            f"{cap['all'][0]}/{cap['all'][1]} | {cap['median_seconds']} | {cap['excluded']} | "
            f"{cap['unverified']} | {cap['silent_failures']} | "
            f"{', '.join(f'{k} {v}' for k, v in cap['causes'].items()) or '-'} | "
            f"{'; '.join(f'{r} ({n})' for r, n in cap['top_reasons']).replace('|', '/') or '-'} |"
        )
    lines += ["", "## Why a capability is not measurable, and what its rate leaves out", ""]
    for cap in data["capabilities"]:
        if cap["reason"]:
            lines.append(f"- {cap['id']}: {cap['reason']}")
        elif cap["unverified"] or cap["silent_failures"]:
            lines.append(
                f"- {cap['id']}: the proof could not confirm {cap['unverified']} tries the skill called done "
                f"and {cap['silent_failures']} it called failed; they are in no rate"
            )
    lines += ["", "## Newest failures", ""]
    for cap in data["capabilities"]:
        if cap["newest_failures"]:
            lines.append(f"- {cap['id']}: {', '.join(cap['newest_failures'])}")
    lines += [
        "",
        "## What to repair next",
        "",
        "| Capability | Cause | Reason | Count |",
        "| --- | --- | --- | --- |",
    ]
    for rank in data["ranking"]:
        lines.append(
            f"| {rank['capability']} | {rank['cause']} | "
            f"{rank['reason'].replace('|', '/')} | {rank['count']} |"
        )
    lines += ["", "## Why tries were not counted", "", "| Capability | Why | Tries |", "| --- | --- | --- |"]
    for item in data["exclusions"]:
        lines.append(f"| {item['capability']} | {item['why'].replace('|', '/')} | {item['count']} |")
    lines += ["", "## Rates by commit", ""]
    for commit in data["commits"]:
        lines.append(
            f"- {commit['capability']}: {str(commit['commit'])[:10]} (dirty {commit['dirty']}): "
            f"{commit['ok']}/{commit['counted']}"
        )
    return "\n".join(lines) + "\n"


def write_board(ledger: Path, *, sheets: bool = True, echo: bool = True) -> dict:
    rows = apply_marks(read_jsonl(ledger), read_jsonl(marks_path(ledger)))
    data = board_data(rows)
    markdown = board_markdown(data)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.with_suffix(".md").write_text(markdown)
    head = (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width">'
        "<title>Capability bench</title><style>"
        "body{font:15px system-ui;background:#111821;color:#e4eaf0;margin:2rem;max-width:1400px}"
        "table{border-collapse:collapse;width:100%}"
        "td,th{padding:.6rem;border-bottom:1px solid #344252;text-align:left;vertical-align:top}"
        "pre{white-space:pre-wrap;overflow-wrap:anywhere}.green{color:#78db93}.red{color:#ff8b87}"
        "img{max-width:640px;width:100%}article{border-top:1px solid #344252;margin-top:2rem}"
        "small{display:block;color:#adbace}</style><h1>Capability bench</h1>"
    )
    page = [head, f"<p>{html.escape(markdown.splitlines()[2])}</p>"]
    page.append(
        "<table><tr><th>Capability</th><th>State</th><th>Last ten / all</th><th>Median s</th>"
        "<th>Failures</th></tr>"
    )
    for cap in data["capabilities"]:
        page.append(
            f"<tr><td>{html.escape(cap['id'])}<small>{html.escape(cap['german'])}</small></td>"
            f"<td class='{cap['state'].replace(' ', '-')}'>{cap['state']}"
            f"<small>{html.escape(cap['reason'])}</small></td>"
            f"<td>{cap['last10'][0]}/{cap['last10'][1]} / {cap['all'][0]}/{cap['all'][1]}<small>not counted "
            f"{cap['excluded']}; unverified {cap['unverified']}; failed, proof silent "
            f"{cap['silent_failures']}; marked {cap['marked']}</small></td>"
            f"<td>{cap['median_seconds']}</td><td>{html.escape(str(cap['causes']))}"
            f"<small>{html.escape(str(cap['top_reasons']))}</small></td></tr>"
        )
    page.append("</table><h2>What to repair next, and rates by commit</h2><pre>")
    page.append(html.escape(markdown[markdown.index("## What to repair next") :]))
    page.append("</pre><h2>Failures</h2>")
    cache: dict = {}
    for row in rows:
        if row["outcome"] != "failed":
            continue
        folder = row["session"]
        if folder not in cache:
            made = sheet(Path(folder), ledger.parent / "frames") if sheets else None
            cache[folder] = made.read_bytes() if made else None
        page.append(
            f"<article><h3>{html.escape(row['capability'])}: {html.escape(str(row['cause']))}</h3>"
            f"<p>{html.escape(folder)}</p><p>{html.escape(row['skill_reason'])}</p>"
        )
        if row.get("moment"):
            page.append(f"<p>Went wrong at {row['moment']['t']} s: {html.escape(row['moment']['how'])}</p>")
        page.append(f"<pre>{html.escape(json.dumps(row['proof'], ensure_ascii=False, indent=1))}</pre>")
        if row.get("marked"):
            page.append(f"<p>Marked: {html.escape(row['mark_note'])}</p>")
        if cache[folder]:
            import base64

            page.append(
                '<img alt="four frames of the session, the last one last" '
                f'src="data:image/jpeg;base64,{base64.b64encode(cache[folder]).decode()}">'
            )
        else:
            page.append("<p>No frames: the video is missing or could not be read.</p>")
        page.append("</article>")
    page.append("</html>")
    ledger.with_suffix(".html").write_text("\n".join(page))
    if echo:
        print(markdown)
    return data


# ---- the command line
def catalogue_text() -> str:
    lines = []
    for cap in CATALOGUE.values():
        state = (
            "not built"
            if not cap.built
            else "harvested"
            if cap.harvested
            else "opening"
            if cap.opening
            else "plan"
        )
        lines.append(
            f"{cap.id} ({cap.german}; {state}; start {', '.join(cap.start) or 'any'}; {cap.seconds} s)"
        )
        lines.append(f"    proof: {cap.describe_proof()}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("judge", help="judge a session that exists as a try of one capability")
    command.add_argument("session", type=Path)
    command.add_argument("--capability", choices=CATALOGUE, required=True)
    command = commands.add_parser("import", help="take over the tries of a basics.sh list")
    command.add_argument("source", type=Path)
    commands.add_parser("rejudge", help="judge every try of the ledger again with the proofs as they are")
    command = commands.add_parser("mark", help="overrule a line; written beside the ledger")
    command.add_argument("session", type=Path)
    command.add_argument("--capability", choices=CATALOGUE)
    command.add_argument("--outcome", choices=OUTCOMES, required=True)
    command.add_argument("--cause", choices=CAUSES)
    command.add_argument("--note", required=True)
    command = commands.add_parser("run", help="try capabilities in a loop; `all` goes through the catalogue")
    command.add_argument("capabilities", nargs="+", help="ids, or `all`")
    command.add_argument("--tries", type=int, default=10, help="tries per capability")
    command.add_argument("--minutes", type=float, default=None, help="stop when this many minutes are used")
    command.add_argument(
        "--guard-mission", action="store_true", help="do not run while an objective is on the screen"
    )
    command.add_argument("--dry", action="store_true", help="print what the loop would do and touch nothing")
    command.add_argument(
        "--assume", choices=("foot", "vehicle"), default="foot", help="--dry: the state the first probe finds"
    )
    command.add_argument(
        "--judge", default=None, help="URL=MODEL of the judge server (default: the one basics.sh uses)"
    )
    command.add_argument(
        "--record-dir",
        type=Path,
        default=None,
        help="where the sessions go (default: ~/recordings/pilot, where basics.sh puts them)",
    )
    command = commands.add_parser("board", help="print and write the board")
    command.add_argument("--no-sheets", action="store_true")
    commands.add_parser("catalogue", help="print the catalogue with every proof")
    args = parser.parse_args(argv)
    if args.command == "catalogue":
        print(catalogue_text())
    elif args.command == "judge":
        row = judge(args.session, args.capability)
        append(args.ledger, row)
        print(json.dumps(row, indent=2, ensure_ascii=False))
    elif args.command == "import":
        rows = import_basics(args.source, args.ledger)
        print(f"Imported {len(rows)} tries.")
    elif args.command == "rejudge":
        print(f"Judged {rejudge(args.ledger)} tries again.")
    elif args.command == "mark":
        if args.outcome == "failed" and args.cause is None:
            parser.error("a failed mark needs --cause")
        if not args.note.strip():
            parser.error("a mark needs a note")
        append(
            marks_path(args.ledger),
            {
                "time": datetime.now(UTC).isoformat(),
                "session": str(args.session.resolve()),
                "capability": args.capability,
                "outcome": args.outcome,
                "cause": args.cause,
                "note": args.note,
            },
        )
    elif args.command == "run":
        from . import bench_run

        return bench_run.main_run(args)
    else:
        write_board(args.ledger, sheets=not args.no_sheets)
    return 0


if __name__ == "__main__":
    sys.exit(main())
