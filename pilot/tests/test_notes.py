"""Recording-level semantics, independent of native OCR and live services."""

import pytest

from pilot.notes import build_missions, consolidate, observed_actions, read_sections


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
        {"t": 2.5, "text": {"subtitle": "Hello"}},
        {"t": 3, "text": {"objective": "Sammle eine Waffe auf."}},
    ]
    intervals = [row for row in consolidate(rows) if row["kind"] == "objective"]
    assert [(row["first"], row["last"]) for row in intervals] == [(1, 1.5), (3, 3)]


def test_observed_blank_separates_runs_but_irregular_sampling_does_not():
    rows = [
        {"t": t, "text": {"objective": text}}
        for t, text in ((1, "Go to the car."), (1.9, "Go to the car"), (2.4, ""), (2.9, "Go to the car."))
    ]
    assert [(row["first"], row["last"]) for row in consolidate(rows)] == [(1, 1.9), (2.9, 2.9)]


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
