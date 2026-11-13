"""Observable mission rules, with an injectable head for ambiguous situations."""

import math
import re
import unicodedata
from collections import Counter
from dataclasses import replace

from .contract import ARROW_XY
from .goals import HELD, Goals, leave_vehicle, own_stop
from .head import Head, HeadRequest, HeadResponse, SkillCall, parse_response
from .notes import intent


def _text(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(char)
    )


def _wanted(request: HeadRequest) -> int | None:
    wanted = (request.hud or {}).get("wanted")
    if wanted is not None:
        return wanted
    for event in reversed(request.events):
        if event.get("kind") == "wanted_changed":
            return event.get("wanted", 0) or 0
    return None


def movement(request: HeadRequest) -> str:
    """How the figure moves: the judge's accepted word where there is one, else the minimap.

    head_prompt.txt supplies the minimap heuristic. LOG.md, 11 November, records its exception:
    with stars the map is tilted on foot as well, so a tilted map with stars says nothing.
    """
    judged = (request.judgment or {}).get("mode")
    if judged == "unknown":
        judged = None  # foot said against a tilted map for less than three seconds: the map speaks
    if judged is not None:
        return {"foot": "on_foot", "vehicle": "vehicle"}.get(judged, "none")
    if request.minimap.get("corrupt"):
        return "unknown"
    shape = request.minimap.get("minimap")
    if shape == "flat":
        return "on_foot"
    if shape == "tilted" and _wanted(request) == 0:
        return "vehicle"
    return "unknown"


# The star reader misses frames: on Kerim's recordings of 11 and 12 November the stars went unread on
# 3 to 4 % of the frames with a tilted map, for 2.3 s at the longest. The last count read stands in
# for that long, so that a car is not taken for "who knows" every few seconds.
STARS_HOLD = 3.0
# With stars the map is tilted on foot as well, and says nothing about the seat. Where the figure
# sat when that was last known holds until something says otherwise, and a seat in a car for this
# long at most.
SEAT_HOLD = 120.0
# Seconds for which a marker that a walk arrived at is not a place to walk to again without an order.
REACHED_SECONDS = 60.0
REACHED_PX = 12.0  # A marker this near the arrow on the minimap is one the figure stands at.
# The same answer to the same failure this often in a row, and the next one is a different answer.
SAME_FAILED = 3
# A red marker this close to the arrow, in map pixels, is beside the car: about two car lengths.
NEAR_RED = 12.0
DRIVES = {"drive_route", "get_away", "drive_to_blip"}
# The steps of an errand that has arrived: its marker may lie in a room or up a staircase (a story
# marker in a house, a shop's counter), and the rules of the place do not pull the figure out of it.
AT_ITS_PLACE = {"approach", "await_story", "use", "leave", "switch"}


# Seconds of one fight before the rules look again; the first attempt at the Vagos in
# recordings/20261110-093238 lasted 23 s before it failed.
FIGHT_SECONDS = 20


def _call(name: str, **args: object) -> dict:
    return {"name": name, "args": args}


def _walk(*, sprint: bool = False) -> dict:
    return _call("walk", duration=5, x=0, y=-1, sprint=sprint)


def _explore() -> list[dict]:
    return [_call("walk_road", duration=30)]


def _route(target: str) -> list[dict]:
    return [
        _call("set_waypoint", target=target, duration=45, direction="any", distance="far"),
        _call("drive_route", duration=60),
    ]


def _rim_blip(blip: dict) -> bool:
    # The reader tests component centres, but a rim glyph can straddle that
    # threshold. Include its five-pixel footprint, not every blip of its color.
    if blip.get("border"):
        return True
    if "x" not in blip or "y" not in blip:
        return False
    cx, cy = ARROW_XY[0] + blip["x"], ARROW_XY[1] - blip["y"]
    return cx <= 43 or cx >= 206 or cy <= 37 or cy >= 134


class MissionHead:
    """First matching rule wins; an undecidable request reaches the fallback intact."""

    # After a map without a mission letter, this many routes go somewhere else before the map is
    # asked for a letter again: a new one appears when the game has moved on, not at once.
    LETTERLESS_ROUTES = 4
    # The conductor takes a goal from a head that says so, and from no other: a model behind the
    # rules answers with the plan alone.
    owns_goals = True

    def __init__(
        self, fallback: Head | None = None, *, goal_seed=None, chooser=None, task="autonomy", task_seconds=900
    ) -> None:
        if task not in {"autonomy", "mission-drive"}:
            raise ValueError("unknown mission task")
        if not math.isfinite(task_seconds) or task_seconds <= 0:
            raise ValueError("task seconds must be finite and positive")
        self.task, self.task_seconds = task, task_seconds
        self.fallback = fallback
        # `chooser` picks the next errand among those the rules offer (localhead.ErrandChooser: the
        # local model looking at the picture). It may say nothing, and then the seeded draw decides.
        self.chooser = chooser
        self._chose: str | None = None
        self.goals = Goals(seed=goal_seed, chooser=self._errand if chooser is not None else None)
        self.counts: Counter[str] = Counter()
        self.last_rule: str | None = None
        self.sought_mission = False
        self.letterless = 0
        self.objective_class: str | None = None
        self.pending_class: str | None = None
        self.pending_reads = 0
        self.blip_candidates: list[dict] = []
        self.stable_blips: list[dict] = []
        self.reached: dict[str, float] = {}  # the colour of a marker a walk arrived at, and when
        self.stars: tuple[int, float] | None = None  # the last count read, and when
        self.seat: tuple[str, float] | None = None  # where the figure last sat for sure, and when
        self.failed_key: str | None = None
        self.same_failed = 0
        self.place: tuple[str, float] | None = None
        self.place_label: str | None = None
        self.place_failures = 0
        self.place_result: tuple[str, float] | None = None
        self.place_rest_until = 0.0
        self.place_started_at: float | None = None

    # What one decision changes besides the goals: given back when the conductor drops the answer.
    KEPT = (
        "sought_mission",
        "letterless",
        "objective_class",
        "pending_class",
        "pending_reads",
        "blip_candidates",
        "stable_blips",
        "reached",
        "last_rule",
        "stars",
        "seat",
        "failed_key",
        "same_failed",
        "place",
        "place_label",
        "place_failures",
        "place_result",
        "place_rest_until",
        "place_started_at",
    )

    def _errand(self, offers):
        chosen = self.chooser(offers)
        if chosen is None:
            return None
        name = chosen.get("name") if isinstance(chosen, dict) else getattr(chosen, "name", chosen)
        self._chose = name if isinstance(name, str) else None
        return self._chose

    def decide(self, request: HeadRequest) -> HeadResponse:
        self._undo_urgent = (set(getattr(self, "pressed_help", set())), getattr(self, "standing_count", 0))
        self._undo_rest = {name: getattr(self, name) for name in self.KEPT}
        self._undo_counts = self.counts.copy()
        if self.chooser is not None:
            self._chose = None
            if hasattr(self.chooser, "observe"):
                self.chooser.observe(request)
            before = self.goals.active
        response = self._decide(request)
        if self.chooser is not None and hasattr(self.chooser, "record"):
            # What the seeded draw chose is told to the chooser, which keeps its own choices itself:
            # it offers the model nothing that has just been done twice.
            started = self.goals.active
            if started is not None and started is not before and started.name != self._chose:
                self.chooser.record({"name": started.name})
        last = request.last_skill or {}
        events = {event.get("kind") for event in request.events}
        exceptions = {"failure", "skill_failed", "screen", "standing", "guard"}
        exceptional = bool(events & exceptions) or any(str(kind).startswith("guard_") for kind in events)
        if (
            response.plan
            and last.get("status") == "running"
            and "args" in last
            and response.plan[0].name == last.get("name")
            and response.plan[0].args == last["args"]
            and not exceptional
        ):
            response = replace(
                response,
                plan=(),
                action="go_on",
                reason="goal_running: identical skill and arguments",
            )
            # Nothing was planned, so no route was used up: a waypoint that is being set is not
            # counted down towards asking the map for a letter again.
            self.letterless = self._undo_rest["letterless"]
            self.sought_mission = self._undo_rest["sought_mission"]
        first = response.plan[0] if response.plan else None
        if (
            first is not None
            and first.name == "press"
            and first.args.get("button") == "triangle"
            and self.seat is not None
            and self.seat[0] == "vehicle"
        ):
            # The plan gets out of the car: with stars the map will not say so afterwards.
            self.seat = ("on_foot", self.goals.now(request))
        return response

    def _held(self, request: HeadRequest) -> HeadRequest:
        """Fill in what this one request could not read from what the last ones did: the stars the
        reader missed for a moment, and the seat a tilted map under stars cannot show."""
        now = self.goals.now(request)
        hud = request.hud
        if self.place_started_at is None:
            self.place_started_at = now
        if request.place in {"room", "landing", "street"}:
            self.place = (request.place, now)
        elif request.place == "unknown" and self.place is not None and 0 <= now - self.place[1] <= 10:
            request = replace(request, place=self.place[0])
        if hud is not None:
            changed = [e for e in request.events if e.get("kind") == "wanted_changed"]
            if hud.get("wanted") is not None:
                self.stars = (hud["wanted"], now)
            elif changed:
                self.stars = (changed[-1].get("wanted", 0) or 0, now)
            elif (
                self.stars is not None
                and 0 <= now - self.stars[1] <= STARS_HOLD
                and hud.get("screen", "game") == "game"
            ):
                request = replace(request, hud={**hud, "wanted": self.stars[0]})
        last = request.last_skill or {}
        for event in request.events:
            if event.get("kind") == "vehicle_enter":
                self.seat = ("vehicle", now)
            elif event.get("kind") == "vehicle_exit":
                self.seat = ("on_foot", now)
        if last.get("name") == "enter_vehicle" and last.get("status") == "done":
            self.seat = ("vehicle", now)
        elif last.get("name") in DRIVES:
            if last.get("status") == "failed" and last.get("reason") in {"on-foot", "water"}:
                self.seat = ("on_foot", now)
            elif last.get("status") in {"running", "done"} and self.seat and self.seat[0] == "vehicle":
                # A drive that moves is a car: one that does not ends held within seconds.
                self.seat = ("vehicle", now)
        mode = movement(request)
        if mode in {"vehicle", "on_foot"}:
            self.seat = (mode, now)
        elif (
            mode == "unknown"
            and self.seat is not None
            # On foot is kept until a car is seen to be entered: taking a figure in a car for one on
            # foot presses nothing that matters, the other way round the throttle is the trigger.
            and (self.seat[0] == "on_foot" or 0 <= now - self.seat[1] <= SEAT_HOLD)
            and request.minimap.get("minimap") == "tilted"
            and not request.minimap.get("corrupt")
            and (request.judgment or {}).get("mode") is None
        ):
            word = {"on_foot": "foot", "vehicle": "vehicle"}[self.seat[0]]
            request = replace(request, judgment={**(request.judgment or {}), "mode": word})
        return request

    def _standing_rule(self, request, mode):
        if not any(event.get("kind") == "standing" for event in request.events):
            self.standing_count = 0
            return None
        event = next(e for e in reversed(request.events) if e.get("kind") == "standing")
        count = event.get("count", getattr(self, "standing_count", 0) + 1)
        self.standing_count = count
        goal = self.goals.active
        if goal is not None and goal.step == "await_story":
            # Standing on the letter is what the errand is doing while the mission starts.
            return None
        last = request.last_skill or {}
        indoors = (last.get("name") == "walk_to_point" and last.get("reason") == "entered") or bool(
            goal and goal.step in {"use", "leave"}
        )
        # Every fourth time the errand is given up for another, where there is nothing the game
        # asks for: in a mission no errand is started, and the figure keeps trying to get free.
        # Between two such ends the three ways out are tried again, so that the errand just begun
        # is not thrown out by the next report twelve seconds later.
        free = not request.objective.strip() and self.objective_class in (None, "unknown")
        count = count if count < 4 else (count % 4 or (4 if free else 3))
        if count >= 4:
            self.goals.end(request, "standing four times")
            response = self.goals.decide(request, mode)
            return (
                "standing_abandon",
                [{"name": item.name, "args": item.args} for item in response.plan],
                "Hier geht es nicht weiter, ich nehme mir etwas anderes vor.",
            )
        if indoors and count >= 2:
            if goal:
                goal.step = "leave"
            return "standing_leave", [_call("leave_building", duration=30)], "Ich gehe wieder nach draußen."
        if mode == "vehicle" and count > 1:
            plan = leave_vehicle()
        elif mode == "vehicle":
            plan = (
                [_call("get_away", duration=60)]
                if _wanted(request)
                else [_call("drive_route", duration=120)]
                if request.minimap.get("route") in {"purple", "yellow"}
                else leave_vehicle()
            )
        elif count == 1:
            plan = [
                _call("press", button="square", duration=0.1),
                _call("walk", duration=3, x=0, y=-1, sprint=True),
            ]
        elif count == 2:
            plan = [_call("look", duration=1, angle=120), _call("walk", duration=4, x=0, y=-1, sprint=True)]
        else:
            plan = [
                _call("walk", duration=3, x=0, y=1),
                _call("look", duration=1, angle=180),
                _call("walk_road", duration=15),
            ]
        return "standing_recovery", plan, "Ich stecke fest und versuche einen anderen Weg."

    def _route_going(self, request: HeadRequest, mode: str, interrupted: str | None) -> bool:
        """A drive follows a route that has just gone and no goal holds the plan: let the drive end.

        drive_route stops on its own after two seconds without the route, as arrived at the place or as
        a route lost, and the request after that says which. Planning a new waypoint at the first sign
        of it threw out the drive of the recorded arrivals about a second before it could."""
        last = request.last_skill or {}
        return (
            mode == "vehicle"
            and self.goals.active is None
            and last.get("name") == "drive_route"
            and last.get("status") == "running"
            and request.minimap.get("minimap") == "tilted"
            and request.minimap.get("route") not in {"yellow", "purple"}
            and (request.hud or {}).get("screen", "game") == "game"
            and not _wanted(request)
            and interrupted not in {"low_health", "death_or_arrest"}
        )

    def discard(self) -> None:
        """The conductor has dropped the answer to the last request: give back what it consumed."""
        self.goals.undo()
        if hasattr(self, "_undo_urgent"):
            self.pressed_help, self.standing_count = self._undo_urgent
        for name, value in getattr(self, "_undo_rest", {}).items():
            setattr(self, name, value)
        if hasattr(self, "_undo_counts"):
            self.counts = self._undo_counts.copy()

    def _place_rule(self, request, mode, interrupted):
        now = self.goals.now(request)
        if request.place != self.place_label:
            self.place_label = request.place
            self.place_failures = 0
            self.place_rest_until = 0.0

        name = {"room": "leave_building", "landing": "descend"}.get(request.place)
        last = request.last_skill or {}
        events = [
            event.get("skill") or {}
            for event in request.events
            if event.get("kind") in {"skill_failed", "skill_ended"}
            and (event.get("skill") or {}).get("name") == name
        ]
        result = events[-1] if events else last
        retry = False
        if name and result.get("name") == name:
            signature = repr(result)
            fresh = (
                self.place_result is None
                or self.place_result[0] != signature
                or (bool(events) and self.place_result[1] != now)
            )
            if result.get("status") == "done":
                self.place_failures = 0
                self.place_rest_until = 0.0
            elif result.get("status") == "failed" and fresh and not own_stop(result):
                self.place_failures += 1
                retry = True
                if self.place_failures >= 3:
                    self.place_rest_until = now + 120
            self.place_result = (signature, now if fresh else self.place_result[1])

        hud = request.hud or {}
        kinds = {event.get("kind") for event in request.events}
        health = hud.get("health")
        low_health = health < 1 / 3 if health is not None else "low_health" in kinds
        free = not request.objective.strip() and self.objective_class in (None, "unknown")
        # The first decision of a session comes before the judge has said how the figure moves, and
        # the map alone can be wrong about it: on 13 November the camera stood in the first person
        # in a room, the map was read as tilted, and the head took the figure to sit in a car and
        # opened the pause map. Until the judge has spoken the head waits for the place as well.
        unsure = (
            request.place == "unknown"
            and (request.judgment or {}).get("mode") is None
            and now - self.place_started_at < 6
        )
        if (
            not free
            or (mode != "on_foot" and not unsure)
            or hud.get("screen", "game") != "game"
            or _wanted(request)
            or low_health
            or interrupted in {"low_health", "death_or_arrest"}
            or any(e.get("kind") == "stuck" and e.get("screen") == "shop_menu" for e in request.events)
        ):
            return None

        if request.place == "unknown" and now - self.place_started_at < 6:
            rule, plan, sentence = (
                "place_wait",
                [SkillCall("wait", {"duration": 1})],
                "Ich schaue erst, wo ich bin.",
            )
        elif name:
            if now < self.place_rest_until:
                return None
            if self.place_rest_until:
                self.place_rest_until = 0.0
                self.place_failures = 0
            if self.goals.active is not None and self.goals.active.step in AT_ITS_PLACE:
                return None
            room = request.place == "room"
            rule = "room_leave" if room else "landing_descend"
            sentence = (
                "Ich bin in einem Raum, ich gehe zuerst raus."
                if room
                else "Ich stehe oben vor der Tür, ich gehe die Treppe runter."
            )
            plan = [SkillCall(name, {"duration": 120 if room else 40})]
            # A failure is answered with the same skill and no turn of the view before it: the
            # search looks all round by itself and remembers what it has tried, and a turn it has
            # not made itself is one it cannot reckon with. On 13 November the limit came while the
            # figure was pushing the apartment's front door open, and the half turn that followed
            # took it back into the bedroom.
            if not room and last.get("status") == "running" and last.get("name") == "leave_building":
                # Out of the door: leave_building walks clear of it and ends by itself.
                self.last_rule = rule
                self.counts[rule] += 1
                return HeadResponse((), sentence, action="go_on")
            if (
                not retry
                and last.get("status") == "running"
                and (
                    # Already on its way out or down: an event that asks the head again, the guard's news
                    # of a marker or a changed help text, must not start the skill's search afresh. On
                    # 13 November that restarted leave_building every few seconds.
                    last.get("name") == name or (last.get("name") == "look" and name in last.get("queue", []))
                )
            ):
                self.last_rule = rule
                self.counts[rule] += 1
                return HeadResponse((), sentence, action="go_on")
        else:
            return None
        self.last_rule = rule
        self.counts[rule] += 1
        # P83 registers descend; this card deliberately plans that call by name only.
        return HeadResponse(
            tuple(plan),
            sentence,
            goal=self.goals.active.data() if self.goals.active else None,
            step=self.goals.active.step if self.goals.active else None,
        )

    def _decide(self, request: HeadRequest) -> HeadResponse:
        if self.task == "mission-drive":
            self.goals.mark()
            return self.goals.mission_drive(
                request,
                seconds=self.task_seconds,
                own_vehicle=self._own_vehicle,
            )
        last = request.last_skill or {}
        if last.get("status") == "failed" and str(last.get("reason") or "").startswith(("guard_", "pad_")):
            # The guard took the pad and stopped the skill (guard.py), or a hand on the controller did
            # (conductor.refuse). Neither is a failure of the skill: the rules and the goals plan afresh
            # instead of retrying it with a look, and the guard's own events, guard_start and guard_end,
            # are news like any other.
            request = replace(request, last_skill={**last, "status": "stopped"})
        request = self._held(request)
        self.goals.mark()
        self._update_intent(request)
        self.goals.learn(request.last_skill)
        arrived = request.last_skill or {}
        if (
            arrived.get("name") == "walk_to"
            and arrived.get("status") == "done"
            and str(arrived.get("reason") or "").startswith("arrived")
        ):
            # The report names no colour: the markers at the figure's feet are the ones it arrived at.
            at_hand = {
                blip.get("color")
                for blip in request.minimap.get("blips", [])
                if blip.get("color") in {"yellow", "blue"}
                and math.hypot(blip.get("x", math.inf), blip.get("y", math.inf)) <= REACHED_PX
            }
            self.reached = {**self.reached, **dict.fromkeys(at_hand, self.goals.now(request))}
        candidates = [
            blip
            for blip in request.minimap.get("blips", [])
            if blip.get("color") in {"yellow", "blue"} and not _rim_blip(blip)
        ]
        self.stable_blips = [
            blip
            for blip in candidates
            if any(
                old.get("color") == blip.get("color")
                and (old.get("x", 0) - blip.get("x", 0)) ** 2 + (old.get("y", 0) - blip.get("y", 0)) ** 2
                <= 12**2
                for old in self.blip_candidates
            )
        ]
        self.blip_candidates = candidates
        interrupted = self.goals.guard(request)
        hud = request.hud or {}
        mode = movement(request)
        if any(
            event.get("kind") in {"cutscene", "loading", "black"}
            or (event.get("kind") == "screen" and event.get("screen") in {"cutscene", "loading", "black"})
            for event in request.events
        ):
            rule, plan, sentence = self._rule(request)
            self.last_rule = rule
            self.counts[rule] += 1
            return parse_response({"plan": plan, "sentence": sentence})
        placed = self._place_rule(request, mode, interrupted)
        if placed is not None:
            return placed
        urgent = None
        if any(
            event.get("kind") == "stuck" and event.get("screen") == "shop_menu" for event in request.events
        ):
            # A menu is open in a mission and no skill asked for it (flow.py tells the head once, and
            # leaves the menu itself when nothing comes of it): it may be what the mission wants used,
            # the suit for the jeweller or the gun before the long stretch.
            # The reflex reports a menu only in a mission, and there money goes where the mission
            # wants something bought. Should an errand hold the plan all the same, the errand says:
            # a shop's spends, the one at home and every other do not.
            active = self.goals.active
            spend = "yes" if active is None or active.name == "shop" else "no"
            urgent = (
                "mission_menu",
                [_call("use_place", duration=40, spend=spend, choice="first")],
                "Ein Menü ist offen, ich nehme, was die Mission will.",
            )
        elif hud.get("screen", "game") == "game":
            if (
                request.objective.strip()
                and intent(request.objective)["class"] in {"use", "pick_up", "unknown"}
                and re.search(r"drücke|halte", request.help, re.IGNORECASE)
                and request.help not in getattr(self, "pressed_help", set())
            ):
                if not hasattr(self, "pressed_help"):
                    self.pressed_help = set()
                self.pressed_help.add(request.help)
                urgent = (
                    "objective_prompt",
                    [_call("do_prompt", duration=3)],
                    "Ich benutze den angezeigten Knopf.",
                )
            if urgent is None:
                urgent = self._standing_rule(request, mode)
        if urgent is not None:
            rule, plan, sentence = urgent
            self.last_rule = rule
            self.counts[rule] += 1
            return parse_response(
                {
                    "plan": plan,
                    "sentence": sentence,
                    "goal": self.goals.active.data() if self.goals.active else None,
                    "step": self.goals.active.step if self.goals.active else None,
                }
            )
        if self._route_going(request, mode, interrupted):
            self.last_rule = "drive_ends"
            self.counts[self.last_rule] += 1
            return parse_response(
                {
                    "plan": [],
                    "sentence": "Die Route ist weg, die Fahrt endet gleich von selbst.",
                    "action": "go_on",
                    "reason": "kept: the drive ends by itself two seconds after the route went",
                }
            )
        free = not request.objective.strip() and self.objective_class == "unknown"
        available = hud.get("screen", "game") == "game" and mode in {"vehicle", "on_foot"}
        colors = {b.get("color") for b in request.minimap.get("blips", []) if not _rim_blip(b)}
        # The goal's waypoint skill owns its map/menu and must finish closing it.
        last = request.last_skill or {}
        # A temporarily unreadable movement mode is not evidence against the running goal.
        if (
            self.goals.active is not None
            and last.get("status") == "running"
            and hud.get("screen", "game") == "game"
        ):
            available = True
        if (
            free
            and self.goals.active is not None
            and interrupted is None
            and last.get("name") == "set_waypoint"
            and last.get("status") == "running"
            and hud.get("screen") in {"map", "pause"}
        ):
            response = self.goals.decide(request, mode)
            self.last_rule = "goal_" + response.goal["name"]
            self.counts[self.last_rule] += 1
            return response
        if (
            free
            and available
            and interrupted not in {"low_health", "death_or_arrest"}
            and (self.goals.active is not None or not self._failed(request))
        ):
            if _wanted(request) and not (self.goals.active is None and self.goals.abandoned == "escape"):
                selected = self._rule(request)
                if selected is not None:
                    response = self.goals.decide(request, mode, escape_plan=selected[1])
                    self.last_rule = selected[0]
                    self.counts[self.last_rule] += 1
                    return response
            elif not _wanted(request) and (
                self.goals.active is not None or not colors & {"red", "yellow", "blue"}
            ):
                recovery = self._rule(request) if self._failed(request) else None
                story_recovery = self.goals.active is not None and self.goals.active.name == "story"
                if story_recovery:
                    # A failed map does not change the destination. Only a stable
                    # mission blip can replace the map route during story recovery.
                    recovery = None
                    if self.stable_blips:
                        color = self.stable_blips[0]["color"]
                        recovery = (
                            "story_radar",
                            [
                                _call("drive_to_blip", color=color, mode="reach", duration=60)
                                if mode == "vehicle"
                                else _call("walk_to", color=color, duration=10)
                            ],
                        )
                response = self.goals.decide(
                    request,
                    mode,
                    recovery_plan=recovery[1] if recovery else None,
                    # A map without roads keeps its compass heading: no turn is put before the walk.
                    keep_heading=bool(recovery) and recovery[0] == "foot_explore_roadless",
                )
                self.last_rule = "goal_" + response.goal["name"]
                self.counts[self.last_rule] += 1
                return response
        selected = self._rule(request)
        if selected is None:
            if self.fallback is not None:
                self.last_rule = "fallback"
                self.counts[self.last_rule] += 1
                # What the model answers is a plan; a goal belongs to the rules.
                response = self.fallback.decide(request)
                if response.goal is not None:
                    response = replace(response, goal=None)
                if self.goals.transition:
                    response = replace(response, reason=self.goals.transition)
                    self.goals.transition = ""
                return response
            selected = (
                "moving_default",
                [_walk(sprint=bool(_wanted(request)))],
                "Ein eindeutiges Ziel ist gerade nicht erkennbar, ich gehe weiter.",
            )
        rule, plan, sentence = selected
        # head_prompt.txt:58-60: never immediately repeat a failed skill call.
        failed = None if self._chase_over(request) else self._failed(request)
        if (
            failed
            and plan[0]["name"] == failed
            and rule not in {"screen_wait", "screen_reflex", "foot_explore_roadless"}
        ):
            rule += "_after_failure"
            plan = [_call("look", duration=0.5, angle=45), *plan]
            sentence = "Der letzte Versuch ist gescheitert, ich orientiere mich zuerst neu."
        # The same answer to a failure, failing again, was given for as long as the session lasted.
        # From the third time on the answer changes: out of the car that gets nowhere, and on foot
        # off in another direction each time.
        key = repr((rule, plan))
        self.same_failed = (self.same_failed + 1 if key == self.failed_key else 1) if failed else 0
        self.failed_key = key if failed else None
        if self.same_failed >= SAME_FAILED and not rule.startswith(("screen_", "judged_", "objective_wait")):
            if mode == "vehicle":
                rule, plan = "failed_again_leave_vehicle", leave_vehicle()
                sentence = "So komme ich mit diesem Auto nicht weiter, ich steige aus."
            else:
                angle = (90, 180, -90)[(self.same_failed - SAME_FAILED) % 3]
                rule, plan = "failed_again", [_call("look", duration=1, angle=angle), _walk()]
                sentence = "Derselbe Versuch scheitert immer wieder, ich gehe woanders hin."
        response = parse_response({"plan": plan, "sentence": sentence})
        if self.goals.transition:
            response = replace(response, reason=self.goals.transition)
            self.goals.transition = ""
        self.last_rule = rule
        self.counts[rule] += 1
        self.sought_mission = any(call.args.get("target") == "mission" for call in response.plan)
        return response

    @staticmethod
    def _own_vehicle(request):
        """A saved head frame is read off the control loop; absence remains unknown."""
        from pathlib import Path

        import cv2

        from .foot import hud_crop
        from .own_vehicle import find_own_vehicle

        if not request.jpeg_path or not Path(request.jpeg_path).is_file():
            return None
        frame = cv2.imread(request.jpeg_path)
        if frame is None:
            return None
        return find_own_vehicle(hud_crop(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))

    def _update_intent(self, request: HeadRequest) -> None:
        """Require a second observation before replacing an established class."""
        observed = intent(request.objective)["class"]
        if self.objective_class is None or any(
            event.get("kind") in {"failure", "pass", "mission_ended"} for event in request.events
        ):
            self.objective_class = observed
            self.pending_class = observed
            self.pending_reads = 0
        elif observed == self.objective_class:
            self.pending_class = observed
            self.pending_reads = 0
        else:
            if observed != self.pending_class:
                self.pending_class = observed
                self.pending_reads = 0
            self.pending_reads += 1
            if self.pending_reads >= 2:
                self.objective_class = observed
                self.pending_reads = 0

    def _intent_rule(self, request: HeadRequest, mode: str, cars: bool):
        """What the class of the objective settles by itself; None leaves it to the rules below."""
        objective_class = self.objective_class
        if objective_class == "wait":
            return (
                "objective_wait",
                [_call("look", duration=0.5, angle=20), _call("wait", duration=3)],
                "Der Auftrag verlangt zu warten, ich bleibe hier.",
            )
        if objective_class == "escape":
            # A route or a marker the game gives is the way out and belongs to the rules below.
            marked = {blip.get("color") for blip in request.minimap.get("blips", [])} & {"yellow", "blue"}
            if mode == "vehicle":
                return (
                    "objective_escape_vehicle",
                    [_call("get_away", duration=60)],
                    "Ich fahre aus dem Gebiet.",
                )
            if mode == "on_foot" and not marked:
                return "objective_escape_foot", [_walk(sprint=True)], "Ich laufe aus dem Gebiet."
        if mode == "on_foot" and objective_class in {"enter_vehicle", "steal"} and cars:
            return (
                "objective_" + objective_class,
                [_call("enter_vehicle", duration=25, kind="any")],
                "Ich gehe zum sichtbaren Fahrzeug und steige ein.",
            )
        if (
            mode == "on_foot"
            and objective_class == "take_out"
            and any(
                blip.get("color") == "red" and not blip.get("border")
                for blip in request.minimap.get("blips", [])
            )
        ):
            return (
                "take_out_fight",
                [_call("fight", duration=FIGHT_SECONDS, cover="no")],
                "Der Auftrag lautet ausschalten, ich kämpfe gegen die roten Ziele.",
            )
        if mode == "vehicle" and request.minimap.get("route") not in {"yellow", "purple"}:
            # Seated, with an order and no route: what the order is about is a marker on the map, and
            # the car goes at the marker (pursuit.py). With a route the rules below follow the route.
            colors = {blip.get("color") for blip in request.minimap.get("blips", [])}
            chase = None
            if objective_class == "follow":
                color = next((c for c in ("blue", "red", "yellow") if c in colors), None)
                # "Verfolge" is a chase and closes in; "Folge" keeps the distance the game wants.
                how = "catch" if _text(request.objective).lstrip().startswith("verfolg") else "follow"
                chase = color and (color, how, "Ich bleibe an dem markierten Ziel dran.")
            elif objective_class in {"take_out", "destroy"} and "red" in colors:
                near = min(
                    (
                        math.hypot(blip.get("x", 0), blip.get("y", 0))
                        for blip in request.minimap.get("blips", [])
                        if blip.get("color") == "red" and not _rim_blip(blip)
                    ),
                    default=None,
                )
                if near is not None and near <= NEAR_RED:
                    # Beside the target: out of the car, and the rule on foot fights it.
                    return (
                        "take_out_leave_vehicle",
                        [_call("press", button="triangle", duration=0.1), _call("wait", duration=2)],
                        "Das Ziel ist direkt neben mir, ich steige aus.",
                    )
                # A short stretch, so that the rules see whether the car is beside the target yet.
                chase = ("red", "catch", "Das Ziel ist rot markiert, ich fahre hinterher.")
            elif objective_class in {"go_to", "bring", "return_to"}:
                color = next((c for c in ("yellow", "blue") if c in colors), None)
                chase = color and (color, "reach", "Es gibt keine Route, ich fahre auf die Markierung zu.")
            if chase:
                color, how, sentence = chase
                return (
                    "objective_blip_" + how,
                    [
                        _call(
                            "drive_to_blip",
                            color=color,
                            mode=how,
                            duration=20 if objective_class in {"take_out", "destroy"} else 120,
                        )
                    ],
                    sentence,
                )
        # Going somewhere, bringing, following, picking up and using are answered by the route and
        # the marked target as the rules below do for any objective; protecting, destroying and
        # sneaking have no skill of their own yet and get the same.
        return None

    def close(self) -> None:
        close = getattr(self.fallback, "close", None)
        if close is not None:
            close()

    def _trip(self, request: HeadRequest, *, follow: int = 60) -> list[dict]:
        """Where a route goes when the rules choose it: to the mission the objective names, or, with
        nothing asked, to a place from the map's legend. Escapes keep their point on the map."""
        if not self._unasked(request):
            return _route(self._destination(request))
        return self.goals.trip(follow=follow)

    def _unasked(self, request: HeadRequest) -> bool:
        """Nothing on screen and no order kept from before asks for anything."""
        return not request.objective.strip() and self.objective_class == "unknown"

    def _destination(self, request: HeadRequest) -> str:
        """Where a new route goes: to a mission letter, because the story lies there, unless the
        map has just shown none (head_prompt.txt:28-30)."""
        if self.sought_mission and self._failed(request) == "set_waypoint":
            self.letterless = self.LETTERLESS_ROUTES
        if self.letterless:
            self.letterless -= 1
            return "away"
        return "mission"

    def _chase_over(self, request: HeadRequest) -> bool:
        """A drive at a marker ended on its time or lost the marker: following has no arrival, so that
        is how it ends, and the rules look at the map again instead of treating it as a failure."""
        return self._failed(request) == "drive_to_blip" and self._failure_reason(request) in {
            "time-limit",
            "blip-gone",
        }

    @staticmethod
    def _failure_reason(request: HeadRequest) -> str | None:
        if request.last_skill and request.last_skill.get("status") == "failed":
            if not own_stop(request.last_skill):
                return request.last_skill.get("reason")
        for event in reversed(request.events):
            if event.get("kind") == "skill_failed" and not own_stop(event.get("skill")):
                return (event.get("skill") or {}).get("reason")
        return None

    @staticmethod
    def _failed(request: HeadRequest) -> str | None:
        # A skill the conductor stopped for the goal (goal_limit, goal_stars) did not fail.
        if request.last_skill and request.last_skill.get("status") == "failed":
            if not own_stop(request.last_skill):
                return request.last_skill.get("name")
        for event in reversed(request.events):
            if event.get("kind") == "skill_failed" and not own_stop(event.get("skill")):
                return (event.get("skill") or {}).get("name")
        return None

    def _rule(self, request: HeadRequest) -> tuple[str, list[dict], str] | None:
        hud = request.hud or {}
        kinds = {event.get("kind") for event in request.events}
        screen = hud.get("screen")
        screens = {"cutscene", "loading", "black"}
        # head_prompt.txt:10: these screens are allowed a short wait.
        if (
            screen in screens
            or kinds & screens
            or any(
                event.get("kind") == "screen" and event.get("screen") in screens for event in request.events
            )
        ):
            return "screen_wait", [_call("wait", duration=3)], "Das Bild wechselt gerade, ich warte kurz."

        # head_prompt.txt:49-56: the local reflex owns blocking screens.
        # Do not send movement into recorded failed/pause/map/phone screens.
        if screen and screen != "game":
            return (
                "screen_reflex",
                [_call("wait", duration=1)],
                "Ein Bildschirm unterbricht das Spiel, ich warte kurz.",
            )

        mode = movement(request)
        if mode == "none":
            # The judge sees a cutscene, a black screen or a figure that is dead: nothing to steer.
            return "judged_wait", [_call("wait", duration=3)], "Gerade läuft etwas ohne mich, ich warte."
        wanted = _wanted(request)
        cars = any(obj.get("kind") in {"car", "truck", "motorcycle"} for obj in request.objects)
        # head_prompt.txt:43-47 and LOG.md:102-106: flee, never fight;
        # a tilted wanted minimap alone cannot authorize entering a vehicle.
        if self._failed(request) in {"get_away", "drive_to_blip"}:
            reason = self._failure_reason(request)
            if reason == "vehicle-held" and mode == "vehicle":
                return "leave_held_vehicle", leave_vehicle(), "Ich steige aus und suche ein anderes Auto."
            if reason in {"water", "on-foot"}:
                mode = "on_foot"
        if wanted:
            if mode == "vehicle":
                # A waypoint set by the pilot is still up: keep driving instead of opening the map
                # again with the police behind.
                if request.minimap.get("route") == "purple":
                    return (
                        "wanted_vehicle_route",
                        [_call("get_away", duration=60)],
                        "Die Polizei sucht mich, ich fahre weiter aus dem Suchgebiet.",
                    )
                return (
                    "wanted_vehicle",
                    [_call("get_away", duration=60)],
                    "Die Polizei sucht mich, ich fahre aus dem Suchgebiet.",
                )
            if mode == "on_foot":
                # A car that could not be entered is not asked for again at once: the figure runs
                # first, and the next car in view is another try.
                if cars and self._failed(request) != "enter_vehicle":
                    return (
                        "wanted_on_foot_vehicle",
                        [_call("enter_vehicle", duration=25, kind="any"), _call("get_away", duration=60)],
                        "Ein Fahrzeug ist zu sehen, ich steige zur Flucht ein.",
                    )
                return "wanted_on_foot", [_walk(sprint=True)], "Die Polizei sucht mich, ich laufe weiter."
            return None

        health = hud.get("health")
        low_health = health is not None and health < 1 / 3
        if health is None:
            low_health = "low_health" in kinds
        # head_prompt.txt:35-41: escape at less than one third health.
        if low_health:
            if mode == "vehicle":
                return "low_health_vehicle", _route("away"), "Meine Gesundheit ist niedrig, ich fahre weg."
            if mode == "on_foot":
                return (
                    "low_health_on_foot",
                    [_walk(sprint=True)],
                    "Meine Gesundheit ist niedrig, ich laufe weg.",
                )
            return None

        # head_prompt.txt:49-60: failure/retry must not replay the old plan.
        # Menu confirmation belongs to the existing reflex, not this head.
        if self.objective_class == "wait":
            return self._intent_rule(request, mode, cars)

        if self._failed(request) and not self._chase_over(request):
            if mode == "unknown":
                return None
            if mode == "vehicle":
                if self._failed(request) == "drive_route" and self._failure_reason(request) == HELD:
                    # The car will not move: out of it and on to another, not a new route in the same car.
                    return (
                        "leave_held_vehicle",
                        leave_vehicle(),
                        "Das Auto bewegt sich nicht, ich steige aus und nehme ein anderes.",
                    )
                self._destination(request)
                return (
                    "failed_vehicle_skill",
                    self._trip(request) if self._unasked(request) else _route("away"),
                    "Der letzte Versuch ist gescheitert, ich setze eine neue Route.",
                )
            failed, reason = self._failed(request), self._failure_reason(request)
            if (failed in {"walk", "walk_road"} and reason == "stuck") or (
                failed == "walk_to" and reason == "blocked"
            ):
                # Walking found no way round in four tries (foot.py): the way lies behind. A look of
                # 180 at 1.2 s asks for full stick, which the camera turns at 146 deg/s, about 175 deg.
                return (
                    "foot_stuck",
                    [_call("look", duration=1, angle=60), _call("walk_road", duration=30)],
                    "Hier komme ich nicht weiter, ich versuche eine neue Richtung.",
                )
            if failed == "walk_road" and reason == "no-road":
                return (
                    "foot_explore_roadless",
                    _explore(),
                    "Keine Straße auf der Karte, ich halte die Kompassrichtung.",
                )
            return (
                "failed_skill",
                [_walk()],
                "Der letzte Versuch ist gescheitert, ich suche einen anderen Weg.",
            )

        # A class with no rule of its own for this situation is answered by the rules below.
        selected = self._intent_rule(request, mode, cars)
        if selected is not None:
            return selected

        text = _text(" ".join([request.objective, request.help, request.subtitle, request.banner]))
        restart = bool(kinds & {"failure", "pass", "menu_closed", "screen_cleared"}) or bool(
            re.search(r"fehlgesch|mission failed|retry|erneut versuchen|wiederholen", text)
        )
        # head_prompt.txt:25-33 and 49-56: recompute from current observations.
        if mode == "vehicle":
            if request.minimap.get("route") in {"yellow", "purple"}:
                return (
                    "vehicle_route",
                    [_call("drive_route", duration=60)],
                    "Die Route ist sichtbar, ich folge ihr.",
                )
            last = request.last_skill or {}
            if last.get("name") == "drive_route" and last.get("status") == "done":
                # The route ended where it led. What the place wants, a marker to walk into or a
                # cutscene about to start, is in the picture and not in the readings.
                return None
            return (
                "vehicle_waypoint",
                self._trip(request),
                "Eine Route fehlt, ich setze ein neues Ziel auf der Karte.",
            )

        if mode == "on_foot":
            blips = request.minimap.get("blips", [])
            # A rim marker gives a bearing, not a nearby destination. Without an
            # objective only markers inside the map should interrupt free roam.
            colors = {blip.get("color") for blip in blips if request.objective.strip() or not _rim_blip(blip)}
            # head_prompt.txt:42-48: in a mission fight red blips only, and only when the game orders
            # it; stars and low health have been answered above. A red pinned to the map's border is
            # out of range at an unknown distance, and fight would fire along its bearing at nothing.
            # Without a red in range the rules below stay in charge: the minimap shows the same red
            # whichever way the camera faces, so looking finds nothing, while walking to what the
            # game marks brings the enemies into range, and with nothing marked the picture decides.
            # head_prompt.txt:35-41 and docs/LOG.md:64: red alone is not an
            # instruction, nor proof of a gun in hand. Without an order to take
            # somebody out, leave combat selection to the fallback.
            if "red" in colors:
                if self.objective_class == "take_out" and not colors & {"yellow", "blue"}:
                    # Told to take somebody out, and every red is out of range (one in range was
                    # answered with the fight above; fight itself ends on a red it cannot reach):
                    # with nothing else marked the figure goes towards the red.
                    return (
                        "take_out_approach",
                        [_call("walk_to", color="red", duration=10, sprint=True)],
                        "Die Ziele sind noch zu weit weg, ich laufe hin.",
                    )
                return None
            targets = (
                colors if request.objective.strip() else {blip.get("color") for blip in self.stable_blips}
            )
            if not request.objective.strip():
                # Without an order of the game a marker that a walk has just arrived at is not walked
                # to again: the figure stands at it. On 13 November, 19:57, Michael stood before his
                # own car, whose marker is blue, with the car in the middle of the picture, and
                # walked to that marker 167 times in 55 seconds, each walk done at once as arrived,
                # and then went off along the road without the car. What stands at a marker reached
                # is for the rules below: a car in the picture is taken.
                now = self.goals.now(request)
                targets = {c for c in targets if now - self.reached.get(c, -math.inf) > REACHED_SECONDS}
            for color in ("yellow", "blue"):
                if color in targets:
                    return (
                        "foot_target",
                        [_call("walk_to", color=color, duration=10, sprint=False)],
                        "Ein Ziel ist auf der Karte markiert, ich gehe dorthin.",
                    )
            if restart:
                return (
                    "restart_on_foot",
                    [_walk()],
                    "Der vorige Abschnitt ist vorbei, ich orientiere mich neu.",
                )
            if not request.objective.strip() and not targets and cars:
                # head_prompt.txt:30-33: on foot with nothing to do, go for a drive in one plan.
                return (
                    "foot_drive",
                    [_call("enter_vehicle", duration=25, kind="any"), *self._trip(request)],
                    "Nichts hält mich hier, ich nehme mir ein Fahrzeug und fahre los.",
                )
            if not request.objective.strip() and not targets and not cars:
                # Nothing marked and no car: a road is where cars come by. walk_road fails no-road
                # when the map shows none, and the rule above then looks and walks as before.
                return (
                    "foot_explore",
                    [_call("walk_road", duration=30)],
                    "Ein markiertes Ziel ist nicht zu sehen, ich gehe zur nächsten Straße.",
                )
        return None
