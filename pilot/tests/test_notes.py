"""Recording-level semantics, independent of native OCR and live services."""

import pytest

from pilot.notes import (
    build_missions,
    consolidate,
    ending,
    intent,
    observed_actions,
    read_sections,
)


def section_data(has_pad=True):
    return {
        "recording": "example",
        "seconds": 200,
        "sample_hz": 10,
        "has_pad": has_pad,
        "sections": [
            {"start": 0, "end": 200, "kind": "foot", "wanted": 2, "route": ["yellow"], "human": 0.5},
        ],
    }


def objective(start=1, last=3, text="Sammle eine Waffe auf."):
    return {"kind": "objective", "text": text, "first": start, "last": last}


def test_consolidates_ocr_variants_but_preserves_cutscene_reappearance():
    rows = [
        {"t": 1, "text": {"objective": "Sammle eine Waffe auf."}},
        {"t": 1.5, "text": {"objective": "Sammle eine Waffe auf"}},
        {"t": 2, "text": {}},
        {"t": 12, "text": {"subtitle": "Hello"}},
        {"t": 15, "text": {"objective": "Sammle eine Waffe auf."}},
    ]
    intervals = [row for row in consolidate(rows) if row["kind"] == "objective"]
    assert [(row["first"], row["last"]) for row in intervals] == [(1, 1.5), (15, 15)]


def test_observed_blank_separates_runs_but_irregular_sampling_does_not():
    rows = [
        {"t": t, "text": {"objective": text}}
        for t, text in ((1, "Go to the car."), (1.9, "Go to the car"), (2.4, ""), (9.9, "Go to the car."))
    ]
    assert [(row["first"], row["last"]) for row in consolidate(rows)] == [(1, 1.9), (9.9, 9.9)]


@pytest.mark.parametrize(
    "text,outcome",
    [
        ("MISSION BESTANDEN", "passed"),
        ("mission fehlgeschlagen", "failed"),
        ("mission Fehlgesch agen", "failed"),
        ("WASTED", "dead"),
    ],
)
def test_banner_ends_mission_before_silence(text, outcome):
    result = build_missions(
        [objective(), {"kind": "banner", "text": text, "first": 10, "last": 12}], section_data()
    )
    mission = result["missions"][0]
    assert (mission["end"], mission["ending"], mission["end_reason"]) == (10, outcome, "banner")


def test_sixty_seconds_without_objective_starts_a_new_mission():
    result = build_missions([objective(), objective(70, 72)], section_data())
    assert len(result["missions"]) == 2
    assert result["missions"][0]["end"] == 63
    assert result["missions"][0]["end_reason"] == "silence"


def test_next_objective_keeps_steps_ordered_and_flattens_route():
    result = build_missions([objective(20, 23, "Schalte die Vagos aus."), objective()], section_data())
    mission = result["missions"][0]
    assert len(mission["steps"]) == 2
    assert mission["steps"][0]["ending"] == "next objective"
    assert mission["steps"][0]["route"] == ["yellow"]
    assert mission["steps"][0]["blips_known"] is False
    assert len(mission["notes"]) <= 600
    assert mission["notes"].index("Sammle") < mission["notes"].index("Schalte")


def test_missing_controller_is_unknown_even_when_section_has_human_share():
    assert build_missions([objective()], section_data())["missions"][0]["steps"][0]["human"] is None
    assert observed_actions([{"t": 50, "src": "human"}], section_data()["sections"], 1, 10) is None


def test_controller_holds_state_and_disambiguates_triggers_per_section():
    sections = [
        {"start": 0, "end": 5, "kind": "drive"},
        {"start": 5, "end": 10, "kind": "foot"},
    ]
    pads = [{"t": 0, "src": "human", "left": [0, -1], "buttons": ["cross"], "l2": 1, "r2": 1}]
    human = observed_actions(pads, sections, 2, 8)
    assert human["observed_seconds"] == 6
    assert human["seconds"] == {
        "driving": 3,
        "walking": 3,
        "running": 3,
        "aiming": 3,
        "firing": 3,
        "looking": 0,
        "map_input": 0,
        "vehicle_input": 0,
        "neutral": 0,
    }


def test_missing_sections_has_actionable_error(tmp_path):
    with pytest.raises(FileNotFoundError, match=r"Missing sections\.json.*run P38 first"):
        read_sections(tmp_path / "sections.json")


def objective_rows(readings):
    return [{"t": t, "text": {"objective": text}} for t, text in readings]


def test_one_objective_misread_over_wifi_is_one_line_with_the_best_reading():
    rows = objective_rows(
        [
            (435.0, "Begib dich nach Vespucci Beach."),
            (435.5, "Begib dich nach Vespucci Beach."),
            (437.0, "Begib dich nach Vesp"),
            (437.5, "Begib dich nBch Vespucci Beach."),
            (438.0, "Begib dich nach Vespucci Beach."),
        ]
    )
    lines = [row for row in consolidate(rows) if row["kind"] == "objective"]
    assert [(row["text"], row["first"], row["last"]) for row in lines] == [
        ("Begib dich nach Vespucci Beach.", 435.0, 438.0)
    ]
    rows = objective_rows(
        [(133.0, "Schalte den GafUI"), (133.5, "Schalte den Gartne"), (134.0, "Schalte den Gai ti ie")]
    )
    assert len([row for row in consolidate(rows) if row["kind"] == "objective"]) == 1


def test_cut_off_reading_never_wins_against_the_full_one():
    rows = objective_rows(
        [(1, "Schlepp den Wagen zum Abschle"), (1.5, "Schlepp den Wagen zum Abschleppplatz.")]
    )
    (line,) = [row for row in consolidate(rows) if row["kind"] == "objective"]
    assert line["text"] == "Schlepp den Wagen zum Abschleppplatz."


def test_two_different_objectives_in_a_row_stay_two_lines():
    rows = objective_rows(
        [
            (1, "Begib dich nach Vespucci Beach."),
            (1.5, "Begib dich nach Vespucci Beach."),
            (2, "Folge Lamar."),
        ]
    )
    lines = [row for row in consolidate(rows) if row["kind"] == "objective"]
    assert [row["text"] for row in lines] == ["Begib dich nach Vespucci Beach.", "Folge Lamar."]


def test_misread_banner_still_ends_a_mission_and_is_one_ending():
    assert ending("besianden") == "passed" and ending("mission Fe") == "failed"
    rows = [
        {"t": 104.0, "text": {"banner": "besianden"}},
        {"t": 105.0, "text": {"banner": "bestsandeTr."}},
        {"t": 106.5, "text": {"banner": "besiandeTr."}},
    ]
    assert len([row for row in consolidate(rows) if row["kind"] == "banner"]) == 1


# Wordings read in the recordings of 11 November, with the class each must get.
SEEN_OBJECTIVES = [
    ("Sammle eine Waffe auf.", "pick_up"),
    ("Schalte die Vagos aus.", "take_out"),
    ("Steig auf das Motorrad.", "enter_vehicle"),
    ("Steig in den Pickup.", "enter_vehicle"),
    ("Steig wieder in den Lieferwagen.", "enter_vehicle"),
    ("Begib dich zu der Autowaschanlage.", "go_to"),
    ("Begib dich nach Vespucci Beach.", "go_to"),
    ("Begib dich zu dem herrenlosen Auto.", "go_to"),
    ("Fahr zum Canyon.", "go_to"),
    ("Mach dich auf zur Kanalmündung.", "go_to"),
    ("Mach dlch auf zur K8nBlmündung.", "go_to"),
    ("Kehr zurück zu Lamar und Stretch.", "return_to"),
    ("Begib dich wieder zu Franklins Haus.", "return_to"),
    ("Folge Lamar.", "follow"),
    ("Verfolge die Yacht.", "follow"),
    ("Warte auf Tonya.", "wait"),
    ("Bring das Auto zum Autohaus.", "bring"),
    ("Schlepp den Wagen zum Abschleppplatz.", "bring"),
    ("Hol das Auto zurück.", "steal"),
    ("Mach das Fahrzeug in der Ablieferzone los.", "use"),
]


@pytest.mark.parametrize("text,cls", SEEN_OBJECTIVES)
def test_every_wording_of_the_recordings_has_its_class(text, cls):
    assert intent(text)["class"] == cls


@pytest.mark.parametrize(
    "text,cls",
    [
        ("Schalte dle Vagos aus.", "take_out"),
        ("Begib dich nBch Vespucci Beach.", "go_to"),
        ("Stelg In den Liefemagen.", "enter_vehicle"),
        ("Schalte den Gartne", "take_out"),
        ("Beglb dlch zum Abschleppwagen.", "go_to"),
        ("Begib dlch wieder zu Franklins Haus.", "return_to"),
        ("Kehr zur(ick zu Michaels Haus.", "return_to"),
        ("Kehr zurüGI)zu Latnar und Stretch.", "return_to"),
        ("8egib dich zu Ammu-Nation.", "go_to"),
        ("-schalte die Vagos aus.", "take_out"),
        ("Begib dich zu Ammu-", "go_to"),
        ("Hol das Au", "steal"),
        ("Mach das Fahrzeug in der Ablleferz", "use"),
        ("Warte au onya.", "wait"),
        ("Folge dem Tenni61ehrer.", "follow"),
        ("Sammle elne Waffe auf.", "pick_up"),
    ],
)
def test_misread_and_cut_off_wordings_keep_their_class(text, cls):
    assert intent(text)["class"] == cls


@pytest.mark.parametrize(
    "text,cls",
    [
        ("Töte den Informanten.", "take_out"),
        ("Erledige die Ballas.", "take_out"),
        ("Eliminiere das Ziel.", "take_out"),
        ("Beseitige die Zeugen.", "take_out"),
        ("Erschieße den Dealer.", "take_out"),
        ("Entkomme der Polizei.", "escape"),
        ("Häng die Polizei ab.", "escape"),
        ("Flieh vor der Polizei.", "escape"),
        ("Verliere die Polizei.", "escape"),
        ("Lauf zur Garage.", "go_to"),
        ("Flieg zum Flughafen.", "go_to"),
        ("Beschütze Lamar.", "protect"),
        ("Zerstöre den Transporter.", "destroy"),
        ("Fotografiere die Yacht.", "use"),
        ("Schleich dich an die Wachen heran.", "sneak"),
        ("Stiehl das Fahrzeug.", "steal"),
        ("Hebe die Tasche auf.", "pick_up"),
    ],
)
def test_synonyms_added_from_knowledge_get_their_class(text, cls):
    asked = intent(text)
    assert (asked["class"], asked["seen"]) == (cls, False)


@pytest.mark.parametrize(
    "text",
    [
        "Schalte das Radio ein.",
        "Schalte zu Michael um.",
        "Das ist doch Wahnsinn, Franklin!",
        "Ich weiß nicht, was du meinst.",
        "Fahren wir nach Vespucci.",
        "Machen wir das morgen.",
        "Sprich mit Lamar.",
        "",
        "...",
    ],
)
def test_unrelated_lines_stay_unknown(text):
    assert intent(text)["class"] == "unknown"


def test_target_is_the_rest_of_the_line_verbatim():
    asked = intent("Begib dlch nBch Vespucci Beach.")
    assert (asked["wording"], asked["matched"], asked["target"]) == (
        "begib dich",
        "Begib dlch",
        "nBch Vespucci Beach.",
    )
    assert intent("Schalte die Vagos aus.")["target"] == "die Vagos aus."
    assert intent("Das ist doch Wahnsinn!")["target"] == "Das ist doch Wahnsinn!"


def test_steps_carry_their_class_and_target():
    step = build_missions([objective(1, 3, "Schalte die Vagos aus.")], section_data())["missions"][0][
        "steps"
    ][0]
    assert (step["intent_class"], step["intent_target"]) == ("take_out", "die Vagos aus.")
