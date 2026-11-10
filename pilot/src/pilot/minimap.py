"""Minimap reader, approach "colour segmentation and tracing".

read(crop) -> Reading.  crop: 170 x 260 x 3 uint8 RGB (bottom-left HUD corner of a GTA V frame).

Pipeline
  1. HSV once for the whole crop.
  2. Minimap present: the three bars under the map (colour against the rows above and below them) and the
     player arrow (matched filter, 48 headings x 25 shifts).
  3. Route, per colour (yellow, purple): a route is a thin line of saturated colour, so the masks come from a
     top-hat (ellipse 13 px) of the chroma channel min(R,G)-B resp. min(R,B)-G, gated by hue. "weak" is what
     the flood may walk on, "strong" tells a real route from pale look-alikes.
     Flood: breadth-first from the mask pixels nearest to the arrow (within 16 px), 2 px per step, so gaps of
     2 px are bridged. A second flood back from the pixels reached last marks the main path; the bearings are
     the first pixels of that path at NEAR_R / FAR_R, or the end of the path if the route is shorter.
     Yellow road markings of the game world have the colour of the route. They are told apart by geometry:
     they are straight and go on outside the map rectangle. Such lines are fitted outside the map and erased
     along their whole length; a trace that leaves the map rectangle is no route either.
  4. flat / tilted: a route means tilted; otherwise a logistic regression on eight numbers that describe the
     perspective of the road pattern.
  5. corrupt: 16 px block borders of the video codec that show as edges. Damage next to the arrow tightens
     the route test and lowers the confidence.
"""

from __future__ import annotations

import math

import cv2
import numpy as np

from .contract import ARROW_XY, FAR_R, NEAR_R, Reading

cv2.setNumThreads(1)

H, W = 170, 260
# --- measured geometry (crop pixels)
MX0, MX1, MY0, MY1 = 34, 215, 28, 142  # map rectangle, half-open
ACX, ACY = 123.3, 116.8  # rotation centre of the player arrow
BAR_Y0, BAR_Y1 = 146, 150  # solid rows of the three bars

# --- region of interest for the route flood: map rectangle plus a moat on three sides (not the bars)
MOAT = 8
RX0, RX1, RY0, RY1 = MX0 - MOAT, MX1 + MOAT, MY0 - MOAT, MY1
RW, RH = RX1 - RX0, RY1 - RY0
_yy, _xx = np.mgrid[RY0:RY1, RX0:RX1]
_dist = np.hypot(_xx - ARROW_XY[0], _yy - ARROW_XY[1]).astype(np.float32)
_DIST_FLAT = _dist.ravel()
_XF = (_xx - ARROW_XY[0]).astype(np.float32).ravel()
_YF = (_yy - ARROW_XY[1]).astype(np.float32).ravel()
# pixels of the moat that no blip on the map border can reach: a route never gets there, world lines do
_OUT = ((_xx < MX0 - 5) | (_xx >= MX1 + 5) | (_yy < MY0 - 5)).astype(np.uint8)
_OUT_IDX = np.flatnonzero(_OUT.ravel())

# Measured maximum gap from the arrow to a route core.
SEED_R = 16.0
_seed_idx = np.flatnonzero(_DIST_FLAT <= SEED_R)
_seed_idx = _seed_idx[np.argsort(_DIST_FLAT[_seed_idx], kind="stable")]
_SEED_IDX = _seed_idx
_SEED_D = _DIST_FLAT[_seed_idx]
_NEAR_ZONE = np.flatnonzero(_DIST_FLAT < 36)

# Close one-pixel gaps in the colour mask.
_K3 = np.ones((3, 3), np.uint8)
# Flood in two-pixel steps across compression gaps.
_K5 = np.ones((5, 5), np.uint8)


# ------------------------------------------------------------------ player arrow
def _arrow_kernels(n_angles: int = 48, size: int = 17, ss: int = 8):
    """Matched filters for the arrow: +1/n on the white inside, -1/n on the dark outline, 0 elsewhere."""
    c = size // 2
    outer = np.array([(0.0, -6.2), (5.0, 4.3), (0.0, 1.9), (-5.0, 4.3)])
    inner = np.array([(0.0, -3.9), (3.0, 2.6), (0.0, 0.6), (-3.0, 2.6)])
    kernels = []
    for i in range(n_angles):
        a = 2 * math.pi * i / n_angles
        rot = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
        maps = []
        for poly in (outer, inner):
            p = (poly @ rot.T + c + 0.5) * ss
            canvas = np.zeros((size * ss, size * ss), np.uint8)
            cv2.fillPoly(canvas, [np.round(p).astype(np.int32)], 255)
            maps.append(
                cv2.resize(canvas, (size, size), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
            )
        inside = maps[1]
        outline = np.clip(maps[0] - maps[1], 0, 1)
        kernels.append((inside / inside.sum() - outline / outline.sum()).ravel())
    return np.stack(kernels).astype(np.float32), size


_ARROW_K, _ARROW_SIZE = _arrow_kernels()
_ARROW_N = _ARROW_K.shape[0]
_ARROW_SHIFTS = [(dx, dy) for dy in (-2, -1, 0, 1, 2) for dx in (-2, -1, 0, 1, 2)]


def _read_arrow(gray: np.ndarray):
    """(heading in degrees or None, score 0..1). gray: float32 170x260, 0..1."""
    half = _ARROW_SIZE // 2
    cx, cy = round(ACX), round(ACY)
    wins = np.empty((len(_ARROW_SHIFTS), _ARROW_SIZE * _ARROW_SIZE), np.float32)
    for n, (dx, dy) in enumerate(_ARROW_SHIFTS):
        wins[n] = gray[cy + dy - half : cy + dy + half + 1, cx + dx - half : cx + dx + half + 1].ravel()
    resp = wins @ _ARROW_K.T  # shifts x angles
    per_angle = resp.max(axis=0)
    i = int(per_angle.argmax())
    best = float(per_angle[i])
    a, b = float(per_angle[i - 1]), float(per_angle[(i + 1) % _ARROW_N])
    denom = a - 2 * best + b
    off = 0.5 * (a - b) / denom if denom < -1e-6 else 0.0
    deg = ((i + off) * 360.0 / _ARROW_N + 180.0) % 360.0 - 180.0
    if deg == -180.0:
        deg = 180.0
    return deg, best


# ------------------------------------------------------------------ bars
def _bars(crop: np.ndarray) -> int:
    """How many of the three bars under the map are visible (0..3): each must have its colour and stand out
    in that colour against the rows just above and below it (a green meadow is not a health bar)."""
    inside = crop[BAR_Y0:BAR_Y1, MX0:MX1].astype(np.int16).mean(axis=0)
    around = np.concatenate((crop[137:140, MX0:MX1], crop[155:158, MX0:MX1])).astype(np.int16).mean(axis=0)

    def chroma(row):
        r, g, b = row[:, 0], row[:, 1], row[:, 2]
        return g - np.maximum(r, b), r - np.maximum(g, b), b - r, np.minimum(r, g) - b

    gi, ri, bi, yi = chroma(inside)
    go, ro, bo, yo = chroma(around)
    s1, s2, s3 = slice(38 - MX0, 118 - MX0), slice(128 - MX0, 164 - MX0), slice(174 - MX0, 210 - MX0)
    health = (((gi[s1] > 10) & (gi[s1] - go[s1] > 12)) | ((ri[s1] > 30) & (ri[s1] - ro[s1] > 25))).mean()
    armour = ((bi[s2] > 12) & (bi[s2] - bo[s2] > 15)).mean()
    special = ((yi[s3] > 35) & (yi[s3] - yo[s3] > 25)).mean()
    return int(health > 0.5) + int(armour > 0.5) + int(special > 0.5)


# ------------------------------------------------------------------ route
_KTOP = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13))
_K7 = np.ones((7, 7), np.uint8)

# the part of the crop where only the game world is seen: outside the map (6 px clear of it, blips stick out
# of the map border) and not the strip of the bars
_gy, _gx = np.mgrid[0:H, 0:W]
_OUTSIDE = (
    ((_gx < MX0 - 6) | (_gx >= MX1 + 6) | (_gy < MY0 - 6) | (_gy >= MY1 + 14))
    & ~((_gy >= MY1 - 2) & (_gy < MY1 + 14) & (_gx >= MX0 - 6) & (_gx < MX1 + 6))
).astype(np.uint8) * 255


# Broad world-paint scale, wider than the 13px GPS top-hat.
_KTOP_W = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (17, 17))


def _world_lines(crop: np.ndarray, hsv: np.ndarray):
    """Yellow road markings of the game world shine through the map. They are straight and, unlike a route,
    go on outside the map. Returns ([(xa, ya, xb, yb, half_width)], number of world-yellow pixels outside)."""
    r, g, b = cv2.split(crop)
    top = cv2.morphologyEx(cv2.subtract(cv2.min(r, g), b), cv2.MORPH_TOPHAT, _KTOP_W)
    thin = cv2.bitwise_and(
        cv2.threshold(top, 59, 255, cv2.THRESH_BINARY)[1], cv2.inRange(hsv, (27, 85, 185), (33, 255, 255))
    )
    outm = cv2.bitwise_and(thin, _OUTSIDE)
    n_out = cv2.countNonZero(outm)
    if n_out < 25:
        return [], n_out
    _n, lab, stats, _ = cv2.connectedComponentsWithStats(outm, connectivity=8)
    areas = stats[1:, cv2.CC_STAT_AREA]
    order = np.argsort(-areas)[:8] + 1
    ys_all, xs_all = np.nonzero(thin)
    xs_all = xs_all.astype(np.float32)
    ys_all = ys_all.astype(np.float32)
    lines = []
    for i in order:
        x, y, w, h, area = stats[i]
        if area < 20:
            break
        py, px = np.nonzero(lab[y : y + h, x : x + w] == i)
        fit = _pca(px.astype(np.float32) + x, py.astype(np.float32) + y)
        if fit is None:
            continue
        mx, my, dx, dy, l1, l2 = fit
        if l1 < 12 or l2 > 0.3 * l1:  # shorter than 12 px or a blob: no direction to trust
            continue
        hw = min(math.sqrt(3 * l2), 12.0)
        # refit on all thin yellow along the line, inside the map too: a much longer baseline
        for tol in (5.0, 3.0):
            off = (xs_all - mx) * -dy + (ys_all - my) * dx
            sel = np.abs(off) <= hw + tol
            fit2 = _pca(xs_all[sel], ys_all[sel])
            if fit2 is None or fit2[5] > 0.15 * fit2[4] or abs(fit2[2] * dx + fit2[3] * dy) < 0.96:
                break
            mx, my, dx, dy = fit2[:4]
        # how far the line really runs: from the piece outside along the yellow, over gaps of up to 40 px
        # (map roads hide it); a route that merely lies on the extension of something yellow stays
        off = (xs_all - mx) * -dy + (ys_all - my) * dx
        sel = np.abs(off) <= hw + 3
        t = np.rint((xs_all[sel] - mx) * dx + (ys_all[sel] - my) * dy).astype(np.int32) + 400
        occ = np.zeros(800, bool)
        occ[np.clip(t, 0, 799)] = True
        t_c = round((x + 0.5 * w - mx) * dx + (y + 0.5 * h - my) * dy) + 400
        on = np.flatnonzero(occ)
        if on.size == 0:
            continue
        j = int(np.abs(on - t_c).argmin())
        gaps = np.diff(on) > 40
        lo = j - int(np.argmax(gaps[:j][::-1])) if gaps[:j].any() else 0
        hi = j + int(np.argmax(gaps[j:])) if gaps[j:].any() else on.size - 1
        ta, tb = float(on[lo] - 400 - 3), float(on[hi] - 400 + 3)
        lines.append((mx + ta * dx, my + ta * dy, mx + tb * dx, my + tb * dy, hw))
    return lines, n_out


def _pca(xs: np.ndarray, ys: np.ndarray):
    if xs.size < 8:
        return None
    mx, my = float(xs.mean()), float(ys.mean())
    ax, ay = xs - mx, ys - my
    sxx, syy, sxy = float((ax * ax).mean()), float((ay * ay).mean()), float((ax * ay).mean())
    half_tr = 0.5 * (sxx + syy)
    disc = math.sqrt(max(half_tr * half_tr - (sxx * syy - sxy * sxy), 0.0))
    ang = 0.5 * math.atan2(2 * sxy, sxx - syy)
    return mx, my, math.cos(ang), math.sin(ang), half_tr + disc, max(half_tr - disc, 0.0)


def _masks(roi_rgb: np.ndarray, hsv_roi: np.ndarray, colour: str):
    """(weak, strong) uint8 masks of route-coloured thin structures in the region of interest."""
    # HSV/chroma bands measured on GPS tiles: pale pixels connect the trace,
    # while saturated, bright pixels confirm its colour.
    r, g, b = cv2.split(roi_rgb)
    if colour == "yellow":
        chroma = cv2.subtract(cv2.min(r, g), b)  # yellowness
        hue = cv2.inRange(hsv_roi, (26, 45, 140), (35, 255, 255))
        hue_s = cv2.inRange(hsv_roi, (26, 75, 180), (34, 255, 255))
        t_weak, t_strong = 35, 70
    else:
        chroma = cv2.subtract(cv2.min(r, b), g)  # purpleness
        hue = cv2.inRange(hsv_roi, (126, 40, 110), (152, 255, 255))
        hue_s = cv2.inRange(hsv_roi, (130, 65, 150), (148, 255, 255))
        t_weak, t_strong = 25, 45
    # top-hat: keeps only what is narrower than 13 px, a route is a thin line; broad yellowish ground goes
    top = cv2.morphologyEx(chroma, cv2.MORPH_TOPHAT, _KTOP)
    weak = cv2.bitwise_and(cv2.threshold(top, t_weak - 1, 255, cv2.THRESH_BINARY)[1], hue)
    strong = cv2.bitwise_and(cv2.threshold(top, t_strong - 1, 255, cv2.THRESH_BINARY)[1], hue_s)
    return weak, strong


_PASS_R = 34.0  # within this distance of the arrow the flood may cross an erased world line
_FAR_OF_ARROW = (_dist > _PASS_R).astype(np.uint8) * 255


def _erase_mask(lines) -> np.ndarray:
    """Mask (region of interest) of the world lines, a little wider than the lines themselves."""
    erase = np.zeros((RH, RW), np.uint8)
    for xa, ya, xb, yb, hw in lines:
        p0 = (round(xa) - RX0, round(ya) - RY0)
        p1 = (round(xb) - RX0, round(yb) - RY0)
        cv2.line(erase, p0, p1, 255, int(2 * (hw + 3)) + 1)
    return erase


def _flood(seed01: np.ndarray, mask01: np.ndarray):
    """Breadth-first flood in steps of 2 px (bridges gaps of 2 px). Returns (acc, steps): acc counts for how
    many steps a pixel has been reached, so it was reached at step `steps - acc` (acc 0: never)."""
    reached = seed01
    acc = reached.copy()
    n_prev = cv2.countNonZero(reached)
    steps = 1
    for _ in range(250):
        grown = cv2.dilate(reached, _K5)
        cv2.bitwise_and(grown, mask01, dst=grown)
        n = cv2.countNonZero(grown)
        if n == n_prev:
            break
        reached, n_prev = grown, n
        cv2.add(acc, reached, dst=acc)
        steps += 1
    return acc, steps


def _trace(weak: np.ndarray, strong: np.ndarray, val: np.ndarray, erase: np.ndarray | None = None):
    """Follow the route mask from the arrow. Returns None or a dict with bearings and quality numbers.

    With `erase` (world lines) the flood may cross erased pixels next to the arrow, where a world line can
    hide the first pixels of a route, but erased pixels never count as route."""
    if cv2.countNonZero(weak) < 25:
        return None
    mask = cv2.morphologyEx(weak, cv2.MORPH_CLOSE, _K3)
    erased_near = 0
    if erase is not None:
        erased_near = int(np.count_nonzero(cv2.bitwise_and(mask, erase).ravel()[_NEAR_ZONE]))
        cv2.bitwise_and(mask, cv2.bitwise_not(cv2.bitwise_and(erase, _FAR_OF_ARROW)), dst=mask)
    hit = np.flatnonzero(mask.ravel()[_SEED_IDX])
    if hit.size == 0:
        return None
    d0 = float(_SEED_D[hit[0]])
    seed = np.zeros((RH, RW), np.uint8)
    seed.ravel()[_SEED_IDX[hit[_SEED_D[hit] <= d0 + 3.0]]] = 1
    mask01 = (mask > 0).view(np.uint8)
    acc, steps = _flood(seed, mask01)
    reached01 = cv2.threshold(acc, 0, 1, cv2.THRESH_BINARY)[1]
    if erase is not None:
        cv2.bitwise_and(acc, cv2.bitwise_not(erase), dst=acc)
    accf = acc.ravel()
    idx_all = np.flatnonzero(accf)
    if idx_all.size < 30:
        return None
    a_all = accf[idx_all]
    d_all = _DIST_FLAT[idx_all]
    dmax = float(d_all.max())

    # the route is the path from the arrow to the pixels reached last; side branches (remains of world
    # lines, damage) are left out: flood back from the end, a pixel is on the path if both floods agree
    end_idx = idx_all[a_all <= int(a_all.min()) + 1]
    back = np.zeros((RH, RW), np.uint8)
    back.ravel()[end_idx] = 1
    accb, stepsb = _flood(back, reached01)
    t_all = steps - a_all.astype(np.int32)
    s_all = stepsb - accb.ravel()[idx_all].astype(np.int32)
    on_path = (t_all + s_all) <= int((t_all + s_all).min()) + 2
    p_idx, p_t, p_d = idx_all[on_path], t_all[on_path], d_all[on_path]

    # Export only observed route pixels, never the filled arrow or morphology gap.
    reliable = (p_d >= 11.0) & (weak.ravel()[p_idx] > 0)
    if erase is not None:
        reliable &= erase.ravel()[p_idx] == 0
    path = []
    if reliable.any():
        start, stop = int(p_t[reliable].min()), int(p_t[reliable].max())
        for travel in range(start, stop + 1, 3):
            pick = p_idx[reliable & (p_t >= travel) & (p_t < travel + 3)]
            if not pick.size:
                continue
            x, y = _XF[pick], -_YF[pick]
            center = int(np.argmin((x - x.mean()) ** 2 + (y - y.mean()) ** 2))
            point = (float(x[center]), float(y[center]))
            if not path or math.dist(point, path[-1]) >= 2:
                path.append(point)

    def at_radius(radius):
        sel = p_d >= radius - 1.5
        if not sel.any():
            return None  # the route ends inside this circle
        tmin = int(p_t[sel].min())
        pick = p_idx[sel & (p_t <= tmin + 1) & (p_d < radius + 4.0)]
        if pick.size == 0:
            pick = p_idx[sel & (p_t <= tmin + 1)]
        return float(_XF[pick].mean()), float(_YF[pick].mean())

    end = float(_XF[end_idx].mean()), float(_YF[end_idx].mean())
    near = at_radius(NEAR_R) or end
    far = at_radius(FAR_R) or end
    zone = d_all < 36
    strong_frac = float(np.count_nonzero(strong.ravel()[idx_all[zone]])) / max(1, int(zone.sum()))
    out_n = int(np.count_nonzero(accf[_OUT_IDX]))
    xs, ys = _XF[idx_all], _YF[idx_all]
    span = float(max(xs.max() - xs.min(), ys.max() - ys.min()))
    # blips are yellow discs inside a dark ring: pixels that are not next to something dark are line pixels
    dark = cv2.dilate(cv2.threshold(val, 90, 255, cv2.THRESH_BINARY_INV)[1], _K7)
    n_clear = int(np.count_nonzero(dark.ravel()[idx_all] == 0))
    return {
        "n": int(idx_all.size),
        "d0": d0,
        "dmax": dmax,
        "span": span,
        "strong": strong_frac,
        "out": out_n,
        "clear": n_clear,
        "steps": steps,
        "erased": erased_near,
        "near": math.degrees(math.atan2(near[0], -near[1])),
        "far": math.degrees(math.atan2(far[0], -far[1])),
        "path": tuple(path),
    }


def _route_ok(tr, world: bool = False, damaged: bool = False) -> bool:
    if tr is None:
        return False
    # The attacked genuine trace had a 1.3% fringe after world-line removal.
    # Allow up to 2% exterior pixels; substantial spill still indicates world paint.
    if tr["out"] >= 3 and tr["out"] >= 0.02 * tr["n"]:
        return False
    # Minimum span/reach and saturated, unobscured support reject coloured blips.
    # These trace thresholds retain all labelled routes on both splits.
    if tr["span"] < 15 or tr["dmax"] < 14:
        return False
    if tr["strong"] < 0.3:
        return False
    if tr["clear"] < 30:
        return False
    if world:  # yellow markings of the world are around: only a line that starts at the arrow and goes on
        if tr["d0"] > 6.5 or tr["dmax"] < 25 or tr["span"] < 18 or tr["clear"] < 50:
            return False
    if damaged:  # block damage around the arrow: a thin or pale trace is a guess, no route then
        if tr["strong"] < 0.45 or tr["clear"] < 60 or tr["dmax"] < 20:
            return False
    return True


# ------------------------------------------------------------------ flat / tilted
# In a vehicle the map is drawn in perspective: far roads (upper part of the map) become thin lines, while
# on foot roads keep their width everywhere. Eight numbers describe that; the weights are a logistic
# regression fitted on the two recordings (driving stretches against on-foot stretches).
_E5 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
_KH7 = np.ones((1, 7), np.uint8)


def _line_kernel(length: int, deg: float) -> np.ndarray:
    k = np.zeros((length, length), np.uint8)
    c = length // 2
    a = math.radians(deg)
    dx, dy = math.cos(a), -math.sin(a)
    p0 = (round(c - dx * c), round(c - dy * c))
    p1 = (round(c + dx * c), round(c + dy * c))
    cv2.line(k, p0, p1, 1, 1)
    return k


_LINE_DEG = (0, 15, -15, 30, -30, 50, -50, 70, -70, 90)
_K9 = [_line_kernel(9, d) for d in _LINE_DEG]
_K13 = [_line_kernel(13, d) for d in _LINE_DEG]
# Frozen lab fit to road width, line length, texture and perspective in these recordings.
_TILT_W = (62.0383, -7.5284, -49.9419, 0.6407, 7.218, 2.9659, 60.201, -2.8143)  # ln9_up hl_up wide_up w_up
_TILT_B = -7.854  # ... e1_up an_up ln13_mid e1_lo


def _lines(thin: np.ndarray, kernels) -> np.ndarray:
    acc = cv2.morphologyEx(thin, cv2.MORPH_OPEN, kernels[0])
    for k in kernels[1:]:
        cv2.bitwise_or(acc, cv2.morphologyEx(thin, cv2.MORPH_OPEN, k), dst=acc)
    return acc


def _tilt_score(crop: np.ndarray) -> float:
    """> 0: tilted (in a vehicle), < 0: flat (on foot)."""
    m = cv2.cvtColor(crop[MY0:MY1, MX0:MX1], cv2.COLOR_RGB2GRAY)
    gb = cv2.blur(m, (3, 3))
    sd = float(cv2.meanStdDev(gb)[1][0, 0])
    # roads: brighter than their surroundings; how wide are they in the upper part
    road = cv2.threshold(cv2.subtract(gb, cv2.blur(gb, (31, 31))), max(8.0, 0.25 * sd), 1, cv2.THRESH_BINARY)[
        1
    ]
    dt = cv2.distanceTransform(road, cv2.DIST_L2, 3)
    dt_up, road_up = dt[2:42], road[2:42]
    n_road = cv2.countNonZero(road_up)
    w_up = float(dt_up.sum()) / n_road if n_road > 20 else 0.0
    wide_up = float(np.count_nonzero(dt_up >= 4)) / dt_up.size
    # thin bright lines: far roads
    top = cv2.morphologyEx(gb, cv2.MORPH_TOPHAT, _E5)
    thin = cv2.threshold(top, min(max(0.4 * sd, 6.0), 18.0), 1, cv2.THRESH_BINARY)[1]
    t_up = thin[0:54]
    hl_up = float(cv2.countNonZero(cv2.morphologyEx(t_up, cv2.MORPH_OPEN, _KH7)[2:42])) / (40 * (MX1 - MX0))
    ln9_up = float(cv2.countNonZero(_lines(t_up, _K9)[2:42])) / (40 * (MX1 - MX0))
    ln13_mid = float(cv2.countNonZero(_lines(thin[28:86], _K13)[14:44])) / (30 * (MX1 - MX0))
    # fine detail relative to all detail, upper and lower part; direction of the edges in the upper part
    f = m.astype(np.float32)
    b1 = cv2.blur(f, (3, 3))
    e1 = cv2.absdiff(b1, cv2.blur(f, (7, 7)))
    tot = float(cv2.absdiff(b1, cv2.blur(f, (31, 31))).mean()) + 1.0
    e1_up = float(e1[2:42].mean()) / tot
    e1_lo = float(e1[72:112].mean()) / tot
    gy = float(np.abs(b1[4:44, 1:-1] - b1[2:42, 1:-1]).mean())
    gx = float(np.abs(b1[3:43, 2:] - b1[3:43, :-2]).mean())
    an_up = gy / (gx + 1.0)
    x = (ln9_up, hl_up, wide_up, w_up, e1_up, an_up, ln13_mid, e1_lo)
    return sum(w * v for w, v in zip(_TILT_W, x, strict=True)) + _TILT_B


# ------------------------------------------------------------------ stream damage
# A damaged frame consists of 16 x 16 blocks that do not fit their neighbours. The crop starts at (30, 530)
# of the frame, so block borders lie at x = 2 + 16 i and y = 14 + 16 j. A border piece (16 px) counts when
# nearly all its pixels show a jump across the border that the pixels next to it do not show.
_BX = np.arange(18, 243, 16)  # vertical borders used (x: jump between x - 1 and x)
_BY = np.arange(30, 143, 16)  # horizontal borders used
_BV_SKIP = int(np.flatnonzero(_BX == MX0)[0])  # the left edge of the map sits on a block border
_BH_SKIP = int(np.flatnonzero(_BY == MY1)[0])  # and so does the top edge of the bars
_bv_cx, _bv_cy = np.meshgrid(_BX.astype(np.float32), 14 + 16 * np.arange(9, dtype=np.float32) + 8)
_bh_cx, _bh_cy = np.meshgrid(2 + 16 * np.arange(16, dtype=np.float32) + 8, _BY.astype(np.float32))
_BV_NEAR = np.hypot(_bv_cx - ARROW_XY[0], _bv_cy - ARROW_XY[1]) <= 48
_BH_NEAR = np.hypot(_bh_cx - ARROW_XY[0], _bh_cy - ARROW_XY[1]) <= 48


def _blocks(crop: np.ndarray):
    """(number of block-border pieces in the crop, number of them within 48 px of the arrow)."""
    g = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY).astype(np.int16)
    dx = np.abs(g[14:158, 1:] - g[14:158, :-1])
    a, b, c = dx[:, _BX - 1], dx[:, _BX - 2], dx[:, _BX]
    bv = ((a > 10) & (a > 2.5 * np.maximum(b, c) + 3)).reshape(9, 16, len(_BX)).sum(axis=1) >= 12
    dy = np.abs(g[1:, 2:258] - g[:-1, 2:258])
    a, b, c = dy[_BY - 1], dy[_BY - 2], dy[_BY]
    bh = ((a > 10) & (a > 2.5 * np.maximum(b, c) + 3)).reshape(len(_BY), 16, 16).sum(axis=2) >= 12
    bv[:, _BV_SKIP] = False
    bh[_BH_SKIP, :] = False
    return int(bv.sum() + bh.sum()), int(bv[_BV_NEAR].sum() + bh[_BH_NEAR].sum())


# ------------------------------------------------------------------ read
def read(crop: np.ndarray) -> Reading:
    try:
        if not isinstance(crop, np.ndarray) or crop.shape != (H, W, 3) or crop.dtype != np.uint8:
            return Reading("none", "none", None, None, None, False, 0.0)
        return _analyse(crop)[0]
    except Exception:  # never raise on any input
        return Reading("none", "none", None, None, None, False, 0.0)


# Rings heading: measured 18px silhouette, 48 angular bins and a 3x3 centre
# search. Normalized correlation suppresses world brightness and coloured blips.
_HEADING_ARROW_C = (123.3, 116.0)
_HEADING_ARROW_SCALE = 0.95
_HEADING_ARROW_OUTER = [
    (-1.3, -5.9),
    (1.3, -5.9),
    (4.95, 3.2),
    (4.95, 5.1),
    (3.0, 5.1),
    (2.5, 4.5),
    (0.0, 4.3),
    (-2.5, 4.5),
    (-3.0, 5.1),
    (-4.95, 5.1),
    (-4.95, 3.2),
]
_HEADING_ARROW_INNER = [
    (0.0, -4.0),
    (3.2, 2.6),
    (3.2, 3.2),
    (1.4, 3.2),
    (0.0, 2.0),
    (-1.4, 3.2),
    (-3.2, 3.2),
    (-3.2, 2.6),
]
_HEADING_AX0, _HEADING_AY0, _HEADING_AW, _HEADING_AH = (115, 108, 18, 18)
_HEADING_NT = 48
_HEADING_SHIFTS = [(dx, dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1)]


def _heading_make_arrow_templates():
    up = 8
    ts, ms = ([], [])
    for j in range(_HEADING_NT):
        t = math.radians(j * 360.0 / _HEADING_NT)
        c, sn = (math.cos(t), math.sin(t))

        def poly(pts, grow=0.0, c=c, sn=sn):
            out = []
            for x, y in pts:
                x, y = (x * _HEADING_ARROW_SCALE, y * _HEADING_ARROW_SCALE)
                if grow:
                    n = math.hypot(x, y - 1.0)
                    x, y = (x + grow * x / n, y + grow * (y - 1.0) / n)
                xr, yr = (x * c - y * sn, x * sn + y * c)
                out.append(
                    (
                        (_HEADING_ARROW_C[0] + xr - _HEADING_AX0 + 0.5) * up - 0.5,
                        (_HEADING_ARROW_C[1] + yr - _HEADING_AY0 + 0.5) * up - 0.5,
                    )
                )
            return np.round(np.array(out)).astype(np.int32)

        img = np.zeros((_HEADING_AH * up, _HEADING_AW * up), np.float32)
        msk = np.zeros((_HEADING_AH * up, _HEADING_AW * up), np.float32)
        cv2.fillPoly(msk, [poly(_HEADING_ARROW_OUTER, 1.6)], 1.0)
        cv2.fillPoly(img, [poly(_HEADING_ARROW_OUTER, 1.6)], 0.2)
        cv2.fillPoly(img, [poly(_HEADING_ARROW_OUTER)], -2.0)
        cv2.fillPoly(img, [poly(_HEADING_ARROW_INNER)], 1.0)
        img = cv2.resize(img, (_HEADING_AW, _HEADING_AH), interpolation=cv2.INTER_AREA)
        m = (cv2.resize(msk, (_HEADING_AW, _HEADING_AH), interpolation=cv2.INTER_AREA) > 0.5).astype(
            np.float32
        )
        img = (img - (img * m).sum() / m.sum()) * m
        img /= np.linalg.norm(img)
        ts.append(img.ravel())
        ms.append(m.ravel())
    return (np.array(ts, np.float32), np.array(ms, np.float32))


_HEADING_ARROW_T, _HEADING_ARROW_M = _heading_make_arrow_templates()
_HEADING_ARROW_N = _HEADING_ARROW_M.sum(axis=1)


def _heading_arrow(white: np.ndarray) -> tuple[float, float]:
    """Heading of the player arrow in degrees and the match quality (normalised correlation, -1..1).
    `white` is min(R, G, B) as float32."""
    patches = np.empty((len(_HEADING_SHIFTS), _HEADING_AH * _HEADING_AW), np.float32)
    for n, (dx, dy) in enumerate(_HEADING_SHIFTS):
        patches[n] = white[
            _HEADING_AY0 + dy : _HEADING_AY0 + dy + _HEADING_AH,
            _HEADING_AX0 + dx : _HEADING_AX0 + dx + _HEADING_AW,
        ].ravel()
    num = patches @ _HEADING_ARROW_T.T
    s1 = patches @ _HEADING_ARROW_M.T
    s2 = patches * patches @ _HEADING_ARROW_M.T
    var = np.maximum(s2 - s1 * s1 / _HEADING_ARROW_N, 0.001)
    ncc = num / np.sqrt(var)
    j = int(np.argmax(ncc))
    q = float(ncc.flat[j])
    row, t = divmod(j, _HEADING_NT)
    a, b, c = (float(ncc[row, (t - 1) % _HEADING_NT]), q, float(ncc[row, (t + 1) % _HEADING_NT]))
    den = a - 2 * b + c
    off = 0.5 * (a - c) / den if den < -1e-06 else 0.0
    deg = (t + off) * 360.0 / _HEADING_NT
    return ((deg + 180.0) % 360.0 - 180.0, q)


def _heading(crop):
    # Only these pixels are read by the 18px templates and their +/-1px shifts.
    white = np.zeros((H, W), np.float32)
    white[107:127, 114:134] = crop[107:127, 114:134].min(axis=2)
    angle, quality = _heading_arrow(white)
    # Validated Rings threshold, independently tested on both labelled splits.
    if quality < 0.5:
        return None
    return 180.0 if angle == -180.0 else angle


def _analyse(crop: np.ndarray, keep: bool = False):
    info: dict = {}
    crop = np.ascontiguousarray(crop)
    hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
    bars = _bars(crop)
    full = np.zeros((H, W), np.float32)
    full[96:138, 102:146] = cv2.cvtColor(crop[96:138, 102:146], cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    _, arrow_score = _read_arrow(full)
    has_arrow = arrow_score > 0.3
    present = bars >= 2 or (bars >= 1 and has_arrow) or arrow_score > 0.45
    n_blocks, n_local = _blocks(crop)
    corrupt = n_blocks >= 2
    info.update(bars=bars, arrow_score=round(arrow_score, 3), blocks=n_blocks, blocks_near=n_local)
    if not present:
        return Reading("none", "none", None, None, None, corrupt, 0.0), info

    hsv_roi = np.ascontiguousarray(hsv[RY0:RY1, RX0:RX1])
    rgb_roi = np.ascontiguousarray(crop[RY0:RY1, RX0:RX1])
    val = np.ascontiguousarray(hsv_roi[:, :, 2])
    wy, sy = _masks(rgb_roi, hsv_roi, "yellow")
    ty = _trace(wy, sy, val)
    world = False
    if ty is not None:
        lines, n_out = _world_lines(crop, hsv)
        world = n_out >= 25
        info.update(world_lines=len(lines), world_out=n_out)
        if lines:
            ty = _trace(wy, sy, val, _erase_mask(lines))
    wp, sp = _masks(rgb_roi, hsv_roi, "purple")
    tp = _trace(wp, sp, val)
    if keep:
        info.update(yellow=ty, purple=tp, yellow_weak=wy, yellow_strong=sy, purple_weak=wp, purple_strong=sp)
    damaged_here = n_local >= 4  # the damage covers the surroundings of the arrow
    oky = _route_ok(ty, world, damaged_here)
    okp = _route_ok(tp, False, damaged_here)
    if oky and okp:
        if ty["n"] * ty["strong"] >= tp["n"] * tp["strong"]:
            okp = False
        else:
            oky = False
    route, tr = ("yellow", ty) if oky else ("purple", tp) if okp else ("none", None)

    if tr is not None:
        minimap = "tilted"  # a route is only drawn while driving
        bearing, far_bearing = tr["near"], tr["far"]
        conf = 0.5 + 0.5 * min(1.0, max(0.0, (tr["strong"] - 0.3) / 0.4))
        if tr["dmax"] < NEAR_R:
            conf *= 0.8
        if tr["d0"] > 6.5:
            conf *= 0.85
        if tr["erased"]:
            conf *= 0.8
        if route == "yellow" and world:
            conf *= 0.9
    else:
        tilt = _tilt_score(crop)
        info["tilt"] = round(tilt, 2)
        minimap = "tilted" if tilt > 0 else "flat"
        bearing = far_bearing = None
        conf = 0.9 if (ty is None and tp is None) else 0.7  # something route-like was seen and turned down
    if corrupt:
        conf *= 0.6
    if n_local >= 2:
        conf *= 0.75
    if damaged_here:
        conf *= 0.75
    # The attack found visibly damaged maps still scoring 0.54-0.60. A codec
    # warning caps confidence below 0.5 even when a strong route survives.
    # This is an abstention signal, not a calibrated probability of correctness.
    if corrupt:
        conf = min(conf, 0.35)
    reading = Reading(
        minimap=minimap,
        route=route,
        bearing=bearing,
        far_bearing=far_bearing,
        arrow=_heading(crop),
        corrupt=corrupt,
        confidence=round(conf, 3),
        path=tr["path"] if tr is not None else (),
    )
    return reading, info


def _debug(crop: np.ndarray) -> dict:
    return _analyse(crop, keep=True)[1]
