"""The health track as the sign of a figure that has run itself out."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from pilot.breath import Breath, track

LAB = Path(__file__).parents[2] / "lab/walkto"


def frame(name, *, shade=0):
    """A frame that is dark but for the bars cut from the console's picture."""
    picture = np.full((720, 1280, 3), shade, np.uint8)
    bars = cv2.cvtColor(cv2.imread(str(LAB / f"bars-{name}.png")), cv2.COLOR_BGR2RGB)
    picture[670:684, 64:244] = bars
    return picture


GREEN, RED = "green-49s", "red-55s"


def test_the_track_is_read_green_before_the_figure_ran_out_and_red_after():
    assert track(frame(GREEN)) == "green"
    for name in (RED, "red-62s", "red-66s"):
        assert track(frame(name)) == "red"


def test_a_picture_without_the_bars_says_nothing():
    for picture in (np.zeros((720, 1280, 3), np.uint8), np.full((720, 1280, 3), 255, np.uint8)):
        assert track(picture) is None
    assert track(None) is None
    assert track(np.zeros((10, 10, 3), np.uint8)) is None
    assert track(frame(GREEN).astype(np.float32)) is None


def run(breath, name, start, seconds):
    """Feed one picture for a stretch at thirty ticks a second; what the last tick said."""
    answer = None
    for tick in range(round(seconds * 30)):
        answer = breath.sprint(frame(name), start + tick / 30)
    return answer


def test_a_track_that_turns_red_under_the_sprint_ends_it_until_it_has_been_green_again():
    breath = Breath()
    assert run(breath, GREEN, 0, 2) is True
    assert run(breath, RED, 2, 0.5) is True  # a hit flashes for less
    assert run(breath, RED, 2.5, 0.5) is False
    assert run(breath, RED, 3, 5) is False
    assert run(breath, GREEN, 8, Breath.GREEN_FOR - 0.5) is False
    assert run(breath, GREEN, 8 + Breath.GREEN_FOR - 0.5, 1) is True
    assert breath.rests == [pytest.approx((2 + Breath.RED_FOR, 8 + Breath.GREEN_FOR))]
    # and it ends it again the next time
    start = 8 + Breath.GREEN_FOR + 0.5
    assert run(breath, RED, start, 1) is False


def test_a_short_red_flash_does_not_end_the_sprint():
    breath = Breath()
    run(breath, GREEN, 0, 1)
    assert run(breath, RED, 1, 0.4) is True
    assert run(breath, GREEN, 1.4, 1) is True
    assert breath.rests == []


def test_a_track_that_was_never_green_is_red_for_another_reason():
    breath = Breath()
    assert run(breath, RED, 0, 10) is True


def test_a_track_that_stays_red_without_the_sprint_does_not_hold_the_figure_back_for_ever():
    breath = Breath()
    run(breath, GREEN, 0, 1)
    assert run(breath, RED, 1, Breath.REST_MAX) is False
    assert run(breath, RED, 1 + Breath.REST_MAX, 2) is True
    # and is not taken for exhaustion again while it has not been green
    assert run(breath, RED, 3 + Breath.REST_MAX, 20) is True


def test_ticks_without_the_bars_decide_nothing():
    breath = Breath()
    run(breath, GREEN, 0, 1)
    blank = np.zeros((720, 1280, 3), np.uint8)
    for tick in range(60):
        assert breath.sprint(blank, 1 + tick / 30) is True
    run(breath, RED, 3, 1)
    for tick in range(60):
        assert breath.sprint(blank, 4 + tick / 30) is False


def test_a_gap_in_the_ticks_starts_the_counting_again():
    breath = Breath()
    run(breath, GREEN, 0, 1)
    assert run(breath, RED, 1, 0.5) is True
    breath.gap()
    assert breath.sprint(frame(RED), 30) is True
    assert run(breath, RED, 30, 1) is False
