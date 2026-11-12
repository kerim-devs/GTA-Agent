"""The waypoint's marker and the way along the map's roads, on minimap crops of 12 November."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from pilot.contract import ARROW_XY
from pilot.waymark import find_waypoint, way_by_road

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
