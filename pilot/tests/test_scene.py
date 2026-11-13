"""Scene transitions use synthetic evidence; OCR needs no source recordings."""

import resource
import sys
from dataclasses import replace

import cv2
import numpy as np
import pytest

from pilot.contract import Reading
from pilot.scene import EventDetector, SceneText, TextReader, VisionUnavailableError, _objective


def reading(minimap="flat", route="none", corrupt=False, confidence=0.9):
    return Reading(minimap, route, None, None, None, corrupt, confidence)


def feed(detector, start, stop, fact, text=None):
    events = []
    for step in range(start, stop):
        events.extend(detector.update(fact, step / 2, text=text))
    return events


def test_stable_scene_and_typing_subtitles_are_quiet():
    detector = EventDetector()
    for i in range(100):
        assert not detector.update(reading(), i / 2, text=SceneText(subtitle="Komm mit mir."[: i % 13]))


def test_hud_absence_ignores_flicker_and_corruption_then_returns():
    detector = EventDetector()
    assert not feed(detector, 0, 6, reading())
    assert not detector.update(reading("none", confidence=0), 3)
    assert not detector.update(reading(), 3.5)
    assert not feed(detector, 8, 16, reading("none", corrupt=True, confidence=0))
    events = feed(detector, 16, 24, reading("none", confidence=0))
    assert [event.kind for event in events] == ["hud_absent"]
    assert events[0].timestamp == 10
    events = feed(detector, 24, 30, reading())
    assert [event.kind for event in events] == ["hud_present"]


def test_vehicle_route_colour_and_exit_are_separate():
    detector = EventDetector()
    feed(detector, 0, 6, reading())
    events = feed(detector, 6, 12, reading("tilted", "yellow"))
    assert [event.kind for event in events] == ["vehicle_enter", "route_appeared"]
    events = feed(detector, 12, 18, reading("tilted", "purple"))
    assert [event.kind for event in events] == ["route_colour_changed"]
    events = feed(detector, 18, 24, reading("flat"))
    assert [event.kind for event in events] == ["route_vanished"]
    events = detector.update(reading("flat"), 100, mode="foot")
    assert [event.kind for event in events] == ["vehicle_exit"]


def test_cutscene_does_not_invent_route_loss_or_vehicle_exit():
    detector = EventDetector()
    feed(detector, 0, 6, reading("tilted", "yellow"))
    events = feed(detector, 6, 14, reading("none", confidence=0))
    assert [event.kind for event in events] == ["hud_absent"]
    events = feed(detector, 14, 20, reading("tilted", "yellow"))
    assert [event.kind for event in events] == ["hud_present"]


def test_corrupt_or_low_confidence_reading_cannot_complete_pending_change():
    for invalid in (reading("tilted", corrupt=True), reading("tilted", confidence=0.1)):
        detector = EventDetector()
        feed(detector, 0, 6, reading())
        detector.update(reading("tilted"), 3)
        detector.update(invalid, 3.5)
        assert not detector.update(reading("tilted"), 4)
        assert not detector.update(reading(), 4.5)


def test_changed_text_has_context_and_no_repeated_events_for_minor_ocr_noise():
    detector = EventDetector()
    feed(detector, 0, 6, reading(), SceneText())
    text = SceneText(help="Halte in der Deckung R2 gedrückt.", objective="Folge Lamar.", subtitle="Los!")
    events = feed(detector, 6, 12, reading(), text)
    assert [event.kind for event in events] == ["help_changed", "objective_changed"]
    assert events[0].text == text
    assert not feed(detector, 12, 20, reading(), replace(text, help="Halte in der Deckung RZ gedrückt!"))
    events = feed(detector, 20, 26, reading(), replace(text, banner="MISSION FEHLGESCHLAGEN"))
    assert [event.kind for event in events] == ["banner_appeared"]
    assert not feed(detector, 26, 32, reading(), text)


def test_missing_ocr_and_capture_gap_do_not_count_as_persistence():
    detector = EventDetector()
    feed(detector, 0, 6, reading(), SceneText())
    detector.update(reading(), 3, text=SceneText(help="Folge Lamar."))
    detector.update(reading(), 3.5)
    assert not detector.update(reading(), 4, text=SceneText(help="Folge Lamar."))
    assert not detector.update(reading("tilted"), 10)
    assert not detector.update(reading("tilted"), 20)
    assert not detector.update(reading("tilted"), 30)


def test_invalid_timestamps_and_intervals_rejected():
    detector = EventDetector()
    detector.update(reading(), 1)
    for timestamp in (1, 0, float("nan"), float("inf")):
        with pytest.raises(ValueError, match="timestamps"):
            detector.update(reading(), timestamp)
    with pytest.raises(ValueError, match="intervals"):
        EventDetector(map_seconds=0)


def test_frame_validation_without_vision():
    detector = EventDetector()
    with pytest.raises(ValueError, match="1280x720"):
        detector.update(reading(), 0, frame=np.zeros((10, 10, 3), np.uint8))
    with pytest.raises(ValueError, match="level"):
        TextReader("unknown")


def test_missing_optional_vision_dependency(monkeypatch):
    monkeypatch.setitem(sys.modules, "Vision", None)
    with pytest.raises(VisionUnavailableError):
        TextReader()


def test_vision_recognizes_generated_help_without_recordings():
    pytest.importorskip("Vision")
    frame = np.zeros((720, 1280, 3), np.uint8)
    cv2.putText(frame, "Folge Lamar", (80, 80), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    original = frame.copy()
    try:
        result = TextReader().read(frame, "help")
    except RuntimeError as exc:
        # Framework import can succeed while sandboxed CVPixelBuffer access fails.
        if "-6662" in str(exc) or "failed: None" in str(exc):
            pytest.skip(f"Vision runtime unavailable in this sandbox: {exc}")
        raise
    assert "folge lamar" in result.help.casefold()
    assert result.elapsed_ms > 0
    assert np.array_equal(frame, original)
    reader = TextReader()
    for _ in range(10):
        reader.read(frame)
    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    for _ in range(40):
        reader.read(frame)
    # a full frame is 2.8 MB; a reader that keeps them grows by more than 100 MB here
    assert resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - before < 30e6


def test_judge_foot_cannot_overrule_a_vehicle_map():
    detector = EventDetector()
    detector.update(reading("tilted"), 0, mode="vehicle")
    for t in (0.5, 1, 1.5):
        assert not [
            e for e in detector.update(reading("tilted"), t, mode="foot") if e.kind.startswith("vehicle_")
        ]
    events = detector.update(reading("flat"), 1.6, mode="foot")
    assert [e.kind for e in events] == ["vehicle_exit"]


def test_judge_silence_seeds_map_state_and_debounces_disagreement():
    for mode, matching, opposite, kind in (
        ("foot", "flat", "tilted", "vehicle_enter"),
        ("vehicle", "tilted", "flat", "vehicle_exit"),
    ):
        detector = EventDetector()
        detector.update(reading(opposite), 0, mode=mode)
        for t in (0.1, 0.6, 1.1):
            assert not [e for e in detector.update(reading(matching), t) if e.kind.startswith("vehicle_")]
        for t in (1.2, 1.7, 2.1):
            assert not detector.update(reading(opposite), t)
        events = detector.update(reading(opposite), 2.21)
        assert [e.kind for e in events] == ([kind] if kind == "vehicle_enter" else [])
        if kind == "vehicle_exit":
            events = detector.update(reading("flat"), 2.3, mode="foot")
            assert [e.kind for e in events] == [kind]
        assert "minimap" in events[0].evidence


def test_none_keeps_vehicle_state_and_discards_pending_map_change():
    detector = EventDetector()
    detector.update(reading("flat"), 0, mode="foot")
    detector.update(reading("tilted"), 0.1)
    for t in (0.5, 1, 1.5):
        assert not [
            e for e in detector.update(reading("tilted"), t, mode="none") if e.kind.startswith("vehicle_")
        ]
    for t in (1.6, 2, 2.5):
        assert not detector.update(reading("tilted"), t)
    assert [e.kind for e in detector.update(reading("tilted"), 2.61)] == ["vehicle_enter"]


def test_judge_vehicle_mode_does_not_depend_on_map_integrity():
    detector = EventDetector()
    detector.update(reading("flat"), 0, mode="foot")
    events = detector.update(reading("none", corrupt=True), 0.1, mode="vehicle")
    assert [e.kind for e in events] == ["vehicle_enter"]


def objective_frame(colour):
    frame = np.full((720, 1280, 3), 200, dtype=np.uint8)
    if colour is not None:
        frame[664:680, 600:690] = colour
    return frame


@pytest.mark.parametrize(
    "colour",
    [
        (173, 210, 221),
        (126, 170, 184),
        (160, 233, 233),
        (236, 232, 155),
        (240, 200, 40),
        (30, 220, 220),
        (220, 40, 40),
        (40, 220, 40),
        (180, 135, 110),
        (115, 145, 145),
        (150, 110, 110),
    ],
)
def test_objective_accepts_pale_and_original_target_colours(colour):
    assert _objective(objective_frame(colour), (500, 660, 200, 20), "Steig wieder in den Lieferwagen.")


@pytest.mark.parametrize(
    "text",
    [
        "Begib dich zu dem herrenlosen Auto.",
        "Beglb dlch zum Abschleppwagen.",
        "8egib dich zu Michaels Haus.",
        "Stelg in den Lieferwagen.",
        "Folge Chop.",
        "Schlepp das Auto ab.",
        "Mach den Wagen fertig.",
        "Kehr zu Lamar zurück.",
        "Halte den Wagen an.",
    ],
)
def test_objective_accepts_recorded_instructions_and_bounded_ocr_errors(text):
    assert _objective(objective_frame((160, 233, 233)), (500, 660, 200, 20), text)


@pytest.mark.parametrize(
    "text",
    [
        "Machen wir die Kiste richtig geil.",
        "hafte, Nlgg",
        "hatte, Nlgg",
        "Fahrt ihr noch weiter?",
        "Macht ihr das jetzt?",
        "Nach dem, was er erlebt hat",
        "Das ist dein Auto.",
        "war",
        "",
        "Beglb",
        "Stelg",
        "Beglb " + "x" * 80,
    ],
)
def test_coloured_dialogue_is_not_an_objective(text):
    assert not _objective(objective_frame((160, 233, 233)), (500, 660, 200, 20), text)


def test_instruction_requires_target_colour_inside_its_own_box():
    assert not _objective(objective_frame(None), (500, 660, 200, 20), "Folge Lamar.")
    assert not _objective(objective_frame((160, 233, 233)), (500, 660, 50, 20), "Folge Lamar.")
    assert not _objective(objective_frame((160, 233, 233)), (500, 660, 0, 20), "Folge Lamar.")


@pytest.mark.parametrize("text", ["Go!", "Warte!", "Folge X.", "Begib " + "x" * 80])
def test_exact_instruction_keeps_original_reader_length_tolerance(text):
    assert _objective(objective_frame((30, 220, 220)), (500, 660, 200, 20), text)
