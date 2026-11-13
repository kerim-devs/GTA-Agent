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
_BUILT = 40.0  # and a step through a building the map shows: a way round is nearly always cheaper
_FLAT = 0.4  # the share of the map that has the ground's one value where buildings can be read
_MIDDLE = 1.5  # what a step down the middle of a road costs when its side is asked for
_LOOK = 5  # cells along the way that the walker aims at, at the least
_FAR = 12  # cells along the way within which every cell is tried as the end of a straight line
_ARROW_R = 9  # the white arrow hides what it stands on
_TRUST = 0.5  # a map of which more than this share counts as road is not read as a map of roads
_NEIGHBOURS = tuple((dy, dx, math.hypot(dy, dx)) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx)
# Degrees between the first stretches of two ways that make them two ways and not one way's bend.
# The two ways of 13 November left 52 to 75 degrees apart, to either side of the line to the point.
_OTHER = 35.0
_KEPT = 6  # cells round the arrow within which the way being walked leaves in its own direction
# What the way being walked may cost more than the cheapest before it is left: steps along a road.
# The two ways of 13 November differed by 0 to 3.4 while neither was the shorter. A turn the walker
# has reached and would run past costs it the _KEPT cells on and the same back, twelve at least.
_STAY = 5.0


def _turn(degrees: float) -> float:
    """An angle as the shorter turn, from -180 to 180."""
    return (degrees + 180.0) % 360.0 - 180.0


def _roads(crop) -> np.ndarray:
    """The cells of the grid a road runs through: the map's white bands without icons and letters."""
    y1, x1 = _GY0 + _ROWS * _CELL, _GX0 + _COLS * _CELL
    hsv = cv2.cvtColor(np.ascontiguousarray(crop[_GY0:y1, _GX0:x1]), cv2.COLOR_RGB2HSV)
    value = hsv[:, :, 2]
    # The map is translucent. Over sand at noon its ground is nearly white itself (value 210 to 226
    # on the second run of 12 November, where 13 of 56 samples counted over six cells in ten as
    # road) and the roads are 247 and more: a road has to be clearly brighter than the map's middle.
    middle, bright = np.percentile(value, (50, 95))
    floor = max(195.0, middle + 0.4 * (bright - middle))
    # When the figure is hurt the map pulses red and its roads with it: saturation 66 to 74 on
    # the roads and 71 to 80 on the ground between them (12 November, 23:54), where it is 10 and
    # 22 to 28 without the pulse. A road is then told by its brightness alone.
    pale = max(45.0, float(np.median(hsv[:, :, 1])) + 15.0)
    white = ((hsv[:, :, 1] < pale) & (value > floor)).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(white, 8)
    long = np.zeros(count, bool)
    for index in range(1, count):
        long[index] = stats[index, cv2.CC_STAT_AREA] >= 80 and max(stats[index, 2], stats[index, 3]) >= 25
    road = long[labels]
    yy, xx = np.mgrid[_GY0:y1, _GX0:x1]
    road[(xx - ARROW_XY[0]) ** 2 + (yy - ARROW_XY[1]) ** 2 < _ARROW_R**2] = True
    return road.reshape(_ROWS, _CELL, _COLS, _CELL).sum(axis=(1, 3)) >= 3


def _buildings(crop) -> np.ndarray:
    """The cells of the grid a building stands on, where the map shows its buildings.

    The map draws a building as a block a little lighter than the ground. By night in Sandy Shores
    the ground has value 96 to 112, the blocks 136 to 152 and the roads 232 to 240; by day over a
    dark scene 72 to 96, 104 to 120 and 200 and more. Over sand at noon the ground is 200 to 232
    itself and the blocks cannot be told from it, and over a scene of light and shadow the ground
    has no one value at all: there this reads nothing, and the way is planned as over open ground.
    """
    y1, x1 = _GY0 + _ROWS * _CELL, _GX0 + _COLS * _CELL
    hsv = cv2.cvtColor(np.ascontiguousarray(crop[_GY0:y1, _GX0:x1]), cv2.COLOR_RGB2HSV)
    value = hsv[:, :, 2].astype(np.int32)
    none = np.zeros((_ROWS, _COLS), bool)
    bins = np.bincount((value // 8).ravel(), minlength=32)
    ground = int(bins[:24].argmax()) * 8 + 4
    flat = float(bins[max(0, ground // 8 - 1) : ground // 8 + 2].sum()) / value.size
    if ground > 150 or flat < _FLAT:
        return none
    grey = (hsv[:, :, 1] < 45) & (value >= ground + 20) & (value <= min(ground + 70, 190))
    lighter = grey.astype(np.uint8)
    lighter = cv2.morphologyEx(lighter, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(lighter, 8)
    block = np.zeros(count, bool)
    for index in range(1, count):
        width, height, area = (int(stats[index, key]) for key in (2, 3, 4))
        # A block is filled and no larger than a block: the soft rim of the map and the edges of
        # roads are lighter than the ground too, as thin lines.
        block[index] = 16 <= area <= 1500 and area >= 0.45 * width * height and min(width, height) >= 4
    built = block[labels]
    return built.reshape(_ROWS, _CELL, _COLS, _CELL).sum(axis=(1, 3)) >= 5


def near_place(crop):
    """A small outlined symbol beside the arrow, before a walk has taken its first step.

    The three barber starts show 19..37 dark and 23..28 white pixels in a small icon
    just above the arrow. Roads are large components; the arrow alone is too narrow.
    This is a proximity hint, not a claim about which business the symbol names.
    """
    if not isinstance(crop, np.ndarray) or crop.shape != (170, 260, 3):
        return None
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    count, _, stats, centres = cv2.connectedComponentsWithStats((gray < 65).astype(np.uint8), 8)
    for index in range(1, count):
        x, y, width, height, area = stats[index]
        dx, dy = centres[index] - np.array(ARROW_XY)
        if not (8 <= width <= 18 and 8 <= height <= 18 and 16 <= area <= 100):
            continue
        if not (3 <= math.hypot(dx, dy) <= 14 and y < ARROW_XY[1] - 6):
            continue
        if np.count_nonzero(gray[y : y + height, x : x + width] > 175) >= 18:
            return float(dx), float(-dy)
    return None


def blocked_start(crop, toward):
    """Whether the first few map pixels of a planned step cut a visible building."""
    if not isinstance(crop, np.ndarray) or crop.shape != (170, 260, 3):
        return False
    buildings = _buildings(crop)
    hits = 0
    for distance in (7, 10, 13, 16, 19):
        x = int((ARROW_XY[0] + toward[0] * distance - _GX0) // _CELL)
        y = int((ARROW_XY[1] + toward[1] * distance - _GY0) // _CELL)
        if 0 <= x < _COLS and 0 <= y < _ROWS:
            hits += bool(buildings[y, x])
    return hits >= 2


def _centre(cell) -> tuple[float, float]:
    """A cell's centre in pixels right of and below the arrow."""
    return _GX0 + (cell[1] + 0.5) * _CELL - ARROW_XY[0], _GY0 + (cell[0] + 0.5) * _CELL - ARROW_XY[1]


def _straight(start, end):
    """The cells a straight line from one cell to another passes, one for each step, the first left out."""
    steps = max(abs(end[0] - start[0]), abs(end[1] - start[1]))
    return [
        (
            round(start[0] + (end[0] - start[0]) * index / steps),
            round(start[1] + (end[1] - start[1]) * index / steps),
        )
        for index in range(1, steps + 1)
    ]


def _search(cost, start, goal):
    """What the cheapest way to the goal costs from every cell that is nearer it than the start, and
    each such cell's next cell on that way. Outward from the goal, until the start's cell is settled."""
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
    return best, toward


def _first_stretch(cost, road, start, goal):
    """(map bearing, along a road, cost of the whole way) for the cheapest way, or None without one."""
    best, toward = _search(cost, start, goal)
    way = [start]
    while way[-1] != goal:
        following = toward.get(way[-1])
        if following is None:
            return None
        way.append(following)
    # A way over cells bends in steps of 45 degrees. The walker aims at the furthest cell of it
    # that a straight line reaches at no more cost than the way itself: over open ground that
    # is the point, on a road the next bend.
    aim = way[min(_LOOK, len(way) - 1)]
    whole = best[start[0]][start[1]]
    last = len(way) - 1
    for index in [*range(last, _FAR + 3, -4), *range(min(last, _FAR + 3), _LOOK, -1)]:
        line, before, spent = _straight(start, way[index]), start, 0.0
        length = math.hypot(way[index][0] - start[0], way[index][1] - start[1]) / len(line)
        for here in line:
            spent += length * (cost[before[0]][before[1]] + cost[here[0]][here[1]]) / 2
            before = here
        if spent <= 1.02 * (whole - best[way[index][0]][way[index][1]]) + 0.5:
            aim = way[index]
            break
    dx, dy = _centre(aim)
    # Under the arrow nothing is seen of the ground: what lies beyond it says whether it is a road.
    beyond = [here for here in _straight(start, aim) if math.hypot(*_centre(here)) > _ARROW_R]
    on_road = bool(beyond) and sum(bool(road[here]) for here in beyond) >= 0.6 * len(beyond)
    return math.degrees(math.atan2(dx, -dy)), on_road, whole


def way_by_road(
    crop, x: float, y: float, *, side: bool = False, keep: float | None = None
) -> tuple[float, bool] | None:
    """Where to walk now to reach the point at (x, y) from the arrow, keeping to the map's roads.

    The point is given as a blip is, in pixels right of and above the arrow, and may lie on the rim.
    Returns the map bearing (0 = up = where the camera looks, clockwise) of the first stretch of the
    cheapest way and whether that stretch runs along a road, or None when the map cannot be read as
    a map of roads. Open ground can be crossed, at four times the cost of a road, so a road is taken
    while it does not lead far round. With `side` the middle of a road costs more than its side.
    Where the map shows its buildings, a step through one costs forty times a road's.

    `keep` is the map bearing the walker is on. Round a block two ways cost the same, and which of
    them is the cheaper changes from one look to the next as the camera turns the map: on
    13 November, 00:34, a figure seven seconds along one of them was turned 72 degrees onto the
    other and 71 degrees back a second later, for ways that cost 48.5 and 51.9. A way that leaves
    in another direction than the one being walked is taken only where it is clearly the cheaper.
    """
    try:
        if not isinstance(crop, np.ndarray) or crop.shape != (170, 260, 3) or crop.dtype != np.uint8:
            return None
        if not (math.isfinite(x) and math.isfinite(y)):
            return None
        road = _roads(crop)
        if road.mean() > _TRUST:
            return None
        price = np.where(road, 1.0, _OFF_ROAD)
        price[_buildings(crop) & ~road] = _BUILT
        if side:
            price[cv2.erode(road.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)] = _MIDDLE
        cost = price.tolist()

        def cell(px, py):
            return (
                min(_ROWS - 1, max(0, int((py - _GY0) // _CELL))),
                min(_COLS - 1, max(0, int((px - _GX0) // _CELL))),
            )

        start = cell(*ARROW_XY)
        goal = cell(ARROW_XY[0] + x, ARROW_XY[1] - y)
        if start == goal:
            return None
        found = _first_stretch(cost, road, start, goal)
        if found is None:
            return None
        if keep is not None and math.isfinite(keep) and abs(_turn(found[0] - keep)) > _OTHER:
            # The cheapest way among those that leave the way the walker is going: every cell
            # round the arrow that lies in another direction is closed.
            for dy in range(-_KEPT, _KEPT + 1):
                for dx in range(-_KEPT, _KEPT + 1):
                    ny, nx = start[0] + dy, start[1] + dx
                    if not (dy or dx) or not (0 <= ny < _ROWS and 0 <= nx < _COLS):
                        continue
                    off = _turn(math.degrees(math.atan2(dx, -dy)) - keep)
                    if math.hypot(dy, dx) <= _KEPT and abs(off) > _OTHER:
                        cost[ny][nx] = math.inf
            kept = _first_stretch(cost, road, start, goal)
            if kept is not None and kept[2] <= found[2] + _STAY:
                found = kept
        return found[0], found[1]
    except Exception:
        return None


class Spot:
    """Follows what lies under the waypoint after the game has taken its marker off the map.

    The game removes the marker some thirty map pixels before the figure is there. A waypoint set
    on a place from the legend lies on that place's symbol, which the marker hid and which now
    shows: on 13 November, 00:13, the figure ran on for six seconds by the clock and passed
    Ammu-Nation, whose pistol stood on the map twelve pixels from the arrow as it went by. The
    symbol is followed as a small piece of the map, looked for near where it was last. It stays
    upright while the map turns under it, so the piece taken once is good for the rest of the way.
    Bare map turns with the camera and is not followed: a waypoint on no place is walked to by the
    clock, as before.
    """

    HALF = 8  # the piece is 17 pixels square, a symbol's size
    REACH = 7  # pixels it is looked for around where it last was, and three more for every miss
    FAR = 22  # at the most
    SURE = 0.6  # the correlation below which it has not been found
    INK = 14  # pixels of a symbol's drawing a piece must show: black, or a colour the map has not
    # The piece and every place it is looked for lie inside the map itself: its soft rim is dark
    # and the bars under it are coloured, both pass for a symbol's ink, and both stand still while
    # the map moves. The second review locked a follower on to the bars for as long as it was fed.
    BOX = (_GX0, _GY0, _GX0 + _COLS * _CELL, 138)

    def __init__(self):
        self.piece = None
        self.at = None  # centre in crop pixels
        self.missed = 0

    def _cut(self, crop, cx, cy):
        x0, y0 = round(cx) - self.HALF, round(cy) - self.HALF
        left, top, right, bottom = self.BOX
        if x0 < left or y0 < top or x0 + 2 * self.HALF + 1 > right or y0 + 2 * self.HALF + 1 > bottom:
            return None
        colour = np.ascontiguousarray(crop[y0 : y0 + 2 * self.HALF + 1, x0 : x0 + 2 * self.HALF + 1])
        hsv = cv2.cvtColor(colour, cv2.COLOR_RGB2HSV)
        # The map is grey and white, by day and by night, and red all over only while it pulses.
        ground = float(
            np.median(cv2.cvtColor(crop[_GY0 : _GY0 + _ROWS * _CELL, _GX0:], cv2.COLOR_RGB2HSV)[:, :, 1])
        )
        ink = (hsv[:, :, 2] < 60) | ((hsv[:, :, 1] > max(110.0, ground + 60.0)) & (hsv[:, :, 2] > 90))
        if int(ink.sum()) < self.INK:
            return None
        return cv2.cvtColor(colour, cv2.COLOR_RGB2GRAY)

    def begin(self, crop, x: float, y: float) -> bool:
        """Take the piece of the map at (x, y) from the arrow; False where there is nothing to follow."""
        try:
            if not isinstance(crop, np.ndarray) or crop.shape != (170, 260, 3) or crop.dtype != np.uint8:
                return False
            cx, cy = ARROW_XY[0] + x, ARROW_XY[1] - y
            piece = self._cut(crop, cx, cy)
            if piece is None:
                self.piece = self.at = None
                return False
            self.piece, self.at, self.missed = piece, (float(round(cx)), float(round(cy))), 0
            return True
        except Exception:
            self.piece = self.at = None
            return False

    def follow(self, crop) -> tuple[float, float] | None:
        """Where the piece is now, as a blip's x and y from the arrow, or None where it is not found."""
        try:
            if self.piece is None:
                return None
            if not isinstance(crop, np.ndarray) or crop.shape != (170, 260, 3) or crop.dtype != np.uint8:
                return None
            half, reach = self.HALF, min(self.FAR, self.REACH + 3 * self.missed)
            left, top, right, bottom = self.BOX
            x0 = max(left, round(self.at[0]) - half - reach)
            y0 = max(top, round(self.at[1]) - half - reach)
            x1 = min(right, round(self.at[0]) + half + reach + 1)
            y1 = min(bottom, round(self.at[1]) + half + reach + 1)
            if x1 - x0 < 2 * half + 1 or y1 - y0 < 2 * half + 1:
                self.missed += 1
                return None
            window = cv2.cvtColor(np.ascontiguousarray(crop[y0:y1, x0:x1]), cv2.COLOR_RGB2GRAY)
            scores = cv2.matchTemplate(window, self.piece, cv2.TM_CCOEFF_NORMED)
            _, score, _, where = cv2.minMaxLoc(scores)
            if not math.isfinite(score) or score < self.SURE:
                self.missed += 1
                return None
            self.at = (float(x0 + where[0] + half), float(y0 + where[1] + half))
            self.missed = 0
            return self.at[0] - ARROW_XY[0], ARROW_XY[1] - self.at[1]
        except Exception:
            return None

    def last(self) -> tuple[float, float] | None:
        """Where it was last found, as a blip's x and y from the arrow."""
        return None if self.at is None else (self.at[0] - ARROW_XY[0], ARROW_XY[1] - self.at[1])
