"""Observable mission rules, with an injectable head for ambiguous situations."""

import re
import unicodedata
from collections import Counter

from .head import Head, HeadRequest, HeadResponse, parse_response


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


def _call(name: str, **args: object) -> dict:
    return {"name": name, "args": args}


def _walk(*, sprint: bool = False) -> dict:
    return _call("walk", duration=5, x=0, y=-1, sprint=sprint)


def _route(target: str) -> list[dict]:
    return [
        _call("set_waypoint", target=target, duration=45, direction="any", distance="far"),
        _call("drive_route", duration=60),
    ]


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

    def decide(self, request: HeadRequest) -> HeadResponse:
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
            return (
                "failed_skill",
                [_walk()],
                "Der letzte Versuch ist gescheitert, ich suche einen anderen Weg.",
            )

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
            colors = {blip.get("color") for blip in blips}
            # head_prompt.txt:35-41 and docs/LOG.md:64: red alone is not an
            # instruction, nor proof of a gun in hand. The recorded OCR has
            # no combat imperative, so leave combat selection to the fallback.
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
                # pilot/20261110-231512/head.jsonl:2: look and walk through
                # unmarked free roam; do not reproduce the older wait loop.
                return (
                    "foot_explore",
                    [
                        _call("look", duration=0.8, angle=-55),
                        _walk(),
                        _call("look", duration=0.5, angle=20),
                        _walk(),
                    ],
                    "Ein markiertes Ziel ist nicht zu sehen, ich schaue mich um und gehe weiter.",
                )
        return None
