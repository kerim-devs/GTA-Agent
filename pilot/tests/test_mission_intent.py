"""Class decisions and OCR dwell at the mission boundary."""

from dataclasses import replace

import pytest

from pilot.head import HeadRequest, parse_response
from pilot.mission import MissionHead


def observation(objective, **changes):
    fields = dict(
        events=[],
        help="",
        objective=objective,
        subtitle="",
        banner="",
        minimap={"minimap": "flat", "route": "none", "blips": []},
        last_skill=None,
        notebook={},
        jpeg_path="unused.jpg",
        hud={"screen": "game", "wanted": 0, "health": 1},
        objects=[],
    )
    fields.update(changes)
    return HeadRequest(**fields)


class Fallback:
    def __init__(self):
        self.request = None
        self.answer = parse_response(
            {"plan": [{"name": "wait", "args": {"duration": 1}}], "sentence": "Observe."}
        )

    def decide(self, request):
        self.request = request
        return self.answer


@pytest.mark.parametrize(
    "objective,expected,blips,cars",
    [
        ("Begib dich nach Vespucci Beach.", "foot_target", [{"color": "yellow"}], []),
        ("Bring das Auto zum Autohaus.", "foot_target", [{"color": "blue"}], []),
        ("Steig in den Pickup.", "objective_enter_vehicle", [], [{"kind": "truck"}]),
        ("Schalte die Vagos aus.", "take_out_fight", [{"color": "red", "border": False}], []),
        ("Folge Lamar.", "foot_target", [{"color": "blue"}], []),
        ("Entkomme der Polizei.", "objective_escape_foot", [], []),
        ("Hol das Auto zurück.", "objective_steal", [], [{"kind": "car"}]),
        ("Sammle eine Waffe auf.", "foot_target", [{"color": "yellow"}], []),
        ("Warte auf Tonya.", "objective_wait", [], []),
        ("Kehr zurück zu Lamar und Stretch.", "foot_target", [{"color": "blue"}], []),
        ("Beschütze Lamar.", "fallback", [], []),
        ("Zerstöre den Transporter.", "fallback", [], []),
        ("Mach das Fahrzeug in der Ablieferzone los.", "foot_target", [{"color": "yellow"}], []),
        ("Schleich dich an die Wachen heran.", "fallback", [], []),
        ("Sprich mit Lamar.", "fallback", [], []),
    ],
)
def test_decision_for_each_intent(objective, expected, blips, cars):
    fallback = Fallback()
    head = MissionHead(fallback)
    request = observation(
        objective, minimap={"minimap": "flat", "route": "none", "blips": blips}, objects=cars
    )
    answer = head.decide(request)
    assert head.last_rule == expected
    if expected == "fallback":
        assert answer is fallback.answer
        assert fallback.request is request


def test_wait_stays_even_with_route_marker_vehicle_and_previous_failure():
    head = MissionHead()
    request = observation(
        "Warte auf Tonya.",
        minimap={"minimap": "tilted", "route": "yellow", "blips": [{"color": "yellow"}]},
        objects=[{"kind": "car"}],
        last_skill={"name": "drive_route", "status": "failed"},
    )
    assert [call.name for call in head.decide(request).plan] == ["look", "wait"]


@pytest.mark.parametrize(
    "objective",
    [
        "Begib dich nach Vespucci Beach.",
        "Bring das Auto zum Autohaus.",
        "Kehr zurück zu Lamar und Stretch.",
        "Folge Lamar.",
    ],
)
def test_navigation_classes_follow_vehicle_route(objective):
    head = MissionHead()
    answer = head.decide(observation(objective, minimap={"minimap": "tilted", "route": "yellow"}))
    assert answer.plan[0].name == "drive_route"


def test_one_misread_does_not_release_wait_and_two_new_reads_do():
    head = MissionHead(Fallback())
    waiting = observation("Warte auf Tonya.")
    head.decide(waiting)
    head.decide(replace(waiting, objective=""))
    assert head.last_rule == "objective_wait"
    head.decide(waiting)
    changed = observation("Folge Lamar.", minimap={"minimap": "flat", "blips": [{"color": "blue"}]})
    head.decide(changed)
    assert head.last_rule == "objective_wait"
    head.decide(changed)
    assert head.last_rule == "foot_target"


def test_repeated_unknown_reaches_fallback():
    head = MissionHead(Fallback())
    head.decide(observation("Warte auf Tonya."))
    head.decide(observation("unreadable"))
    head.decide(observation("unreadable"))
    assert head.last_rule == "fallback"


@pytest.mark.parametrize("event", ["pass", "failure", "mission_ended"])
def test_mission_boundary_clears_previous_class(event):
    head = MissionHead(Fallback())
    head.decide(observation("Warte auf Tonya."))
    head.decide(observation("unreadable", events=[{"kind": event}]))
    assert head.objective_class == "unknown"


@pytest.mark.parametrize("objective", ["Warte auf Tonya.", "Schalte die Vagos aus."])
@pytest.mark.parametrize(
    "hud,expected",
    [
        ({"screen": "loading", "wanted": 0, "health": 1}, "screen_wait"),
        ({"screen": "game", "wanted": 2, "health": 1}, "wanted_on_foot"),
        ({"screen": "game", "wanted": 0, "health": 0.2}, "low_health_on_foot"),
    ],
)
def test_safety_precedes_intent(objective, hud, expected):
    head = MissionHead()
    head.decide(observation(objective, hud=hud, minimap={"minimap": "flat", "blips": [{"color": "red"}]}))
    assert head.last_rule == expected


@pytest.mark.parametrize(
    "objective,minimap,expected",
    [
        # A class without a rule of its own keeps the route and the marked target of the general rules.
        ("Sammle eine Waffe auf.", {"minimap": "tilted", "route": "yellow", "blips": []}, "vehicle_route"),
        ("Steig in den Pickup.", {"minimap": "tilted", "route": "none", "blips": []}, "vehicle_waypoint"),
        (
            "Beschütze Lamar.",
            {"minimap": "flat", "route": "none", "blips": [{"color": "yellow"}]},
            "foot_target",
        ),
        ("Zerstöre den Transporter.", {"minimap": "tilted", "route": "yellow", "blips": []}, "vehicle_route"),
        # The way out the game marks is taken before the pilot picks one of its own.
        ("Entkomme der Polizei.", {"minimap": "tilted", "route": "yellow", "blips": []}, "vehicle_route"),
        (
            "Entkomme der Polizei.",
            {"minimap": "tilted", "route": "none", "blips": []},
            "objective_escape_vehicle",
        ),
        (
            "Entkomme der Polizei.",
            {"minimap": "flat", "route": "none", "blips": [{"color": "yellow"}]},
            "foot_target",
        ),
    ],
)
def test_class_without_own_rule_falls_to_the_general_rules(objective, minimap, expected):
    fallback = Fallback()
    head = MissionHead(fallback)
    head.decide(observation(objective, minimap=minimap))
    assert head.last_rule == expected
    assert fallback.request is None
