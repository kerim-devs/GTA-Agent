"""Real capture regressions plus failures that must not stop the conductor."""

from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from pilot.contract import Hud
from pilot.hud import read

FIXTURES = Path(__file__).resolve().parents[2] / "lab/hud/fixtures"


def frame(name: str) -> np.ndarray:
    bgr = cv2.imread(str(FIXTURES / f"{name}.png"))
    assert bgr is not None, name
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


@pytest.mark.parametrize(
    ("name", "screen"),
    [
        ("wifi-01013", "game"),
        ("wifi-08196", "pause"),
        ("wifi-08243", "map"),
        ("wifi-00332", "weapon_wheel"),
        ("wifi-03424", "phone"),
        ("wifi-00781", "failed"),
        ("wifi-07317", "passed"),
        ("wifi-00913", "loading"),
    ],
)
def test_real_screen_classes(name, screen):
    result = read(frame(name))
    assert result.screen == screen
    assert result.wanted is None
    assert result.wanted_flashing is False


@pytest.mark.parametrize(
    ("name", "health"),
    [
        ("wifi-01013", 1.0),
        ("wifi-13181", 1.0),
        ("wifi-00179", 0.58),
        ("wifi-00545", 0.27),
        ("wifi-00332", 0.33),
        ("wifi-02708", 0.4),
        ("wifi-03424", 0.5),  # Vehicle minimap while the phone is open.
        ("clean1-00818", 0.55),
        ("clean2-01932", 0.55),
    ],
)
def test_real_health_fractions(name, health):
    assert read(frame(name)).health == pytest.approx(health, abs=0.05)


def test_empty_armour_is_not_full_just_because_track_is_blue():
    result = read(frame("wifi-01013"))
    assert result.armour == pytest.approx(0, abs=0.05)
    assert result.special == pytest.approx(1, abs=0.05)


@pytest.mark.parametrize("name", ["wifi-00781", "wifi-08196", "wifi-08243", "wifi-12601", "wifi-00913"])
def test_real_absent_bars(name):
    result = read(frame(name))
    assert (result.health, result.armour, result.special) == (None, None, None)


def test_damaged_red_bar_does_not_invent_zero_health():
    assert read(frame("wifi-00679")).health is None


def test_real_marker_occlusion_and_wifi_damage_abstain():
    assert read(frame("clean2-07360")).health is None
    result = read(frame("wifi-02869"))
    assert result.health is None
    assert result.screen == "game"


def test_damaged_menu_falls_back_to_game():
    # Visible menu fragments have no intact title anchor; never guess from tint.
    assert read(frame("wifi-08221")).screen == "game"


@pytest.mark.parametrize(
    "bad",
    [
        None,
        "bad frame",
        [],
        np.zeros((170, 260, 3), np.uint8),
        np.zeros((720, 1280), np.uint8),
        np.zeros((720, 1280, 4), np.uint8),
        np.full((720, 1280, 3), np.nan),
        np.empty((0, 0, 3), np.uint8),
    ],
)
def test_invalid_input_never_raises(bad):
    assert read(bad) == Hud()


def test_black_white_noise_and_missing_bar_pixels():
    assert read(np.zeros((720, 1280, 3), np.uint8)) == Hud(screen="loading")
    assert read(np.full((720, 1280, 3), 255, np.uint8)) == Hud()
    damaged = np.random.default_rng(15).integers(0, 256, (720, 1280, 3), dtype=np.uint8)
    assert read(damaged) == Hud()
    missing = frame("wifi-01013")
    missing[670:686, 60:250] = 0
    assert read(missing) == Hud()
    missing = frame("wifi-01013")
    missing[670:686, 60:157] = 0
    result = read(missing)
    assert result.health is None
    assert result.armour == pytest.approx(0, abs=0.05)


def test_stale_text_cannot_stop_normal_play():
    ordinary = frame("wifi-01013")
    for banner in ("MISSION FEHLGESCHLAGEN", "bestanden", "WASTED", "BUSTED", "Karte"):
        text = SimpleNamespace(banner=banner, phone_menu="Kontakte")
        assert read(ordinary, text).screen == "game"
    assert read(frame("wifi-00781"), SimpleNamespace(banner="bestanden")).screen == "failed"
    assert read(frame("wifi-07317"), SimpleNamespace(banner="fehlgeschlagen")).screen == "passed"


def test_repeat_calls_are_pure_and_accept_read_only_pixels():
    pixels = frame("wifi-01013")
    original = pixels.copy()
    pixels.flags.writeable = False
    expected = read(pixels)
    read(frame("wifi-00781"))
    read(frame("wifi-03424"))
    assert read(pixels) == expected
    np.testing.assert_array_equal(pixels, original)
