"""Observable mission rules, with an injectable head for ambiguous situations."""

import re
import unicodedata
from collections import Counter

from .contract import ARROW_XY
from .head import Head, HeadRequest, HeadResponse, parse_response
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


# Seconds of one fight before the rules look again; the first attempt at the Vagos in
# recordings/20261110-093238 lasted 23 s before it failed.
FIGHT_SECONDS = 20


def _call(name: str, **args: object) -> dict:
    return {"name": name, "args": args}


def _walk(*, sprint: bool = False) -> dict:
    return _call("walk", duration=5, x=0, y=-1, sprint=sprint)


def _explore() -> list[dict]:
    # pilot/20261110-231512/head.jsonl:2: look and walk through unmarked free roam; do not
    # reproduce the older wait loop.
    return [
        _call("look", duration=0.8, angle=-55),
        _walk(),
        _call("look", duration=0.5, angle=20),
        _walk(),
    ]


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

    def __init__(self, fallback: Head | None = None) -> None:
        self.fallback = fallback
        self.counts: Counter[str] = Counter()
        self.last_rule: str | None = None
        self.sought_mission = False
        self.letterless = 0
        self.objective_class: str | None = None
        self.pending_class: str | None = None
        self.pending_reads = 0

    def decide(self, request: HeadRequest) -> HeadResponse:
        self._update_intent(request)
        selected = self._rule(request)
        if selected is None:
            if self.fallback is not None:
                self.last_rule = "fallback"
                self.counts[self.last_rule] += 1
                return self.fallback.decide(request)
            selected = (
                "moving_default",
                [_walk(sprint=bool(_wanted(request)))],
                "Ein eindeutiges Ziel ist gerade nicht erkennbar, ich gehe weiter.",
            )
        rule, plan, sentence = selected
        # head_prompt.txt:58-60: never immediately repeat a failed skill call.
        failed = self._failed(request)
        if failed and plan[0]["name"] == failed and rule not in {"screen_wait", "screen_reflex"}:
            rule += "_after_failure"
            plan = [_call("look", duration=0.5, angle=45), *plan]
            sentence = "Der letzte Versuch ist gescheitert, ich orientiere mich zuerst neu."
        response = parse_response({"plan": plan, "sentence": sentence})
        self.last_rule = rule
        self.counts[rule] += 1
        self.sought_mission = any(call.args.get("target") == "mission" for call in response.plan)
        return response

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
            if mode == "vehicle" and request.minimap.get("route") not in {"yellow", "purple"}:
                return "objective_escape_vehicle", _route("away"), "Ich fahre aus dem Gebiet."
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
        # Going somewhere, bringing, following, picking up and using are answered by the route and
        # the marked target as the rules below do for any objective; protecting, destroying and
        # sneaking have no skill of their own yet and get the same.
        return None

    def close(self) -> None:
        close = getattr(self.fallback, "close", None)
        if close is not None:
            close()

    def _destination(self, request: HeadRequest) -> str:
        """Where a new route goes: to a mission letter, because the story lies there, unless the
        map has just shown none (head_prompt.txt:28-30)."""
        if self.sought_mission and self._failed(request) == "set_waypoint":
            self.letterless = self.LETTERLESS_ROUTES
        if self.letterless:
            self.letterless -= 1
            return "away"
        return "mission"

    @staticmethod
    def _failure_reason(request: HeadRequest) -> str | None:
        if request.last_skill and request.last_skill.get("status") == "failed":
            return request.last_skill.get("reason")
        for event in reversed(request.events):
            if event.get("kind") == "skill_failed":
                return (event.get("skill") or {}).get("reason")
        return None

    @staticmethod
    def _failed(request: HeadRequest) -> str | None:
        if request.last_skill and request.last_skill.get("status") == "failed":
            return request.last_skill.get("name")
        for event in reversed(request.events):
            if event.get("kind") == "skill_failed":
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
        if wanted:
            if mode == "vehicle":
                # A waypoint set by the pilot is still up: keep driving instead of opening the map
                # again with the police behind.
                if request.minimap.get("route") == "purple":
                    return (
                        "wanted_vehicle_route",
                        [_call("drive_route", duration=60)],
                        "Die Polizei sucht mich, ich fahre weiter aus dem Suchgebiet.",
                    )
                return (
                    "wanted_vehicle",
                    _route("away"),
                    "Die Polizei sucht mich, ich fahre aus dem Suchgebiet.",
                )
            if mode == "on_foot":
                if cars:
                    return (
                        "wanted_on_foot_vehicle",
                        [_call("enter_vehicle", duration=25, kind="any"), *_route("away")],
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

        if self._failed(request):
            if mode == "unknown":
                return None
            if mode == "vehicle":
                self._destination(request)
                return (
                    "failed_vehicle_skill",
                    _route("away"),
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
                    [_call("look", duration=1.2, angle=180), _call("walk_road", duration=15)],
                    "Hier komme ich nicht weiter, ich drehe um.",
                )
            if failed == "walk_road" and reason == "no-road":
                return (
                    "foot_explore_roadless",
                    _explore(),
                    "Keine Straße auf der Karte, ich schaue mich um und gehe weiter.",
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
                _route(self._destination(request)),
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
                return None
            for color in ("yellow", "blue"):
                if color in colors:
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
            if not request.objective.strip() and not colors and cars:
                # head_prompt.txt:30-33: on foot with nothing to do, go for a drive in one plan.
                return (
                    "foot_drive",
                    [_call("enter_vehicle", duration=25, kind="any"), *_route(self._destination(request))],
                    "Nichts hält mich hier, ich nehme mir ein Fahrzeug und fahre los.",
                )
            if not request.objective.strip() and not colors and not cars:
                # Nothing marked and no car: a road is where cars come by. walk_road fails no-road
                # when the map shows none, and the rule above then looks and walks as before.
                return (
                    "foot_explore",
                    [_call("walk_road", duration=15)],
                    "Ein markiertes Ziel ist nicht zu sehen, ich gehe zur nächsten Straße.",
                )
        return None
