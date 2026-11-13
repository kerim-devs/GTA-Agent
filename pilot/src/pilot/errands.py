"""Bounded, observation-driven errands and their session selection policy."""

import copy
import random
import re
import secrets
import time
from collections import Counter
from dataclasses import dataclass, field

from . import memory
from .head import parse_response

# Relative chances; cooldowns and exclusions are applied before the seeded draw.
ERRANDS = {
    "story": 5,  # Prefer progressing the story at a mission letter.
    "shop": 3,  # Visit an enterable service and return outside.
    "mayhem": 2,  # Punch a street pedestrian and escape the consequences.
    "cruise": 1,  # Drive to a distant point for a change of scenery.
    "home": 1,  # Visit the safehouse wardrobe without saving.
}
TITLES = {
    "story": "zur nächsten Mission",
    "shop": "ein Geschäft besuchen",
    "mayhem": "auf der Straße Ärger machen und entkommen",
    "cruise": "eine Runde fahren",
    "home": "zu Hause die Kleidung wechseln",
    "escape": "der Polizei entkommen",
}
DESCRIPTIONS = {
    "story": "Reach a mission letter and wait for a mission to begin.",
    "shop": "Visit a barber, clothes shop, gun shop or tattoo studio and leave.",
    "mayhem": "Punch a street pedestrian, then escape.",
    "cruise": "Travel to a distant waypoint.",
    "home": "Change clothes at the safehouse wardrobe, never use a bed or save.",
}
SHOPS = (
    "Friseursalon",
    "Binco Bekleidung",
    "Discount Store",
    "Suburban",
    "Ponsonbys",
    "Ammu-Nation",
    "Tattoo-Studio",
)
# Total seconds and maximum issued steps, including recovery attempts.
LIMITS = {
    "story": (420, 24),
    "shop": (480, 24),
    "home": (480, 24),
    "mayhem": (120, 8),
    "cruise": (300, 18),
    "escape": (180, 12),
}
WAYPOINT = re.compile(r"^waypoint set: (.+?) \((?:(\d+(?:\.\d+)?)m|distance not read)\)")


def call(name, **args):
    return {"name": name, "args": args}


def exit_car():
    return [call("press", button="triangle", duration=0.1), call("wait", duration=2)]


@dataclass
class Errand:
    name: str
    started: float
    seed: int
    direction: str
    attempts: int = 0
    step: str = "waypoint"
    place: str | None = None
    distance: float | None = None
    last_result: dict | None = None
    target: dict = field(default_factory=dict)
    stalls: int = 0
    unreadable: int = 0
    exits: int = 0
    left_at: float | None = None
    resume: str = "travel"
    wait_since: float | None = None
    used: bool = False
    arrived: bool = False
    seen_wanted: bool = False
    seen_route: bool = False

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


class Errands:
    STATE = (
        "active",
        "abandoned",
        "history",
        "transition",
        "last_name",
        "cooldowns",
        "shop_times",
        "abandonments",
        "story_instance",
        "story_failures",
        "story_dampened",
        "switch_due",
        "known",
        "learned",
        "next",
    )

    def __init__(self, seed=None, clock=time.monotonic, chooser=None):
        self.seed = secrets.randbits(32) if seed is None else seed
        self.random = random.Random(self.seed)
        self.clock, self.chooser = clock, chooser
        self._noted = None  # the errand whose end the memory was last told of; not undone with the rest
        self.active = None
        self.abandoned = None
        self.history = []
        self.transition = ""
        self.last_name = None
        self.cooldowns = {}
        self.shop_times = {}
        self.abandonments = Counter()
        self.story_instance = 0
        self.story_failures = 0
        self.story_dampened = False
        self.switch_due = False
        self.known = {}
        self.learned = None
        self.next = None
        self._undo = None

    def mark(self):
        # History entries are append-only; snapshotting their count keeps decision
        # cost independent of how long this session has been running.
        self._undo = (
            copy.deepcopy({k: getattr(self, k) for k in self.STATE if k != "history"}),
            self.random.getstate(),
            len(self.history),
        )

    def undo(self):
        if self._undo is not None:
            state, rng, history_length = self._undo
            for key, value in state.items():
                setattr(self, key, value)
            del self.history[history_length:]
            self.random.setstate(rng)
            self._undo = None

    def now(self, request):
        return self.clock() if request.time is None else request.time

    @staticmethod
    def _kept():
        """The memory of earlier sessions, where this one was given a file for it (memory.use)."""
        kept = memory.active()
        return kept if kept.path is not None else None

    def _recent(self, section, name, seconds):
        """Whether an earlier session, or this one, noted the entry less than `seconds` ago."""
        kept = self._kept()
        age = None if kept is None else kept.since(section, name)
        return age is not None and age < seconds

    def shops(self, now):
        kept = self._kept()
        return [
            p
            for p in SHOPS
            if now - self.shop_times.get(p, -float("inf")) >= 1800
            and self.abandonments[p] < 2
            # Across sessions as within one: not the shop the figure was in half an hour ago, and not
            # one the way to which was given up twice running within the hour.
            and not self._recent(memory.PLACES, p, 1800)
            and not (kept is not None and memory.place_avoided(kept, p))
        ]

    def choose(self, request):
        now = self.now(request)
        candidates = [n for n in ERRANDS if n == "story" or n != self.last_name]
        if not self.shops(now):
            candidates.remove("shop") if "shop" in candidates else None
        if (
            now - self.cooldowns.get("home", -float("inf")) < 3600
            or self.abandonments["Unterschlupf"] >= 2
            or self._recent(memory.ERRANDS, "home", 3600)
        ):
            candidates.remove("home") if "home" in candidates else None
        if (
            now - self.cooldowns.get("mayhem", -float("inf")) <= 600
            or self.last_name == "escape"
            or self._recent(memory.ERRANDS, "mayhem", 600)
        ):
            candidates.remove("mayhem") if "mayhem" in candidates else None
        weights = [ERRANDS[n] * (0.5 if n == "story" and self.story_dampened else 1) for n in candidates]
        offers = [
            {"name": name, "weight": weight, "description": DESCRIPTIONS[name]}
            for name, weight in zip(candidates, weights, strict=True)
        ]
        selected = self.chooser(offers) if self.chooser else None
        return (
            selected if selected in candidates else self.random.choices(candidates, weights=weights, k=1)[0]
        )

    def _start(self, request, mode=None, cars=None, wanted=None):
        name = "escape" if wanted else self.choose(request)
        goal = Errand(
            name, self.now(request), self.seed, self.random.choice(("north", "east", "south", "west"))
        )
        if name == "story":
            goal.target = {"target": "mission", "instance": self.story_instance}
            if self.switch_due:
                goal.step = "switch"
                self.switch_due = False
        elif name == "shop":
            goal.place = self.random.choice(self.shops(goal.started))
            self.shop_times[goal.place] = goal.started
            goal.target = {"place": goal.place}
        elif name == "home":
            goal.place = "Unterschlupf"
            goal.target = {"place": goal.place}
        elif name == "cruise":
            goal.target = {"target": "away", "direction": goal.direction, "distance": "far"}
        else:
            goal.step = "punch" if name == "mayhem" else "escape"
        goal.seen_wanted = bool(wanted)
        self.cooldowns[name] = goal.started
        self.active = goal
        self.history.append(
            {
                **goal.data(),
                "time": goal.started,
                "outcome": "started",
                "reason": self.transition or "weighted selection",
            }
        )
        return goal

    def _keep(self, goal, reached, reason):
        """Note the errand's end for later sessions, once: a decision the conductor drops is made again."""
        kept = self._kept()
        key = (goal.name, goal.started)
        if kept is None or key == self._noted:
            return
        self._noted = key
        memory.errand_done(kept, goal.name, reached=reached)
        if goal.place:
            if reached:
                memory.place_reached(kept, goal.place, how=goal.name)
            else:
                memory.place_failed(kept, goal.place, why=str(reason)[:80])

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
        self._keep(goal, reached, reason)
        self.last_name = "escape" if goal.name == "mayhem" and goal.step == "escape" else goal.name
        self.abandoned = None if reached else goal.name
        if not reached and goal.place:
            self.abandonments[goal.place] += 1
        if goal.name == "story":
            if reached:
                self.story_dampened = False
                self.story_failures = 0
            else:
                self.story_instance = (self.story_instance + 1) % 101
            if not reached and reason == "letter did not start a mission":
                self.story_failures += 1
                self.story_dampened = True
                if self.story_failures % 2 == 0:
                    self.switch_due = True
        self.active = None

    def guard(self, request):
        from .goals import interruption

        goal = self.active
        reason = interruption(request, goal.data() if goal else None)
        if (
            reason == "stars"
            and goal
            and goal.name == "mayhem"
            and (goal.step == "escape" or (request.last_skill or {}).get("name") == "punch")
        ):
            reason = None
        screen = (request.hud or {}).get("screen")
        cutscene = screen == "cutscene" or any(
            e.get("kind") == "screen" and e.get("screen") == "cutscene" for e in request.events
        )
        last = request.last_skill or {}
        arrived = goal and (
            goal.arrived
            or (
                goal.step == "approach"
                and last.get("name") == "walk_to_point"
                and last.get("status") == "done"
                and str(last.get("reason") or "").startswith("arrived")
            )
        )
        if goal and goal.name == "story" and arrived and (reason == "objective" or cutscene):
            self.end(request, "mission observed after arrival", reached=True)
            return "objective"
        if reason and goal:
            self.end(request, reason)
        return reason

    def learn(self, last):
        from .goals import read_places
        from .legend import kind_of

        if last and last.get("name") == "set_waypoint":
            self.learned = dict(last)
            self.known.update({name: kind_of(name) for name in read_places(last.get("reason")) or []})

    def trip(self, goal=None, *, follow=120):
        target = goal.target if goal else {"target": "away", "direction": "any", "distance": "far"}
        return [call("set_waypoint", duration=45, **target)]

    def _reply(self, goal, plan, action="replace", reason=""):
        title = goal.place or TITLES[goal.name]
        if goal.distance is not None:
            title += f", {goal.distance:g} m entfernt"
        return parse_response(
            {
                "plan": plan,
                "action": action,
                "sentence": f"Mein Ziel: {title}.",
                "goal": goal.data(),
                "step": goal.step,
                "reason": reason or self.transition or "observed errand step",
            }
        )

    def decide(self, request, mode, *, escape_plan=None, recovery_plan=None, keep_heading=False):
        from .goals import HELD, STALLED, fits, leave_vehicle, occupancy, own_stop

        now = self.now(request)
        wanted = (request.hud or {}).get("wanted")
        if wanted is None:
            wanted = next(
                (e.get("wanted") for e in reversed(request.events) if e.get("kind") == "wanted_changed"), None
            )
        seat = occupancy(mode, request.events)
        cars = any(o.get("kind") in {"car", "truck", "motorcycle"} for o in request.objects)
        if wanted and self.active and self.active.name not in {"escape", "mayhem"}:
            self.end(request, "stars")
        goal = self.active or self._start(request, seat, cars, wanted)
        last = request.last_skill or {}
        fresh = goal.attempts > 0 and (
            last != goal.last_result or any(e.get("kind") == "skill_failed" for e in request.events)
        )
        running = goal.attempts > 0 and (
            last.get("status") in {"running", "queued"}
            or bool(last.get("queue"))
            or bool(last.get("pending"))
        )
        misfit = running and not fits(last.get("name"), seat)
        if misfit:
            running = False
        if now >= goal.data()["deadline"] or (goal.attempts >= LIMITS[goal.name][1] and not running):
            self.end(request, "limit")
            goal = self._start(request, seat, cars, wanted)
            running = False
            fresh = False
        if goal.name == "escape" or (goal.name == "mayhem" and goal.step == "escape"):
            goal.seen_wanted |= bool(wanted)
            if goal.seen_wanted and wanted == 0:
                self.end(request, "wanted cleared", reached=True)
                goal = self._start(request, seat, cars, wanted)
                running = False
                fresh = False
        if goal.step == "await_story" and now - goal.wait_since >= 20:
            self.end(request, "letter did not start a mission")
            goal = self._start(request, seat, cars, wanted)
            running = fresh = False
        if running:
            return self._reply(goal, [], "go_on", "running skill and queue still serve the errand")
        failed = fresh and last.get("status") == "failed" and not own_stop(last)
        done = fresh and last.get("status") == "done"
        if fresh:
            goal.last_result = dict(last)
        skill, reason = last.get("name"), last.get("reason", "")
        goal.seen_route |= request.minimap.get("route") in {"yellow", "purple"}
        plan = None
        free_step = False
        note = "retry: observed skill failure" if failed else ""
        if misfit:
            note = f"step ended: {last.get('name')} does not fit {seat}"
        if (
            failed
            and skill in {"drive_route", "get_away"}
            and reason in {HELD, "vehicle-held"}
            and seat == "vehicle"
        ):
            goal.resume = goal.step
            goal.step = "replace_car"
            plan = leave_vehicle()
            goal.exits += 1
            goal.left_at = now
            free_step = True
            note = reason
        elif failed and skill == "drive_route" and reason in STALLED:
            goal.stalls += 1
            if goal.stalls >= 2:
                self.end(request, f"{reason} twice on the way to {goal.place}")
            elif request.minimap.get("route") in {"purple", "yellow"}:
                plan = [call("drive_route", duration=120)]
                note = reason
            else:
                goal.step = "waypoint"
                note = reason
        elif failed and skill == "drive_route" and reason == "map-unreadable":
            goal.unreadable += 1
            if goal.unreadable >= 2:
                goal.step = "replace_car"
                plan = leave_vehicle()
                goal.left_at = now
                goal.exits += 1
                goal.unreadable = 0
                free_step = True
            else:
                plan = [call("look", duration=1.2, angle=180), call("drive_route", duration=120)]
            note = reason
        elif failed and skill == "drive_route" and reason == "time-limit":
            plan = [call("drive_route", duration=120)]
        elif failed and skill == "use_place":
            goal.step = "leave"
        elif failed and skill == "get_away" and reason in {"water", "on-foot"}:
            seat = "on_foot"
        elif failed and skill not in {"enter_vehicle", "walk_road"}:
            self.end(request, f"{skill}: {reason}")
        if self.active is None:
            goal = self._start(request, seat, cars, wanted)
            done = False
            plan = None
        if done and skill == "switch_character" and goal.step == "switch":
            goal.step = "waypoint"
        if done and skill == "set_waypoint" and goal.step in {"waypoint", "reset_waypoint"}:
            free_step = True
            match = WAYPOINT.match(reason)
            if match:
                goal.place = match[1]
                goal.distance = float(match[2]) if match[2] else None
                if self.abandonments[goal.place] >= 2:
                    self.end(request, "place excluded for this session")
                else:
                    goal.target = {
                        "place": goal.place,
                        **({"instance": self.story_instance} if goal.name == "story" else {}),
                    }
                    goal.step = (
                        "approach" if goal.step == "reset_waypoint" and goal.name != "cruise" else "travel"
                    )
            else:
                self.end(request, "waypoint completion lacked observed place")
        if (
            done
            and skill == "drive_route"
            and goal.step == "travel"
            and reason in {"arrived", "route-gone"}
            and (goal.seen_route or last.get("route_seen"))
        ):
            if goal.name == "cruise":
                self.end(request, "route arrival observed", reached=True)
            else:
                goal.step = "exit"
        if (
            done
            and skill == "walk_to_point"
            and goal.step in {"travel", "approach"}
            and (str(reason).startswith("arrived") or reason == "entered")
        ):
            if goal.step == "travel":
                if goal.name == "cruise":
                    self.end(request, "walking arrival observed", reached=True)
                else:
                    goal.step = "approach"
            elif goal.name == "story":
                goal.arrived = True
                goal.step = "await_story"
                goal.wait_since = now
            else:
                goal.step = "use"
        if done and skill == "use_place" and goal.step == "use":
            goal.used = True
            goal.step = "leave"
        if done and skill == "leave_building" and goal.step == "leave":
            if reason == "outdoors":
                self.end(
                    request,
                    "used place and observed outdoors" if goal.used else "use failed; returned outdoors",
                    reached=goal.used,
                )
            else:
                self.end(request, "exit lacked outdoor evidence")
        if done and skill == "punch" and goal.name == "mayhem":
            goal.step = "escape"
            goal.seen_wanted = bool(wanted)
            plan = escape_plan or [call("walk", duration=5, x=0, y=-1, sprint=True)]
        if self.active is None:
            goal = self._start(request, seat, cars, wanted)
            plan = None
        if plan is None:
            if goal.step == "replace_car":
                if seat == "vehicle":
                    if goal.exits >= 3:
                        self.end(request, "vehicle exit not observed after three attempts")
                        return self.decide(request, mode, escape_plan=escape_plan)
                    plan = leave_vehicle()
                    goal.exits += 1
                    goal.left_at = now
                    free_step = True
                elif goal.left_at is not None and now - goal.left_at < 12:
                    plan = [call("walk_road", duration=max(2, 12 - (now - goal.left_at)))]
                    free_step = True
                else:
                    goal.exits = 0
                    free_step = True
                    goal.step = goal.resume
                    plan = (
                        [call("enter_vehicle", duration=25, kind="any")]
                        if cars
                        else [call("walk_road", duration=15)]
                    )
            elif goal.name == "escape" or (goal.name == "mayhem" and goal.step == "escape"):
                if done and wanted == 0 and skill in {"walk", "get_away"}:
                    self.end(request, "escape movement completed without stars", reached=True)
                    return self.decide(request, mode)
                plan = escape_plan or (
                    [call("get_away", duration=60)]
                    if seat == "vehicle"
                    else [call("walk", duration=5, x=0, y=-1, sprint=True)]
                )
            elif goal.name == "mayhem":
                if seat == "vehicle":
                    plan = exit_car()
                elif any(o.get("kind") == "person" for o in request.objects):
                    plan = [call("punch", duration=20, hits=3)]
                else:
                    plan = [call("look", duration=0.8, angle=55), call("walk_road", duration=15)]
            elif goal.step == "switch":
                plan = [call("switch_character", duration=30, to="next")]
            elif goal.step in {"waypoint", "reset_waypoint"}:
                plan = self.trip(goal)
            elif goal.step == "exit":
                if seat == "vehicle":
                    plan = exit_car()
                else:
                    goal.step = "reset_waypoint"
                    plan = self.trip(goal)
            elif goal.step == "travel":
                if seat == "vehicle" and goal.distance is not None and goal.distance <= 250:
                    goal.step = "exit"
                    plan = exit_car()
                elif seat == "vehicle":
                    plan = [call("drive_route", duration=120)]
                elif goal.distance is not None and goal.distance <= 250:
                    plan = [call("walk_to_point", duration=60, sprint=True)]
                else:
                    plan = (
                        [call("enter_vehicle", duration=25, kind="any")]
                        if cars
                        else [call("walk_road", duration=15)]
                    )
            elif goal.step == "approach":
                if seat == "vehicle":
                    goal.step = "exit"
                    plan = exit_car()
                else:
                    plan = [
                        call(
                            "walk_to_point",
                            duration=60,
                            exact=True,
                            enter=goal.name in {"shop", "home"},
                            sprint=goal.distance is not None and goal.distance <= 250,
                        )
                    ]
            elif goal.step == "use":
                plan = [
                    call(
                        "use_place",
                        duration=30,
                        spend="no" if goal.name == "home" else "yes",
                        choice="random",
                    )
                ]
            elif goal.step == "leave":
                plan = [call("leave_building", duration=30)]
            else:
                plan = [call("wait", duration=min(3, max(0.1, 20 - (now - goal.wait_since))))]
        if not free_step:
            goal.attempts += 1
        response = self._reply(goal, plan, reason=note)
        self.transition = ""
        return response
