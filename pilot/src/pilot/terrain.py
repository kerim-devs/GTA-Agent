"""What the minimap gives a car that flees: where roads leave the arrow, where water lies, where police are.

On the radar a road is a white band and open water a white sheet: the same paint, told apart by width.
Land is the darker grey under both. With stars lit the whole radar flashes red and blue, which tints the
paint without darkening it, so paint is told by brightness with a loose bound on colour. The radar is
translucent, and over sand or concrete in the sun the land under the paint grows pale; where it grows
as pale as paint the reading gives up.

Every reading is in picture degrees as in `contract.py` (0 = up, the way the camera looks; positive to
the right) and crop pixels from the arrow. Each returns None where it is not sure: no minimap, a picture
the stream has damaged, a radar washed out by the world behind it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from .contract import Blip, Reading
from .foot import crop_ok
from .minimap import ACX, ACY, MX0, MX1, MY0, MY1

cv2.setNumThreads(1)

# Paint, roads and water alike, measured on the tilted maps of Kerim's drives (lab/getaway): land lies at
# 85 to 140 in value, up to 170 under the blue flash of the stars, and paint above 200 with a saturation
# under 90 even under the red flash. Over pale ground the land rises, and paint has to stand above it.
PAINT_VALUE = 200
PAINT_SATURATION = 90
# Over sand in the sun the land rises to 180 to 210 in value, but stays saturated (75 to 85) where the
# paint does not (13 to 50): paint stands this far above the land's tenth percentile, and no further
# than the top of the scale allows.
PAINT_STEP = 55
PAINT_CEILING = 240
WASHED_OUT = 190  # a land this pale and grey, sun on concrete, leaves nothing to tell paint by
# ... unless the pale is the sea filling the map (`_open_water`).
OPEN_HUE = (90, 115)
OPEN_SATURATION = (5, 40)
OPEN_GRAIN = 6
OPEN_SHARE = 0.5
# A sheet is water where a disc of this diameter fits into it over this many pixels. Freeways, wide
# junctions and the road under the arrow, widened by the radar's perspective, stay under 28 px across
# (inscribed radius 9.6 to 15 on the sheets that were not water); the sea, the lakes and the water under
# a bridge are wider.
SHEET = 29
SHEET_AREA = 500
# On foot the map is drawn closer: a road is 15 to 25 px wide and a crossing of two holds a disc of 30 to 46
# px (radius 15 to 23 on 16 sheets of on-foot frames that were not water), while the sea off the pier, the
# lakes and the coast hold one of 54 px or more (radius 27 to 48).
SHEET_FOOT = 49
# The wide disc leaves the water beside the pier and along the map's edge out; on foot the sheet is grown
# back into the paint it touches by four pixels a step, as far as the disc's radius.
SHORE_FOOT = 12
# The sea off the pier and the coast on foot are tinted (hue 98 to 105, saturation 18 to 37); the white of
# the roads on foot has a saturation of 2 to 16 and, where higher, another hue (beige, the red flash).
TINT_SATURATION = (12, 45)
# A sheet whose contact with the map's edge goes on outside it this often, as white as paint, is the world.
GLARE_VALUE = 235
GLARE_SATURATION = 40
GLARE_SHARE = 0.7
ROAD_VALUE = 180
ROAD_AREA = 60  # pixels of a piece of band below which it is an icon or a letter
ROAD_LONG = 20  # and its longer side; the house icon is 13 px across
BLIP_SATURATION = 120  # the red, blue and green discs on the map
ARROW_R = 9  # the white arrow itself, never paint
RING_R = 20  # radius of the ring on which a road leaving the arrow is read
CHECK_R = 28  # a road must still be there this far out, so that a stub is no way out
UNDER_R = 16  # paint this close to the arrow is under the car
RUN_GAP = 10.0  # degrees between two crossings of the ring that are still one road
SECTOR = 45.0  # ahead is within this of up; left and right are the quarters beside it
PLAZA = 150.0  # degrees of the outer ring in paint from which the car is on a square, not a road

_Y, _X = np.mgrid[0:170, 0:260]
_DX, _DY = _X - ACX, _Y - ACY
_DIST = np.hypot(_DX, _DY)
_BEARING = np.degrees(np.arctan2(_DX, -_DY))
_INSIDE = (_X >= MX0 + 2) & (_X < MX1 - 2) & (_Y >= MY0 + 2) & (_Y < MY1)
_INSIDE &= _DIST >= ARROW_R
_UNDER = (_DIST >= ARROW_R) & (_DIST <= UNDER_R)
# Pairs of points 3 px inside the map's top, left and right edges and 6 px outside them.
_edge_in, _edge_out = [], []
for _x in range(MX0 + 2, MX1 - 2):
    _edge_in.append((MY0 + 3, _x))
    _edge_out.append((MY0 - 6, _x))
for _y in range(MY0 + 2, MY1):
    _edge_in += [(_y, MX0 + 3), (_y, MX1 - 4)]
    _edge_out += [(_y, MX0 - 6), (_y, MX1 + 5)]
_EDGE_IN = tuple(np.array(_edge_in).T)
_EDGE_OUT = tuple(np.array(_edge_out).T)
_K_SHEET = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (SHEET, SHEET))
_K_SHEET_FOOT = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (SHEET_FOOT, SHEET_FOOT))
_K_SHORE = np.ones((9, 9), np.uint8)
_K3 = np.ones((3, 3), np.uint8)
_K5 = np.ones((5, 5), np.uint8)
_K_BLIP = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13))
_STEP = 2.0
_RING_ANGLES = np.arange(-180.0, 180.0, _STEP)


@dataclass(frozen=True)
class Terrain:
    # Where a road crosses the ring around the arrow: centre bearing and width of each crossing, degrees.
    roads: tuple[tuple[float, float], ...]
    on_road: bool  # road paint under the car
    # Nearest water in crop pixels per 10 degree bin of bearing, from -180 up; None where the map shows
    # none in that direction.
    water: tuple[float | None, ...]
    under_water: bool  # the arrow sits on water

    def road_towards(self, heading: float, within: float) -> float | None:
        """The road bearing closest to `heading`, if one lies within `within` degrees of it. Inside a
        crossing wider than PLAZA the car is on open paint, and `heading` itself is road."""
        if any(width >= PLAZA and abs(_angle(b - heading)) <= width / 2 for b, width in self.roads):
            return _angle(heading)
        best = min((b for b, _ in self.roads), key=lambda b: abs(_angle(b - heading)), default=None)
        return best if best is not None and abs(_angle(best - heading)) <= within else None

    @property
    def exits(self) -> dict[str, bool]:
        """Whether road leaves the arrow ahead, to the left and to the right: a crossing centred in that
        quarter, or one so wide that it covers the quarter's middle."""
        found = {"ahead": False, "left": False, "right": False, "behind": False}
        for bearing, width in self.roads:
            found[_sector(bearing)] = True
            for name, middle in (("ahead", 0.0), ("left", -90.0), ("right", 90.0)):
                found[name] |= abs(_angle(middle - bearing)) <= width / 2
        return {name: found[name] for name in ("ahead", "left", "right")}

    def water_within(self, heading: float, spread: float, distance: float) -> float | None:
        """The nearest water within `spread` degrees of `heading` and `distance` pixels, or None."""
        near = [
            d
            for index, d in enumerate(self.water)
            if d is not None and d <= distance and abs(_angle(_bin_bearing(index) - heading)) <= spread + 5
        ]
        return min(near, default=None)

    @property
    def water_sides(self) -> tuple[str, ...]:
        return tuple(sorted({_sector(_bin_bearing(i)) for i, d in enumerate(self.water) if d is not None}))


def _angle(value: float) -> float:
    return (value + 180.0) % 360.0 - 180.0


def _sector(bearing: float) -> str:
    bearing = _angle(bearing)
    if abs(bearing) <= SECTOR:
        return "ahead"
    if abs(bearing) >= 180 - SECTOR:
        return "behind"
    return "right" if bearing > 0 else "left"


def _bin_bearing(index: int) -> float:
    return -180.0 + 10.0 * index + 5.0


def layers(crop: np.ndarray, on_foot: bool = False) -> tuple[np.ndarray, np.ndarray] | None:
    """(water, road) masks of the crop, or None when the radar is washed out. `on_foot` for the flat map
    of a figure on foot, which is drawn at a closer scale (see SHEET_FOOT)."""
    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
    value, saturation = hsv[:, :, 2], hsv[:, :, 1]
    land = float(np.percentile(value[_INSIDE], 10))
    if land >= WASHED_OUT:
        water = _open_water(crop, hsv)
        return None if water is None else (water, np.zeros_like(water))
    grey = (saturation <= PAINT_SATURATION) & _INSIDE
    step = min(PAINT_CEILING, land + PAINT_STEP)
    bright = ((value >= max(PAINT_VALUE, step)) & grey).astype(np.uint8)
    if on_foot:
        # A sheet of the sea's own pale blue needs only the narrow disc; a white one the wide disc.
        tinted = bright & cv2.inRange(
            hsv, (OPEN_HUE[0], TINT_SATURATION[0], 0), (OPEN_HUE[1], TINT_SATURATION[1], 255)
        )
        opened = cv2.morphologyEx(bright, cv2.MORPH_OPEN, _K_SHEET_FOOT)
        opened |= cv2.morphologyEx((tinted > 0).astype(np.uint8), cv2.MORPH_OPEN, _K_SHEET)
    else:
        opened = cv2.morphologyEx(bright, cv2.MORPH_OPEN, _K_SHEET)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(opened, 8)
    water = np.zeros_like(bright)
    # Glare and white things of the world shine through the radar and go on past its edge; the radar's
    # own water stops there.
    beyond = (value[_EDGE_OUT] >= GLARE_VALUE) & (saturation[_EDGE_OUT] <= GLARE_SATURATION)
    for label in range(1, count):
        if stats[label, cv2.CC_STAT_AREA] < SHEET_AREA:
            continue
        # The opening rounds the shore off; the paint beside it belongs to the sheet, not to a road.
        sheet = (labels == label).astype(np.uint8)
        for _ in range(SHORE_FOOT if on_foot else 1):
            sheet |= cv2.dilate(sheet, _K_SHORE) & bright
        touching = sheet[_EDGE_IN] > 0
        if touching.sum() >= 10 and beyond[touching].mean() >= GLARE_SHARE:
            continue
        water |= sheet
    # Roads at night and under the blue flash are a duller paint than water ever is (L06, L08, L18 of
    # the labelled frames: 185 to 200), and a route is drawn over the middle of its road and hides it.
    paint = (value >= max(ROAD_VALUE, step)) & grey
    route = cv2.inRange(hsv, (26, 75, 180), (34, 255, 255)) | cv2.inRange(
        hsv, (130, 65, 150), (148, 255, 255)
    )
    band = ((paint | ((route > 0) & _INSIDE)) & (cv2.dilate(water, _K3) == 0)).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(band, 8)
    road = np.zeros_like(bright)
    for label in range(1, count):
        w, h = stats[label, cv2.CC_STAT_WIDTH], stats[label, cv2.CC_STAT_HEIGHT]
        # Icons (the house, the shop letters) are white too, but short and compact.
        if stats[label, cv2.CC_STAT_AREA] >= ROAD_AREA and max(w, h) >= ROAD_LONG:
            road[labels == label] = 1
    # A blip on a road hides it: the disc is bridged where the paint goes on at both sides of it.
    blip = ((saturation >= BLIP_SATURATION) & (value >= 60) & _INSIDE & (route == 0)).astype(np.uint8)
    road |= blip & cv2.morphologyEx(road, cv2.MORPH_CLOSE, _K_BLIP)
    return water, road


def _open_water(crop: np.ndarray, hsv: np.ndarray) -> np.ndarray | None:
    """Water that fills the map, as off the end of the pier, or None for a radar washed out by the sun.

    Both leave no dark land to measure paint against. The sea is a smooth sheet of a pale blue (hue 101 to
    104, saturation 13 to 22, no texture on the pier's frames); sun on sand or concrete is beige (hue 19
    to 23) and grainy."""
    pale = cv2.inRange(hsv, (OPEN_HUE[0], OPEN_SATURATION[0], 190), (OPEN_HUE[1], OPEN_SATURATION[1], 255))
    grain = np.abs(
        cv2.Laplacian(cv2.GaussianBlur(cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY), (3, 3), 0), cv2.CV_16S)
    )
    sheet = ((pale > 0) & (grain <= OPEN_GRAIN) & _INSIDE).astype(np.uint8)
    sheet = cv2.morphologyEx(sheet, cv2.MORPH_OPEN, _K_SHEET)
    if sheet[_INSIDE].mean() < OPEN_SHARE:
        return None
    return cv2.dilate(sheet, _K_SHORE) & _INSIDE.astype(np.uint8)


def water_mask(crop: np.ndarray, on_foot: bool = False) -> np.ndarray | None:
    """Where the minimap shows water: a 170 x 260 bool array over the HUD crop, True on water. For the
    tilted map in a vehicle, and with `on_foot=True` for the flat one on foot, which is drawn closer and
    needs a wider sheet to tell water from a crossing. None where the picture cannot say (no minimap, a
    damaged picture, a radar washed out by the sun). The arrow's own disc of ARROW_R is never water."""
    try:
        if not crop_ok(crop):
            return None
        masks = layers(crop, on_foot)
        return None if masks is None else masks[0].astype(bool)
    except Exception:  # degenerate image data must not reach the hands
        return None


def water_cells(
    crop: np.ndarray,
    on_foot: bool = True,
    cell: int = 3,
    x0: int = 35,
    y0: int = 28,
    cols: int = 60,
    rows: int = 38,
):
    """`water_mask` on a grid of `rows` x `cols` cells of `cell` pixels whose corner is crop (x0, y0), as
    `waymark` lays out its roads; a cell is water when any pixel of it is. None where the mask is None."""
    mask = water_mask(crop, on_foot)
    if mask is None:
        return None
    block = mask[y0 : y0 + rows * cell, x0 : x0 + cols * cell]
    if block.shape != (rows * cell, cols * cell):
        raise ValueError("the grid does not fit into the crop")
    return block.reshape(rows, cell, cols, cell).any(axis=(1, 3))


def _ring(mask: np.ndarray, radius: float) -> np.ndarray:
    xs = np.rint(ACX + radius * np.sin(np.radians(_RING_ANGLES))).astype(int)
    ys = np.rint(ACY - radius * np.cos(np.radians(_RING_ANGLES))).astype(int)
    hits = np.zeros(len(_RING_ANGLES), bool)
    valid = (xs >= 0) & (xs < mask.shape[1]) & (ys >= 0) & (ys < mask.shape[0])
    hits[valid] = mask[ys[valid], xs[valid]] > 0
    return hits


def _runs(hits: np.ndarray) -> list[tuple[float, float]]:
    """Runs of hits along the ring, bridging gaps under RUN_GAP: (centre bearing, width), degrees."""
    if not hits.any():
        return []
    if hits.all():
        return [(0.0, 360.0)]
    start = int(np.argmin(hits))  # begin in a gap so that a run over the seam behind stays whole
    runs: list[list[float]] = []
    current: list[float] = []
    gap = 0.0
    for offset in range(len(hits)):
        index = (start + offset) % len(hits)
        if hits[index]:
            if current and gap >= RUN_GAP:
                runs.append(current)
                current = []
            current.append(offset * _STEP)
            gap = 0.0
        else:
            gap += _STEP
    if current:
        runs.append(current)
    base = float(_RING_ANGLES[start])
    return [(_angle(base + (run[0] + run[-1]) / 2), run[-1] - run[0] + _STEP) for run in runs]


def read(crop: np.ndarray) -> Terrain | None:
    """Roads and water around the arrow, or None where the picture cannot say."""
    try:
        if not crop_ok(crop):
            return None
        masks = layers(crop)
        if masks is None:
            return None
        water, road = masks
        # Roads are read where they cross the outer ring. On the inner ring a wide road under the car
        # reaches round to the sides, and a street just ahead merges with it into one crossing.
        near = _runs(_ring(road, RING_R))
        roads = []
        for bearing, width in _runs(_ring(cv2.dilate(road, _K5), CHECK_R)):
            # A crossing that does not come in to the inner ring is a road beside the car, not one it is on.
            if any(abs(_angle(bearing - b)) <= (width + w) / 2 + 15 for b, w in near):
                roads.append((round(bearing, 1), round(width, 1)))
        on_road = bool(road[_UNDER].mean() > 0.15)
        under_water = bool(water[_UNDER].mean() > 0.5)
        bins: list[float | None] = [None] * 36
        ys, xs = np.nonzero(water)
        if len(xs):
            index = np.clip(((_BEARING[ys, xs] + 180.0) // 10).astype(int), 0, 35)
            distances = _DIST[ys, xs]
            for b in np.unique(index):
                bins[int(b)] = round(float(distances[index == b].min()), 1)
        return Terrain(tuple(roads), on_road, tuple(bins), under_water)
    except Exception:  # degenerate image data must not reach the hands
        return None


def police(reading: Reading) -> tuple[float, ...]:
    """Bearings of the red markers the minimap reader found: with stars lit, the police.

    The police flash red and blue, but the reader's blue takes in the teal markers that stand on the map
    at any time: on Kerim's drives it found a red marker on 59 % of the frames with stars lit and 13 %
    of those without, and a blue one on 21 % and 27 %. In a mission red is an enemy as well, and is
    driven away from all the same."""
    blips = reading.blips if isinstance(reading, Reading) else ()
    return tuple(
        round(math.degrees(math.atan2(blip.x, blip.y)), 1)
        for blip in blips
        if isinstance(blip, Blip) and blip.color == "red" and math.hypot(blip.x, blip.y) >= 4
    )
