"""Recorded lower-edge routes and the false positives that must stay rejected."""

from pathlib import Path

import cv2
import pytest

from pilot.minimap import read

FIXTURES = Path(__file__).parent / "fixtures"


def crop(name):
    return cv2.cvtColor(cv2.imread(str(FIXTURES / name)), cv2.COLOR_BGR2RGB)


@pytest.mark.parametrize(
    "session,index",
    [
        ("123938", 1011),
        ("123938", 1038),
        ("123938", 1215),
        ("123938", 1228),
        ("123938", 1269),
        ("123334", 1002),
        ("123334", 1210),
        ("123334", 1384),
        ("123334", 1627),
    ],
)
def test_recorded_lower_edge_route_points_behind(session, index):
    result = read(crop(f"p34-20261111-{session}-{index}.png"))
    assert result.route == "purple"
    assert 90 < abs(result.bearing) <= 180
    assert result.path
    assert result.path[0][1] < 0


@pytest.mark.parametrize("index", [984, 998])
def test_detached_route_can_bend_ahead(index):
    result = read(crop(f"p34-20261111-123938-{index}.png"))
    assert result.route == "purple"
    assert 0 < result.bearing < 90


@pytest.mark.parametrize("index", [1320, 1800, 3600, 5400, 7200])
def test_recorded_pause_and_transition_have_no_route(index):
    result = read(crop(f"p34-20261111-123938-{index}.png"))
    assert result.route == "none"
    assert result.bearing is None
    assert result.path == ()


@pytest.mark.parametrize("index", [2687, 1960, 1780, 691, 2511, 599])
def test_recorded_blips_pink_flash_and_codec_damage_stay_none(index):
    result = read(crop(f"p34-old-{index}.png"))
    assert result.route == "none"
    assert result.bearing is None


@pytest.mark.parametrize("colour", [(200, 90, 240), (240, 220, 30)])
def test_detached_blip_is_not_a_route(colour):
    image = crop("p34-old-2511.png")
    cv2.circle(image, (145, 130), 7, (20, 20, 20), -1)
    cv2.circle(image, (145, 130), 4, colour, -1)
    assert read(image).route == "none"


def test_purple_special_bar_and_its_fringe_are_not_a_route():
    image = crop("p34-old-2511.png")
    cv2.rectangle(image, (171, 143), (214, 150), (200, 90, 240), -1)
    cv2.line(image, (172, 141), (213, 141), (160, 110, 180), 2)
    assert read(image).route == "none"


def test_pink_world_line_spilling_past_lower_map_edge_is_not_a_route():
    image = crop("p34-old-2511.png")
    cv2.line(image, (144, 128), (235, 135), (220, 95, 240), 5)
    assert read(image).route == "none"
