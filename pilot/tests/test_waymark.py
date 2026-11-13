"""The waypoint's marker and the way along the map's roads, on minimap crops of 12 November."""

import math
from pathlib import Path

import cv2
import numpy as np
import pytest

from pilot.contract import ARROW_XY
from pilot.waymark import Spot, _buildings, _roads, find_waypoint, way_by_road

LAB = Path(__file__).parents[2] / "lab/walkto"
GROUND = (70, 70, 70)


def crop(name):
    return np.ascontiguousarray(cv2.cvtColor(cv2.imread(str(LAB / f"{name}.png")), cv2.COLOR_BGR2RGB))


def drawn(*bands):
    """A map of plain ground with white bands, each given as (x0, y0, x1, y1) in crop pixels."""
    picture = np.full((170, 260, 3), GROUND, np.uint8)
    for x0, y0, x1, y1 in bands:
        picture[y0:y1, x0:x1] = 255
    return picture


def test_the_marker_is_found_on_the_rim_by_night_and_by_day():
    left = find_waypoint(crop("hud-waypoint-left-rim-night"))
    assert left.color == "purple" and left.border
    assert (left.x, left.y) == pytest.approx((-87.9, -18.4), abs=1.5)
    corner = find_waypoint(crop("hud-waypoint-corner-day"))
    assert corner.border
    assert (corner.x, corner.y) == pytest.approx((88.8, 87.4), abs=1.5)


def test_no_marker_where_none_is_set_and_none_from_what_is_no_crop():
    assert find_waypoint(crop("hud-no-waypoint-night")) is None
    for bad in (None, np.zeros((10, 10, 3), np.uint8), np.zeros((170, 260, 3), np.float32)):
        assert find_waypoint(bad) is None
        assert way_by_road(bad, 10, 10) is None


def test_a_marker_inside_the_map_is_not_on_the_rim():
    picture = crop("hud-no-waypoint-night")
    picture[72:88, 142:158] = crop("hud-waypoint-corner-day")[22:38, 204:220]
    marker = find_waypoint(picture)
    assert marker is not None and not marker.border
    assert (marker.x, marker.y) == pytest.approx((27, 37), abs=3)


def test_the_way_takes_the_road_round_instead_of_the_straight_line():
    # A road straight up from the arrow and then to the right; the point lies up and to the right.
    picture = drawn((118, 40, 129, 117), (118, 40, 200, 51))
    bearing, on_road = way_by_road(picture, 70, 70)
    # Up the road, cutting across its width, and not the 45 degrees of the straight line.
    assert abs(bearing) < 30 and on_road


def test_open_ground_is_crossed_where_no_road_leads_there():
    bearing, on_road = way_by_road(drawn(), 60, 60)
    assert bearing == pytest.approx(45, abs=10) and not on_road
    # A road that leads the other way is left alone.
    bearing, on_road = way_by_road(drawn((118, 117, 129, 142)), 60, 60)
    assert bearing == pytest.approx(45, abs=10) and not on_road


def test_a_road_beside_the_figure_is_stepped_onto_first():
    # The day crop: the figure stands in a yard beside the road that leads up to the marker.
    picture = crop("hud-waypoint-corner-day")
    marker = find_waypoint(picture)
    bearing, on_road = way_by_road(picture, marker.x, marker.y)
    assert 60 <= bearing <= 120 and on_road


def test_no_way_from_the_point_itself_or_to_nowhere():
    assert way_by_road(drawn(), 0, 0) is None
    assert way_by_road(drawn(), float("nan"), 3) is None
    assert ARROW_XY == (123, 117)


def test_over_bright_ground_only_what_is_clearly_brighter_is_a_road():
    # Sand at noon behind the translucent map: the ground itself is nearly white.
    picture = np.full((170, 260, 3), (222, 220, 214), np.uint8)
    picture[40:117, 118:129] = 252
    picture[40:51, 118:200] = 252
    bearing, on_road = way_by_road(picture, 70, 70)
    assert abs(bearing) < 30 and on_road


def test_a_map_that_is_white_all_over_is_not_read_as_roads():
    # Nothing in it is brighter than the rest: open ground, crossed straight.
    bearing, on_road = way_by_road(np.full((170, 260, 3), 255, np.uint8), 60, 60)
    assert bearing == pytest.approx(45, abs=8) and not on_road
    # And where most of a map's cells count as road all the same, it is not planned on.
    striped = drawn(*((x, 28, x + 1, 142) for x in range(35, 215, 3)))
    assert way_by_road(striped, 60, 60) is None


@pytest.mark.parametrize(
    ("x", "y", "bearing"), [(-88, -26, -106.5), (60, 20, 71.6), (0, 80, 0.0), (-70, 70, -45.0)]
)
def test_over_open_ground_the_way_is_the_straight_line(x, y, bearing):
    found, on_road = way_by_road(drawn(), x, y)
    assert found == pytest.approx(bearing, abs=8) and not on_road


def test_the_side_of_a_road_is_taken_when_it_is_asked_for():
    # A road 21 pixels wide straight up from the arrow: down its middle, or along its edge.
    picture = drawn((113, 30, 134, 142))
    middle, _ = way_by_road(picture, 0, 80)
    edge, on_road = way_by_road(picture, 0, 80, side=True)
    assert abs(middle) < 6 and on_road
    assert 10 < abs(edge) < 50


def test_roads_are_read_while_the_map_pulses_red():
    # Frames of 12 November, 23:54, the figure hurt: before, a third of these roads were found.
    for name, cells in (("hud-red-62s-pulse", 400), ("hud-red-66s-pulse", 380)):
        road = _roads(crop(name))
        assert road.sum() >= cells and road.mean() < 0.3


def test_the_maps_buildings_are_read_by_night_and_nothing_is_read_into_bare_or_bright_ground():
    # Sandy Shores by night, in town and at a building's wall: blocks a little lighter than the ground.
    for name in ("hud-night-town", "hud-night-at-a-wall"):
        built = _buildings(crop(name))
        assert 150 <= built.sum() <= 260 and (built & ~_roads(crop(name))).sum() >= 150
    # Open desert has none, and a map that pulses red or lies over sand at noon is not read at all.
    assert _buildings(crop("hud-night-desert")).sum() <= 8
    assert not _buildings(crop("hud-red-62s-pulse")).any()
    assert not _buildings(np.full((170, 260, 3), (222, 220, 214), np.uint8)).any()
    # A road's edge and the map's soft rim are lighter than the ground too, as lines: no blocks.
    lined = drawn()
    lined[60:62, 60:200] = 110
    assert not _buildings(lined).any()


def test_the_way_leads_round_a_building_the_map_shows():
    bearing, _ = way_by_road(drawn(), 0, 60)
    assert abs(bearing) < 6
    # A block between the arrow and the point: the straight line would walk into its wall.
    built = drawn()
    built[70:100, 103:143] = 112
    assert _buildings(built).sum() >= 100
    bearing, on_road = way_by_road(built, 0, 60)
    assert 25 < abs(bearing) < 80 and not on_road


def marked(x, y, ground=100):
    """A bare map with a place's symbol, a black angle, at (x, y) from the arrow."""
    picture = np.full((170, 260, 3), ground, np.uint8)
    cx, cy = ARROW_XY[0] + round(x), ARROW_XY[1] - round(y)
    picture[cy - 5 : cy + 6, cx - 5 : cx - 1] = 0
    picture[cy + 2 : cy + 6, cx - 5 : cx + 6] = 0
    return picture


def test_the_symbol_under_a_removed_marker_is_followed_as_the_map_moves():
    spot = Spot()
    assert spot.follow(marked(27, 37)) is None and spot.last() is None
    assert spot.begin(marked(27, 37), 27, 37)
    for x, y in ((25, 34), (22, 30), (18, 27), (13, 22)):
        assert spot.follow(marked(x, y)) == pytest.approx((x, y), abs=1.5)
    assert spot.last() == pytest.approx((13, 22), abs=1.5) and spot.missed == 0


def test_bare_map_is_not_followed_and_a_symbol_that_is_gone_is_missed_not_guessed():
    spot = Spot()
    # Bare ground turns with the camera: there is nothing here that stays what it is.
    assert not spot.begin(np.full((170, 260, 3), 100, np.uint8), 27, 37)
    assert not spot.begin(marked(27, 37), 60, -20)
    for bad in (None, np.zeros((10, 10, 3), np.uint8)):
        assert not spot.begin(bad, 27, 37)
    assert spot.begin(marked(27, 37), 27, 37)
    bare = np.full((170, 260, 3), 100, np.uint8)
    for misses in (1, 2, 3):
        assert spot.follow(bare) is None and spot.missed == misses
    assert spot.last() == (27, 37)


def test_a_symbol_that_jumped_is_found_again_once_it_is_looked_for_further_out():
    spot = Spot()
    assert spot.begin(marked(27, 37), 27, 37)
    # Fifteen pixels in one tick is more than a tick moves the map: it is looked for near first.
    moved = marked(27, 22)
    found = [spot.follow(moved) for _ in range(4)]
    assert found[:3] == [None, None, None]
    assert found[3] == pytest.approx((27, 22), abs=1.5) and spot.missed == 0


BLOCK = ((83, 112, 163, 122), (83, 42, 93, 122), (153, 42, 163, 122), (83, 42, 163, 52))


def test_of_two_ways_round_a_block_the_one_being_walked_is_kept():
    # The point lies across a block of houses: left round it or right round it, the same length.
    picture = drawn(*BLOCK)
    free, on_road = way_by_road(picture, 0, 70)
    assert abs(abs(free) - 90) < 25 and on_road
    for walked in (-90.0, 90.0, -60.0, 75.0):
        bearing, on_road = way_by_road(picture, 0, 70, keep=walked)
        assert on_road and abs(bearing - math.copysign(90, walked)) < 25
    # A way that is clearly the longer is left all the same: here the right side of the block is gone.
    bearing, on_road = way_by_road(drawn(*BLOCK[:2], BLOCK[3]), 0, 70, keep=90.0)
    assert abs(bearing + 90) < 25 and on_road


def test_a_turn_the_walker_has_reached_is_taken_whatever_way_it_was_walking():
    # Along a road from the left to where another leads up to the point.
    picture = drawn((40, 112, 128, 122), (118, 40, 128, 122))
    for keep in (None, 90.0, 0.0):
        bearing, on_road = way_by_road(picture, 0, 70, keep=keep)
        assert abs(bearing) < 15 and on_road
    # And a way kept to is the same way without it where the cheapest leaves as the walker goes.
    assert way_by_road(picture, 0, 70, keep=20.0) == way_by_road(picture, 0, 70)
    assert way_by_road(picture, 0, 70, keep=float("nan")) == way_by_road(picture, 0, 70)


def test_the_follower_takes_nothing_from_the_maps_rim_or_the_bars_under_it():
    # Found by the second review: begun in the map's lowest rows, the piece held the health bar,
    # which stands still while the map moves, and a walk chased it until its time ran out.
    picture = crop("hud-red-62s-pulse")
    assert not Spot().begin(picture, -25, -21)
    for name in ("hud-red-62s-pulse", "hud-night-desert", "hud-night-town", "hud-waypoint-corner-day"):
        for x in range(-90, 100, 6):
            for y in (-14, -18, -22, -26, 84, 90):
                assert not Spot().begin(crop(name), x, y)
        for y in range(-10, 80, 6):
            for x in (-96, -90, 96, 102):
                assert not Spot().begin(crop(name), x, y)
    # A symbol that slides under the bars is missed there, not found in them.
    spot = Spot()
    assert spot.begin(marked(27, 0), 27, 0)
    assert spot.follow(marked(27, -6)) == pytest.approx((27, -6), abs=1.5)
    assert spot.follow(np.full((170, 260, 3), 100, np.uint8)) is None and spot.missed == 1
