"""Bounded, observation-driven errands and their session selection policy."""

import copy
import random
import re
import secrets
import time
from collections import Counter, deque
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
    "roam": "ohne Karte die Straße entlang",
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
    "roam": (120, 8),
}
# The map would not take a waypoint this often in a row: it is left alone for a while, and the figure
# walks the road meanwhile instead of opening it every few seconds for the rest of the session.
MAP_FAILURES = 3
MAPLESS_SECONDS = 120.0
# The story's goal outlives a map that would not read, and between two tries lie this many seconds.
MAP_RETRY_SECONDS = 45.0
# The turns of the camera before a walk that ended stuck is tried again, in degrees, in this order.
UNSTICK_TURNS = (120, -120, 180)
# What a failed set_waypoint says when the map worked and the place was not on it: that counts
# against the place. Anything else it fails on is the map's or the reader's, and no place's fault.
NOT_ON_THE_MAP = ("place-not-in-legend", "legend-selection-skips-the-place", "place-instance-not-present")
WAYPOINT = re.compile(r"^waypoint set: (.+?) \((?:(\d+(?:\.\d+)?)m|distance not read)\)")


def call(name, **args):
    return {"name": name, "args": args}


def _sells(place):
    """Whether money may be spent where the waypoint led: not at the safehouse, a mission's letter or
    anything the map's list offers for sale, whatever errand set out for it."""
    from .legend import kind_of

    name = place or ""
    return not re.search(r"unterschlupf|safe ?house", name, re.I) and kind_of(name) not in {
        "property",
        "mission",
        "none",
    }


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
    walk_stuck: int = 0
    unreadable: int = 0
    waypoint_failures: int = 0
    waypoint_failed_at: float = 0.0
    exits: int = 0
    left_at: float | None = None
    resume: str = "travel"
    wait_since: float | None = None
    used: bool = False
    arrived: bool = False
    seen_wanted: bool = False
    seen_route: bool = False
    drive_ons: int = 0
    waypoint_set: bool = False

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
        "map_failures",
        "mapless_until",
    )

    def __init__(self, seed=None, clock=time.monotonic, chooser=None):
        self.seed = secrets.randbits(32) if seed is None else seed
        self.random = random.Random(self.seed)
        self.clock, self.chooser = clock, chooser
        self._noted = None  # the errand whose end the memory was last told of; not undone with the rest
        self._observed = deque(maxlen=64)  # confirmed facts survive a discarded head decision
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
        self.map_failures = 0
        self.mapless_until = -float("inf")
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
        if now < self.mapless_until:
            return "roam"
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
            goal.step = {"mayhem": "punch", "roam": "roam"}.get(name, "escape")
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

    def _keep(self, goal, reached, reason, blame=True):
        """Note the errand's end for later sessions, once: a decision the conductor drops is made again."""
        kept = self._kept()
        key = (goal.name, goal.started)
        if kept is None or key == self._noted or goal.name == "roam":
            return
        self._noted = key
        memory.errand_done(kept, goal.name, reached=reached)
        if goal.place:
            if reached:
                memory.place_reached(kept, goal.place, how=goal.name)
            elif blame:
                memory.place_failed(kept, goal.place, why=str(reason)[:80])

    def _observe(self, goal, event):
        kept = self._kept()
        key = (goal.name, goal.started, event)
        if kept is None or not goal.place or key in self._observed:
            return
        self._observed.append(key)
        memory.place_observed(kept, goal.place, event)

    def end(self, request, reason, *, reached=False, blame=True):
        """`blame` is false where the errand ended for something that says nothing about its place:
        stars, an objective, the map refusing a waypoint. Such an end is not counted against it."""
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
        self._keep(goal, reached, reason, blame)
        self.last_name = "escape" if goal.name == "mayhem" and goal.step == "escape" else goal.name
        self.abandoned = None if reached else goal.name
        if not reached and goal.place and blame:
            self.abandonments[goal.place] += 1
        if goal.name == "story":
            if reached:
                self.story_dampened = False
                self.story_failures = 0
            elif blame:
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
            # Stars, an objective or little health on the way say nothing about the place the errand
            # was going to. (An objective before the letter is not counted as the story reached
            # either: what began may be anything.)
            self.end(request, reason, blame=False)
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
        from .drive import _number
        from .goals import HELD, STALLED, fits, leave_vehicle, occupancy, own_stop
        from .skills import DriveRoute

        now = self.now(request)
        wanted = (request.hud or {}).get("wanted")
        if wanted is None:
            wanted = next(
                (e.get("wanted") for e in reversed(request.events) if e.get("kind") == "wanted_changed"), None
            )
        seat = occupancy(mode, request.events)
        cars = any(o.get("kind") in {"car", "truck", "motorcycle"} for o in request.objects)
        if wanted and self.active and self.active.name not in {"escape", "mayhem"}:
            self.end(request, "stars", blame=False)
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
        skill, reason = last.get("name"), last.get("reason") or ""
        if fresh and skill == "drive_route" and last.get("route_seen"):
            goal.drive_ons = 0
        if done and skill == "set_waypoint":
            goal.waypoint_set = True
        goal.seen_route |= request.minimap.get("route") in {"yellow", "purple"}
        if (
            failed
            and skill == "drive_route"
            and reason.startswith("route-lost")
            and goal.name == "story"
            and goal.step == "travel"
            and (goal.seen_route or last.get("route_seen"))
        ):
            distance = _number(request.minimap.get("gps_distance"))
            sampled_at = _number(request.minimap.get("gps_time"))
            recorded_distance = _number(last.get("end_distance"))
            recorded_age = _number(last.get("distance_age"))
            near_reading = (
                not request.minimap.get("corrupt")
                and request.minimap.get("minimap") == "tilted"
                and request.minimap.get("route") not in {"purple", "yellow"}
                and distance is not None
                and 0 <= distance <= DriveRoute.arrival_metres
                and sampled_at is not None
                and 0 <= now - sampled_at <= DriveRoute.arrival_age
            )
            near_record = (
                recorded_distance is not None
                and 0 <= recorded_distance <= DriveRoute.arrival_metres
                and recorded_age is not None
                and 0 <= recorded_age <= DriveRoute.arrival_age
            )
            if near_reading or near_record:
                failed, done, reason = False, True, "arrived"
        plan = None
        free_step = False
        note = "retry: observed skill failure" if failed else ""
        if misfit:
            note = f"step ended: {last.get('name')} does not fit {seat}"
        if (
            failed
            and skill in {"drive_route", "drive_on", "get_away"}
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
        elif failed and skill == "walk_road" and reason == "stuck" and seat != "vehicle":
            # The same walk from the same spot ends at the same wall: on 13 November, 17:49, the figure
            # stood before a garden wall between it and the road and the walk was planned eight times
            # in a row, each ending stuck after eleven seconds. It turns away first, another way each
            # time, walks a few seconds, and looks for the road from there.
            goal.walk_stuck += 1
            turn = UNSTICK_TURNS[(goal.walk_stuck - 1) % len(UNSTICK_TURNS)]
            plan = [
                call("look", duration=1.2, angle=turn),
                call("walk", duration=4, x=0, y=-1),
                call("walk_road", duration=15),
            ]
            note = f"stuck on foot: another way, turned by {turn}"
        elif (
            seat == "vehicle"
            and goal.step == "travel"
            and goal.waypoint_set
            and (
                (
                    failed
                    and skill == "drive_route"
                    and reason.startswith("route-lost")
                    and last.get("route_seen") is False
                )
                or (done and skill == "drive_on" and reason == "time-limit")
            )
        ):
            # A queued drive_route runs after drive_on, so its no-route failure is also
            # the checkpoint for a completed attempt. Bound the whole pair to two tries.
            if goal.drive_ons < 2:
                goal.drive_ons += 1
                plan = [call("drive_on", duration=30), call("drive_route", duration=120)]
                note = "waypoint stands: follow the road until the route returns"
            else:
                goal.step = "waypoint"
                goal.drive_ons = 0
                note = "route still absent after two road-following attempts"
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
        elif failed and skill in {"get_away", "drive_on"} and reason in {"water", "on-foot"}:
            seat = "on_foot"
        elif failed and skill == "set_waypoint" and goal.name == "story":
            goal.waypoint_failures += 1
            goal.waypoint_failed_at = now
            goal.step = "story_relocate" if goal.waypoint_failures == 1 else "story_radar"
            note = f"story retained after map failure: {reason}"
            free_step = True
            no_mission = (
                goal.waypoint_failures >= 2
                and goal.target.get("target") == "mission"
                and str(reason).startswith(("place-not-in-legend", "no-visible-mission-target"))
                and not request.objective.strip()
                and not any(b.get("color") in {"yellow", "blue"} for b in request.minimap.get("blips", []))
            )
            if no_mission:
                self.end(request, "no mission in the readable map or radar", blame=False)
                free_step = False
        elif failed and goal.name == "story" and goal.waypoint_failures:
            goal.step = "story_radar"
            note = f"story retained after recovery failure: {reason}"
            free_step = True
        elif failed and skill == "set_waypoint":
            on_the_map = str(reason).startswith(NOT_ON_THE_MAP)
            self.map_failures = 0 if on_the_map else self.map_failures + 1
            if self.map_failures >= MAP_FAILURES:
                self.mapless_until = now + MAPLESS_SECONDS
                self.map_failures = MAP_FAILURES - 1  # one more refusal after the pause starts the next
            self.end(request, f"{skill}: {reason}", blame=on_the_map)
        elif failed and skill not in {"enter_vehicle", "walk_road"}:
            self.end(request, f"{skill}: {reason}")
        if self.active is None:
            goal = self._start(request, seat, cars, wanted)
            done = False
            plan = None
        if done and skill == "switch_character" and goal.step == "switch":
            goal.step = "waypoint"
        if done and skill == "set_waypoint":
            self.map_failures = 0
            goal.waypoint_failures = 0
        if done and skill in {"walk_road", "drive_route"} and goal.step == "story_relocate":
            goal.step = "waypoint"
            note = "retry the mission map after relocation"
        if done and skill == "set_waypoint" and goal.step in {"waypoint", "reset_waypoint"}:
            free_step = True
            match = WAYPOINT.match(reason)
            if goal.name == "story":
                from .legend import kind_of

                if not match or kind_of(match[1]) != "mission":
                    goal.step = "story_radar"
                    goal.waypoint_failures = max(2, goal.waypoint_failures)
                    note = "story retained: completed waypoint was not a mission"
                    return self._reply(
                        goal,
                        recovery_plan or [call("wait", duration=1)],
                        reason=note,
                    )
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
            elif reason == "entered":
                self._observe(goal, "entered")
                goal.step = "use"
            else:
                # Reaching the map symbol does not prove the door was found. The walk reports
                # this as done, but a visit cannot use a shop or a wardrobe from the street.
                self._observe(goal, "entry_failed")
                self.end(request, "entrance not observed")
        if done and skill == "use_place" and goal.step == "use":
            self._observe(goal, "used")
            goal.used = True
            goal.step = "leave"
        if done and skill == "leave_building" and goal.step == "leave":
            if reason == "outdoors":
                self._observe(goal, "left")
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
        if goal.name == "story" and goal.step == "exit" and seat != "vehicle":
            goal.step = "approach"
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
            elif goal.name == "roam":
                if seat != "vehicle":
                    plan = [call("walk_road", duration=30)]
                elif request.minimap.get("route") in {"yellow", "purple"}:
                    plan = [call("drive_route", duration=60)]
                else:
                    plan = exit_car()
            elif goal.step == "story_relocate":
                if seat != "vehicle":
                    plan = [call("walk_road", duration=5)]
                elif request.minimap.get("route") in {"yellow", "purple"}:
                    plan = [call("drive_route", duration=5)]
                else:
                    plan = [*exit_car(), call("walk_road", duration=5)]
            elif goal.step == "story_radar":
                # The mission head supplies only stable mission markers here. With none on the radar
                # the map is the only way to the mission, and from another spot it may read: it is
                # opened again after a while of walking, not every few seconds, and the goal ends at
                # its limit like any other, so that a figure never sits in a car and waits for good.
                if recovery_plan:
                    plan = recovery_plan
                elif now - goal.waypoint_failed_at >= MAP_RETRY_SECONDS:
                    goal.step = "waypoint"
                    note = "retry the mission map from another spot"
                    plan = self.trip(goal)
                elif seat != "vehicle":
                    plan = [call("walk_road", duration=10)]
                elif request.minimap.get("route") in {"yellow", "purple"}:
                    plan = [call("drive_route", duration=10)]
                else:
                    plan = [call("wait", duration=3)]
                free_step = True
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
                        # Money is spent in a shop and nowhere else: not at home, and not where a
                        # shop's errand was led to the safehouse by what the map's list read.
                        spend="yes" if goal.name == "shop" and _sells(goal.place) else "no",
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
