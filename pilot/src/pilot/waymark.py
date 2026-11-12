"""What a walk to a point takes from the minimap on foot: the waypoint marker and the roads.

On foot the game draws no route to a waypoint, only its marker, a purple disc with a white pattern:
inside the map when the point is near, held on the map's rim in its direction when it is far.
`minimap.read` knows yellow, blue and red discs and not this one, so it is read here from the same
crop. The way there is the walker's own to find, and the map's white bands are the roads it has.
"""

from __future__ import annotations

import heapq
import math

import cv2
import numpy as np

from .contract import ARROW_XY, Blip

# Measured on two console frames of 12 November (night and dawn, the marker on the left rim and in
# the top right corner): hue 136 and 137, saturation 118 and 120, value 135 and 144, one component of
# 67 and 73 pixels in a box of 14 x 12 and 14 x 13, with 22 and 24 white pixels of its pattern inside.
_HUE = (127, 152)
_SAT_MIN, _VAL_MIN = 80, 85
_SIDE = (9, 17)
_AREA = (35, 120)
_WHITE_MIN = 8
# By day over bright ground, and on the bottom rim where the marker lies half over the three bars,
# that purple falls into the marker's four lobes (frames of 23:04 and 23:08: pieces of 6 to 21
# pixels, 40 and 45 together) and a wider purple gives one component of 70 and 71 pixels in a box
# of 13 x 12 and 14 x 12. So where the first look finds nothing, the wider one is taken, with at
# least twenty pixels of the first purple inside it.
_LOW_HUE = (120, 160)
_LOW_SAT_MIN, _LOW_VAL_MIN = 50, 60
_LOW_SIDE = (9, 19)
_LOW_AREA = (35, 130)
_LOW_CORE = 20
# Where a marker can lie: the map with the few pixels a marker on its rim sticks out.
_X0, _X1, _Y0, _Y1 = 24, 226, 18, 152
# The centre of a marker held on the rim sat at x 35.3 on the left, x 211.9 on the right and y 29.8
# at the top; the game's own north marker sat at y 143 at the bottom.
_RIM = (38.0, 209.0, 33.0, 139.0)


def _disc(purple, side, area, enough):
    """The centre of the largest purple component of a marker's size, in the region's pixels."""
    count, _, stats, centers = cv2.connectedComponentsWithStats(purple, 8)
    best = None
    for index in range(1, count):
        x, y, width, height, pixels = (int(v) for v in stats[index])
        if not (side[0] <= width <= side[1] and side[0] <= height <= side[1]):
            continue
        if not area[0] <= pixels <= area[1]:
            continue
        if not enough(slice(y, y + height), slice(x, x + width)):
            continue
        if best is None or pixels > best[0]:
            best = (pixels, float(centers[index][0]), float(centers[index][1]))
    return None if best is None else best[1:]


def find_waypoint(crop) -> Blip | None:
    """The waypoint marker in a HUD crop as a purple blip relative to the arrow, or None."""
    try:
        if not isinstance(crop, np.ndarray) or crop.shape != (170, 260, 3) or crop.dtype != np.uint8:
            return None
        region = np.ascontiguousarray(crop[_Y0:_Y1, _X0:_X1])
        hue, sat, value = cv2.split(cv2.cvtColor(region, cv2.COLOR_RGB2HSV))
        purple = (hue >= _HUE[0]) & (hue <= _HUE[1]) & (sat >= _SAT_MIN) & (value >= _VAL_MIN)
        found = _disc(
            purple.astype(np.uint8),
            _SIDE,
            _AREA,
            lambda rows, cols: int(((sat[rows, cols] < 60) & (value[rows, cols] > 180)).sum()) >= _WHITE_MIN,
        )
        if found is None:
            low = (
                (hue >= _LOW_HUE[0]) & (hue <= _LOW_HUE[1]) & (sat >= _LOW_SAT_MIN) & (value >= _LOW_VAL_MIN)
            )
            found = _disc(
                low.astype(np.uint8),
                _LOW_SIDE,
                _LOW_AREA,
                lambda rows, cols: int(purple[rows, cols].sum()) >= _LOW_CORE,
            )
        if found is None:
            return None
        cx, cy = found[0] + _X0, found[1] + _Y0
        border = cx <= _RIM[0] or cx >= _RIM[1] or cy <= _RIM[2] or cy >= _RIM[3]
        return Blip("purple", round(cx - ARROW_XY[0], 2), round(ARROW_XY[1] - cy, 2), bool(border))
    except Exception:
        return None


# The map as a coarse grid for finding a way: cells of three pixels over the map's rectangle.
_CELL = 3
_GX0, _GY0, _COLS, _ROWS = 35, 28, 60, 38
_OFF_ROAD = 4.0  # what a step over open ground costs when a step along a road costs one
_LOOK = 5  # cells along the way that the walker aims at
_ARROW_R = 9  # the white arrow hides what it stands on
_NEIGHBOURS = tuple((dy, dx, math.hypot(dy, dx)) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx)


def _roads(crop) -> np.ndarray:
    """The cells of the grid a road runs through: the map's white bands without icons and letters."""
    y1, x1 = _GY0 + _ROWS * _CELL, _GX0 + _COLS * _CELL
    hsv = cv2.cvtColor(np.ascontiguousarray(crop[_GY0:y1, _GX0:x1]), cv2.COLOR_RGB2HSV)
    white = ((hsv[:, :, 1] < 45) & (hsv[:, :, 2] > 195)).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(white, 8)
    long = np.zeros(count, bool)
    for index in range(1, count):
        long[index] = stats[index, cv2.CC_STAT_AREA] >= 80 and max(stats[index, 2], stats[index, 3]) >= 25
    road = long[labels]
    yy, xx = np.mgrid[_GY0:y1, _GX0:x1]
    road[(xx - ARROW_XY[0]) ** 2 + (yy - ARROW_XY[1]) ** 2 < _ARROW_R**2] = True
    return road.reshape(_ROWS, _CELL, _COLS, _CELL).sum(axis=(1, 3)) >= 3


def way_by_road(crop, x: float, y: float) -> tuple[float, bool] | None:
    """Where to walk now to reach the point at (x, y) from the arrow, keeping to the map's roads.

    The point is given as a blip is, in pixels right of and above the arrow, and may lie on the rim.
    Returns the map bearing (0 = up = where the camera looks, clockwise) of the first stretch of the
    cheapest way and whether that stretch runs along a road, or None when the map cannot be read.
    Open ground can be crossed, at four times the cost of a road, so a road is taken while it does
    not lead far round. The map does not tell a building from open ground, so neither does this.
    """
    try:
        if not isinstance(crop, np.ndarray) or crop.shape != (170, 260, 3) or crop.dtype != np.uint8:
            return None
        if not (math.isfinite(x) and math.isfinite(y)):
            return None
        road = _roads(crop)
        cost = np.where(road, 1.0, _OFF_ROAD).tolist()

        def cell(px, py):
            return (
                min(_ROWS - 1, max(0, int((py - _GY0) // _CELL))),
                min(_COLS - 1, max(0, int((px - _GX0) // _CELL))),
            )

        start = cell(*ARROW_XY)
        goal = cell(ARROW_XY[0] + x, ARROW_XY[1] - y)
        if start == goal:
            return None
        # From the point outward, until the arrow's own cell is settled: every cell on the cheapest
        # way from the arrow is settled before it.
        best = [[math.inf] * _COLS for _ in range(_ROWS)]
        toward = {}
        best[goal[0]][goal[1]] = 0.0
        heap = [(0.0, goal)]
        while heap:
            so_far, here = heapq.heappop(heap)
            if here == start:
                break
            if so_far > best[here[0]][here[1]]:
                continue
            step_cost = cost[here[0]][here[1]]
            for dy, dx, length in _NEIGHBOURS:
                ny, nx = here[0] + dy, here[1] + dx
                if 0 <= ny < _ROWS and 0 <= nx < _COLS:
                    total = so_far + length * (step_cost + cost[ny][nx]) / 2
                    if total < best[ny][nx]:
                        best[ny][nx] = total
                        toward[(ny, nx)] = here
                        heapq.heappush(heap, (total, (ny, nx)))
        here, on_road = start, 0
        for step in range(_LOOK):
            here = toward.get(here)
            if here is None:
                return None
            # The first cells lie under the arrow, which hides whether a road is there.
            on_road += step >= _LOOK - 2 and bool(road[here])
            if here == goal:
                break
        dx = _GX0 + (here[1] + 0.5) * _CELL - ARROW_XY[0]
        dy = _GY0 + (here[0] + 0.5) * _CELL - ARROW_XY[1]
        return math.degrees(math.atan2(dx, -dy)), on_road == 2
    except Exception:
        return None
