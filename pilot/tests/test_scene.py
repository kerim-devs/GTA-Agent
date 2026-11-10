"""Scene transitions use synthetic evidence; OCR needs no source recordings."""

import resource
import sys
from dataclasses import replace

import cv2
import numpy as np
import pytest

from pilot.contract import Reading
from pilot.scene import EventDetector, SceneText, TextReader, VisionUnavailableError


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
    assert [event.kind for event in events] == ["vehicle_exit", "route_vanished"]


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
