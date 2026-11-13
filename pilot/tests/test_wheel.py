"""Recorded wheel selections, dark locked portraits and confusing non-wheel UI."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from pilot.wheel import Wheel, wheel

ROOT = Path(__file__).resolve().parents[2]


def picture(path):
    frame = cv2.imread(str(ROOT / path))
    assert frame is not None, path
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)


@pytest.mark.parametrize(
    ("file", "highlight"),
    [("wheel-franklin.jpg", "top"), ("wheel-michael.jpg", "left"), ("wheel-refused.jpg", "right")],
)
def test_recorded_selection_uses_colored_wedge_not_current_white_arc(file, highlight):
    reading = wheel(picture(f"lab/story/{file}"))
    assert reading.visible and reading.highlight == highlight
    if highlight == "right":
        assert reading.disabled == frozenset({"left", "top"})


@pytest.mark.parametrize(
    "path",
    [
        "lab/story/bright-673.jpg",
        "lab/story/bright-769.jpg",
        "lab/story/bright-780.jpg",
        "lab/story/bright-881.jpg",
        "pilot/tests/fixtures/screens/remote-day-pause.png",
        "pilot/tests/fixtures/screens/remote-night-pause.png",
        "pilot/tests/fixtures/calibrate/wheel.png",
    ],
)
def test_confusing_nonwheel_screens(path):
    assert wheel(picture(path)) == Wheel()


@pytest.mark.parametrize("frame", [None, "missing", np.zeros((2, 2, 3)), np.zeros((720, 1280, 3))])
def test_invalid_pictures_abstain(frame):
    assert wheel(frame) == Wheel()
