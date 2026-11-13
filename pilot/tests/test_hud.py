"""Real capture regressions plus failures that must not stop the conductor."""

import json
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from pilot.contract import Hud
from pilot.hud import read


def wanted_frame(name):
    path = Path(__file__).resolve().parent / "fixtures" / "wanted" / f"{name}.png"
    bgr = cv2.imread(str(path))
    assert bgr is not None, path
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


@pytest.mark.parametrize(
    ("name", "wanted"),
    [
        ("wifi-10892", 1),
        ("wifi-11483", 1),
        ("wifi-11497", 1),
        ("wifi-11588", 1),
        ("wifi-11835", 2),
        ("wifi-11857", 3),
        ("wifi-12530", 3),
        ("wifi-00377", 0),
        ("wifi-04670", 0),
        ("wifi-10456", 0),
        ("wifi-13012", 0),
        ("wifi-00714", None),
        ("wifi-12277", None),
        ("wifi-12603", None),
        ("wifi-12934", None),
        # A clean cable frame with white sky in the corner: nothing dark in the star row is an
        # empty corner, a dark edge in it that is no star stays unread.
        ("clean1-00060", 0),
        ("clean1-00413", None),
    ],
)
def test_real_wanted_counts_and_abstentions(name, wanted):
    result = read(wanted_frame(name))
    assert result.wanted == wanted
    # Blue silhouettes and a tinted/dim active star do not prove blinking.
    assert result.wanted_flashing is False


@pytest.mark.parametrize("name", ["wifi-12674", "wifi-12745", "wifi-12797"])
def test_real_german_death_banner_and_fade(name):
    pixels = wanted_frame(name)
    assert read(pixels) == Hud(screen="wasted")
    assert read(pixels, SimpleNamespace(banner="AUSSER GEFECHT")) == Hud(screen="wasted")


def test_death_needs_matching_pixels_and_grayscale_scene():
    assert read(wanted_frame("wifi-12603")).screen == "game"
    ordinary = wanted_frame("wifi-10456")
    assert read(ordinary, SimpleNamespace(banner="AUSSER GEFECHT")).screen == "game"
    # Retain the real death glyphs but restore scene colour outside the banner.
    coloured = wanted_frame("wifi-12745")
    coloured[:280] = ordinary[:280]
    coloured[430:] = ordinary[430:]
    assert read(coloured, SimpleNamespace(banner="AUSSER GEFECHT")).screen == "game"


def test_wanted_does_not_bridge_damage_or_remember_previous_frames():
    one = wanted_frame("wifi-10892")
    before = one.copy()
    one.flags.writeable = False
    assert read(one).wanted == 1
    assert read(wanted_frame("wifi-00714")).wanted is None
    assert read(wanted_frame("wifi-11857")).wanted == 3
    assert read(wanted_frame("wifi-10456")).wanted == 0
    assert read(one).wanted == 1
    np.testing.assert_array_equal(one, before)


def test_bright_corner_is_empty_only_without_anything_dark_and_a_missing_star_slot_abstains():
    bright = wanted_frame("wifi-10456")
    bright[30:64, 1119:1219] = 255
    assert read(bright).wanted == 0
    # A lit star always brings its black outline; a dark mark that matches no star is not a zero.
    bright[40:52, 1150:1156] = 0
    assert read(bright).wanted is None
    # The real stars in front of a white sky still count.
    assert read(wanted_frame("wifi-11588")).wanted == 1
    broken = wanted_frame("wifi-11857")
    # A lost rightmost slot must not turn a three-star HUD into two stars.
    broken[34:58, 1195:1219] = 0
    assert read(broken).wanted is None


def test_a_codec_block_edge_through_the_corner_is_not_an_empty_corner():
    blocky = wanted_frame("wifi-10456")
    assert read(blocky).wanted == 0
    # The lower half of the corner comes from another block row: a step along the 16 pixel grid.
    lower = blocky[48:64, 1120:1216].astype(np.int16)
    blocky[48:64, 1120:1216] = np.clip(lower - 80, 0, 255).astype(np.uint8)
    assert read(blocky).wanted is None


def test_death_text_only_confirms_letters_that_are_there():
    smeared = wanted_frame("wifi-12745")
    # Red where the banner sits, in a black and white picture, but no letters.
    noise = np.random.default_rng(7).integers(60, 255, size=(120, 688), dtype=np.uint8)
    smeared[292:412, 296:984] = np.stack((noise, noise // 8, noise // 8), axis=2)
    assert read(smeared, SimpleNamespace(banner="AUSSER GEFECHT")).screen != "wasted"


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
    assert result.wanted == (0 if screen == "game" else None)
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


def test_real_marker_occlusion_abstains():
    assert read(frame("clean2-07360")).health is None


def test_wifi_damage_beyond_a_sharp_end_does_not_hide_it():
    # P15 left this frame unlabelled: a cyan streak of codec damage crosses the empty track. The
    # fill ends sharply at 0.40 left of it, and the 41 frames 2850 to 2890 of the recording read
    # 0.40 or nothing with this reader, 0.38 to 0.42 with the one before it.
    result = read(frame("wifi-02869"))
    assert result.health == pytest.approx(0.4, abs=0.02)
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


SCREEN_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "screens"
SCREEN_EVIDENCE = FIXTURES.parent.parent / "screens"
CABLE_MENUS = [
    ("tour-00120", "pause"),
    ("calibration2-02400", "pause"),
    # Remote Play, 11 November: the two menus the waypoint skill took for the game.
    ("remote-day-pause", "pause"),
    ("remote-night-pause", "pause"),
    ("tour-00360", "map"),
    ("tour-00780", "weapon_wheel"),
    ("tour-01080", "phone"),
    ("tour-01380", "interaction_menu"),
]


def cable_frame(name):
    bgr = cv2.imread(str(SCREEN_FIXTURES / f"{name}.png"))
    assert bgr is not None, name
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


@pytest.mark.parametrize("name,screen", CABLE_MENUS)
def test_cable_menu(name, screen):
    assert read(cable_frame(name)).screen == screen


@pytest.mark.parametrize("name", ["kerim-03000", "kerim-07500", "kerim-12000"])
def test_cable_driving_wanted_and_combat_stay_game(name):
    assert read(cable_frame(name)).screen == "game"


@pytest.mark.parametrize(
    "name,screen",
    [
        *CABLE_MENUS,
        ("wifi-08196", "pause"),
        ("wifi-08243", "map"),
        ("wifi-00332", "weapon_wheel"),
        ("wifi-03424", "phone"),
    ],
)
@pytest.mark.parametrize("background", ["kerim-03000", "kerim-07500", "kerim-12000"])
def test_menu_glyphs_survive_replacing_the_entire_game_background(name, screen, background):
    # Frozen, reviewed foreground masks contain the printed UI glyphs and
    # their outlines. Every other pixel comes from a different real scene.
    menu = frame(name) if name.startswith("wifi") else cable_frame(name)
    mask = cv2.imread(str(SCREEN_EVIDENCE / "masks" / f"{screen}.png"), cv2.IMREAD_GRAYSCALE)
    assert mask is not None
    mask = mask > 0
    composite = cable_frame(background)
    composite[mask] = menu[mask]
    assert read(composite).screen == screen
    # The same scene without those glyphs must never manufacture a menu.
    composite[mask] = 0
    assert read(composite).screen == "game"


def test_interaction_menu_does_not_emit_gameplay_hud():
    result = read(cable_frame("tour-01380"))
    assert result.screen == "interaction_menu"
    assert result.health is result.armour is result.special is result.wanted is None


# The HUD strips of lab/health/: real hits and the false falls the reaction bench found, each a
# stack of 13 by 180 pixel strips (all the bars reader looks at) of the frames a 30 Hz loop reads.
HEALTH = Path(__file__).resolve().parents[2] / "lab/health"
HEALTH_DATA = json.loads((HEALTH / "cases.json").read_text())
CASES = {case["name"]: case for case in HEALTH_DATA["cases"]}
HITS = [name for name, case in CASES.items() if case["kind"] == "hit"]


def case_readings(name):
    """The reader's Hud for every frame of a lab/health case, its strip set into a game frame."""
    (top, bottom), (left, right) = HEALTH_DATA["strip"]["rows"], HEALTH_DATA["strip"]["columns"]
    stack = cv2.cvtColor(cv2.imread(str(HEALTH / f"{name}.png")), cv2.COLOR_BGR2RGB)
    base = frame("clean2-07360")
    out = []
    for k, (index, _) in enumerate(CASES[name]["frames"]):
        pixels = base.copy()
        pixels[top:bottom, left:right] = stack[k * (bottom - top) : (k + 1) * (bottom - top)]
        out.append((index, read(pixels)))
    return out


@pytest.mark.parametrize("name", ["fade-enemy-13", "fade-enemy-15", "fade-enemy-16"])
def test_a_fading_hud_reads_no_health_not_zero(name):
    health = [hud.health for _, hud in case_readings(name)]
    # The bar is full behind the fade; the old reader read 0.0 on it for a third of a second.
    assert all(value is None or value == pytest.approx(0.99, abs=0.01) for value in health)
    assert health[0] is None
    assert health[-1] == pytest.approx(0.99, abs=0.01)


def test_a_dim_band_reads_nothing():
    # The HUD at 45 per cent of its brightness, as on the fades of lab/health/: the armour and
    # special tracks would read empty, and the health fill is too dim to be the fill.
    dim = frame("wifi-01013")
    dim[664:690, 60:250] = (dim[664:690, 60:250] * 0.45).astype(np.uint8)
    result = read(dim)
    assert (result.health, result.armour, result.special) == (None, None, None)
    assert result.screen == "game"


@pytest.mark.parametrize(
    "name",
    ["icon-wanted-07", "icon-calm-walk-20", "icon-calm-walk-26", "p62-hit-01", "p62-hit-02", "p62-hit-03"],
)
def test_an_icon_on_the_bar_does_not_end_it(name):
    level = CASES[name]["level"]
    health = [hud.health for _, hud in case_readings(name)]
    # Where the bar's end is hidden the reader says nothing; it never guesses a shorter bar.
    assert all(value is None or value == pytest.approx(level, abs=0.03) for value in health)
    assert sum(value is not None for value in health) >= len(health) // 3


@pytest.mark.parametrize("name", ["sand-calm-walk-13", "undone-enemy-17"])
def test_a_bright_background_behind_the_track_does_not_shorten_the_bar(name):
    level = CASES[name]["level"]
    health = [hud.health for _, hud in case_readings(name)]
    assert all(value is None or value >= level - 0.03 for value in health)
    assert any(value == pytest.approx(level, abs=0.03) for value in health if value is not None)


@pytest.mark.parametrize("name", HITS)
def test_a_real_hit_is_read_on_its_first_frames(name):
    case = CASES[name]
    first = case["first"][0]
    readings = case_readings(name)
    before = [hud.health for index, hud in readings if index < first]
    after = [hud.health for index, hud in readings if index >= first]
    assert all(value is None or value == pytest.approx(case["before"], abs=0.03) for value in before)
    # The new length is read at once, also under the pale yellow and orange the game paints for a
    # third of a second, and the old one never again; a second hit may follow in the window.
    assert any(value == pytest.approx(case["after"], abs=0.03) for value in after[:3] if value is not None)
    shorter = min([value for value in before if value is not None] or [case["before"]])
    assert all(value is None or value < shorter for value in after)
