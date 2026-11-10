"""Minimap reader for GTA V, colour-model variant.

read(crop) -> Reading for the bottom-left HUD corner (170 x 260 x 3 uint8 RGB).

How it works
  1. Colour model.  Every pixel is looked up in a table over RGB quantised to 6 bits per channel.  The table was
     fitted on the dev labels (train.py): histograms of route pixels against histograms of everything else, turned
     into a posterior; it yields "strong" (route core) and "weak" (blended edge, thin far line) for yellow and purple.
     World-yellow road markings have the same colour as the yellow route, so colour alone never decides.
  2. Geometry.  A route is the connected ribbon of route-coloured pixels that starts at the arrow.  It is accepted
     only if it is thin, pure, has a clean flank, leaves the near circle on one side only, stays inside the map
     rectangle and is not the continuation of a yellow line that is visible outside the map.
  3. Trace.  The ribbon is followed from the arrow in geodesic order to the circles of radius NEAR_R and FAR_R.
  4. The rest: HUD bars decide whether there is a minimap at all, a rendered dart matched at 24 rotations gives the
     arrow heading, a small logistic regression on a width spectrum of the map tells flat from tilted, and the
     blockiness of the 8-px coding grid tells whether the picture is damaged.

Only numpy and cv2, no files read at run time; all learnt parameters are the constants below.
"""
from __future__ import annotations

import base64
import math
import zlib

import cv2
import numpy as np

from contract import ARROW_XY, FAR_R, NEAR_R, Reading

# ----------------------------------------------------------------------------------------------- learnt constants
# (written by bake.py from train.py / train_tilt.py / arrow_model.py; do not edit by hand)
# BAKED-BEGIN
_LUT_Z = (
    "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"
    "TOD1AGK1/j/7KNBW"
)
_TILT_W = (9.48615, 1.21229, -4.51593, 0.60395, 2.13500, -3.55399, -2.94202, -4.58838, -1.16140, -3.52883, 0.44172, 2.28057, 0.42309, -0.20388, -0.73958, 3.09396, 0.32619, 2.13662, -0.27456, 1.35403, -1.59984, -11.96994, 7.72891, 1.21731)
_ARROW = dict(tip=5.2, bx=3.4, by=3.2, notch=1.8, ow=1.0, cy=-0.5)
# BAKED-END

# ------------------------------------------------------------------------------------------- measured constants
AX, AY = ARROW_XY                                # arrow centre, verified on the mean of all crops: (123, 117)
MX0, MX1, MY0, MY1 = 34, 214, 28, 142            # map rectangle, half-open (edges measured on the mean image)
BAR_ROWS = (146, 150)                            # coloured core of the three bars
BAR_COLS = ((38, 118), (130, 164), (175, 209))   # health, armour, special ability

SEED_R = 13                                      # a route has strong pixels this close to the arrow centre
# Acceptance limits per colour, set from the route frames of the two recordings (yellow k 817..1092: purity
# p1 0.42, strong p1 65, half width p99 5.85; purple k 1389..1432: purity p1 0.65, strong p1 133).
# max_half_width is the largest inscribed radius of the ribbon inside the near circle.  World markings in
# route yellow start at 7.1, so yellow stays tight; nothing in the world has the route purple, so purple may
# be looser, which keeps a route that folds back on itself right at the arrow (k 1420: 6.56).
ROUTE = {
    "yellow": dict(min_strong=40, min_purity=0.40, max_half_width=6.5),
    "purple": dict(min_strong=60, min_purity=0.55, max_half_width=7.5),
}
MAX_HALO = 0.25                                  # share of route-coloured pixels 2..3 px beside the ribbon
MIN_REACH = 22                                   # shorter than this is a blip beside the arrow, not a route
START_ON = 7.5                                   # ribbon starts this close to the arrow centre: on the route
START_BESIDE = 12.0                              # ... or beside the arrow, accepted in a clean picture only
# A second way out of the near circle, more than 60 degrees from the first and reached less than one
# radius later, means two branches leave the arrow: a line passing by, or a world marking touching the route
# (k 909: 18 steps).  A route that folds back reaches its second way out later (k 1054, 1055: 46, 39).
SECOND_WAY_GAP = NEAR_R
CORRUPT_T = 100                                  # excess of clean steps on the 8-px grid over off the grid
LOCAL_DAMAGE_T = 50                              # the same inside the 64 x 64 window around the arrow
ARROW_MIN = 0.42                                 # below this match score the arrow is not readable
ARROW_PRESENT = 0.50                             # an arrow this clear proves a minimap without the bars

# ------------------------------------------------------------------------------------------------- derived tables
if _LUT_Z:
    LUT = np.frombuffer(zlib.decompress(base64.b64decode(_LUT_Z)), np.uint8).copy()
else:  # not baked yet (only while training)
    LUT = np.zeros(64 ** 3, np.uint8)

_yy, _xx = np.mgrid[0:170, 0:260]
DIST = np.hypot(_xx - AX, _yy - AY).astype(np.float32)
ANG = np.degrees(np.arctan2(_xx - AX, -(_yy - AY))).astype(np.float32)      # 0 = up, clockwise positive
SIN, COS = np.sin(np.radians(ANG)), np.cos(np.radians(ANG))
SEED = DIST <= SEED_R
ROI = np.zeros((170, 260), np.uint8)             # where a route may be traced: the map and 14 px around it
ROI[MY0 - 14:MY1, MX0 - 14:MX1 + 14] = 1
INMAP = np.zeros((170, 260), bool)
INMAP[MY0:MY1, MX0:MX1] = True
OUT = np.ones((170, 260), bool)                  # clearly outside the map (not the bars)
OUT[MY0 - 3:MY1 + 12, MX0 - 3:MX1 + 3] = False
BOTTOM = (_yy >= MY1 - 3) & (_yy < MY1)
DISC = {R: (DIST <= R).astype(np.uint8) for R in (NEAR_R, FAR_R)}
SHELL = {R: ((DIST > R) & (DIST <= R + 2)).astype(np.uint8) for R in (NEAR_R, FAR_R)}
NWIN = (slice(AY - NEAR_R - 3, MY1), slice(AX - NEAR_R - 3, AX + NEAR_R + 4))   # window holding the near circle
K3 = np.ones((3, 3), np.uint8)
K5 = np.ones((5, 5), np.uint8)
K7 = np.ones((7, 7), np.uint8)
K_THIN = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
_NONE = Reading("none", "none", None, None, None, False, 0.0)


# ---------------------------------------------------------------------------------------------------------- arrow
_AH = 9                                          # the arrow patch is 19 x 19


def _dart(theta, tip, bx, by, notch, ow, cy, ss=8):
    """Template (+1 inside the dart, -1 on its dark outline) and weight (0 outside both), 19 x 19."""
    n = (2 * _AH + 1) * ss
    t = math.radians(theta)
    rot = np.array([[math.cos(t), -math.sin(t)], [math.sin(t), math.cos(t)]])
    pts = np.array([[0, -tip], [bx, by], [0, notch], [-bx, by]], np.float64) @ rot.T + [0.0, cy]
    inner = np.zeros((n, n), np.uint8)
    cv2.fillPoly(inner, [np.round((pts + _AH + 0.5) * ss).astype(np.int32)], 1)
    k = int(round(ow * ss)) * 2 + 1
    ring = cv2.dilate(inner, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))) - inner
    down = lambda m: m.reshape(2 * _AH + 1, ss, 2 * _AH + 1, ss).mean((1, 3))
    a, b = down(inner.astype(np.float64)), down(ring.astype(np.float64))
    return (a - b).ravel(), (a + b).ravel()


def _dart_bank(step=15):
    T, W = [], []
    for ang in range(0, 360, step):
        t, w = _dart(ang, **_ARROW)
        mu = (w * t).sum() / w.sum()
        T.append(w * (t - mu) / math.sqrt((w * (t - mu) ** 2).sum()))
        W.append(w)
    W = np.array(W, np.float32)
    return np.array(T, np.float32), W, W.sum(1)


ARROW_T, ARROW_W, ARROW_SW = _dart_bank()


def _arrow(grey):
    """(heading in degrees, match score -1..1): weighted correlation with the dart at 24 rotations."""
    p = grey[AY - _AH:AY + _AH + 1, AX - _AH:AX + _AH + 1].astype(np.float32).ravel()
    var = ARROW_W @ (p * p) - (ARROW_W @ p) ** 2 / ARROW_SW
    s = (ARROW_T @ p) / np.sqrt(np.maximum(var, 1e-3))
    i = int(s.argmax())
    a, b, c = float(s[i - 1]), float(s[i]), float(s[(i + 1) % len(s)])
    den = a - 2 * b + c
    off = 0.5 * (a - c) / den if den < 0 else 0.0
    return float(((i + off) * 15.0 + 180.0) % 360.0 - 180.0), b


# ----------------------------------------------------------------------------------------------------------- bars
def _bars(crop):
    """How many of the three HUD bars have their colour (health green or red, armour blue, special amber)."""
    band = crop[BAR_ROWS[0]:BAR_ROWS[1]:2]
    (hr, hg, hb), (ar, ag, ab), (sr, sg, sb) = (
        np.median(band[:, x0:x1:2].reshape(-1, 3), axis=0) for x0, x1 in BAR_COLS)
    health = (hg - hr >= 18 and hg - hb >= 18) or (hr - hg >= 45 and hr - hb >= 40)
    armour = ab - ar >= 8 and ab >= ag - 12 and ag >= ar - 5
    special = sr - sb >= 90 and sr >= sg and sg - sb >= 60
    return int(health) + int(armour) + int(special)


# --------------------------------------------------------------------------------------------------------- damage
def _damage(grey):
    """Stream damage shows as flat blocks with sharp edges on the 8-px coding grid (crop x = 2 mod 8, y = 6 mod 8).
    Counts "clean steps" (a jump of >= 18 between two pixels with flat neighbours on both sides) on the grid minus
    the same count half a block away, over the whole picture above the bars and in the window around the arrow."""
    g = grey.astype(np.int16)
    cnt = []
    for o in (0, 4):                                              # vertical boundaries: on the grid, off the grid
        a, b, c, d = g[:, o:256:8], g[:, o + 1:256:8], g[:, o + 2:256:8], g[:, o + 3:256:8]
        cnt.append((np.abs(c - b) >= 18) & (np.abs(b - a) <= 6) & (np.abs(d - c) <= 6))
    for o in (4, 0):                                              # horizontal boundaries
        a, b, c, d = g[o:168:8], g[o + 1:168:8], g[o + 2:168:8], g[o + 3:168:8]
        cnt.append((np.abs(c - b) >= 18) & (np.abs(b - a) <= 6) & (np.abs(d - c) <= 6))
    von, voff, hon, hoff = cnt
    von[:, 4] = False                                             # x = 34: left edge of the map
    voff[:, 26] = False                                           # x = 214: right edge of the map
    cz = np.count_nonzero
    glob = cz(von[:140]) + cz(hon[:17]) - cz(voff[:140]) - cz(hoff[:17])
    loc = cz(von[78:142, 11:20]) + cz(hon[9:17, 90:154]) - cz(voff[78:142, 11:19]) - cz(hoff[10:18, 90:154])
    return int(glob), int(loc)


# ----------------------------------------------------------------------------------------------- flat / tilted
_KS = {s: np.ones((s, s), np.uint8) for s in (3, 5, 9, 15)}
_BANDS = ((2, 24), (24, 46), (46, 68), (68, 90), (90, 112))


def _tilt_features(grey):
    """Width spectrum of the bright structure (roads) in five horizontal bands of the map, and edge statistics.
    A tilted map has thin, dense roads at the top and wide ones at the bottom; a flat one looks alike everywhere."""
    m = grey[MY0:MY1, MX0:MX1]
    prev, lev = m, []
    for s in (3, 5, 9, 15):
        o = cv2.morphologyEx(m, cv2.MORPH_OPEN, _KS[s])
        lev.append(cv2.subtract(prev, o))
        prev = o
    F = np.array([[cv2.mean(l[a:b])[0] for l in lev] for a, b in _BANDS])
    tot = F.sum(1) + 2.0
    g = m.astype(np.int16)
    dx = np.abs(g[:, 2:] - g[:, :-2]).mean(1)
    dy = np.abs(g[2:, :] - g[:-2, :]).mean(1)
    e = []
    for a, b in ((2, 40), (40, 76), (76, 112)):
        ex, ey = dx[a:b].mean() + 1, dy[a:b].mean() + 1
        e += [math.log(ey / ex), math.log(ex + ey)]
    e.append(float((dy * np.arange(len(dy))).sum() / (dy.sum() + 1) / 112))
    e.append(float((dx * np.arange(len(dx))).sum() / (dx.sum() + 1) / 112))
    return np.concatenate([(F[:, 0] + F[:, 1]) / tot, F[:, 3] / tot, np.log(tot), e])


def _tilted_prob(grey):
    if len(_TILT_W) == 0:
        return 0.5
    z = float(np.dot(_tilt_features(grey), _TILT_W[:-1]) + _TILT_W[-1])
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))


# ---------------------------------------------------------------------------------------------------------- route
def _classes(crop):
    q = (crop >> 2).astype(np.int32)
    return LUT[(q[..., 0] << 12) | (q[..., 1] << 6) | q[..., 2]]


def _attached(mask, seeds):
    """The connected component (8-neighbour) of `mask` that holds most `seeds` pixels, as uint8, or None."""
    n, lab = cv2.connectedComponents(mask, connectivity=8)
    cnt = np.bincount(lab[seeds], minlength=n)
    cnt[0] = 0
    i = int(cnt.argmax())
    return (lab == i).view(np.uint8) if cnt[i] else None


def _mean_angle(mask, win=None):
    m = mask > 0
    s, c = (SIN, COS) if win is None else (SIN[win], COS[win])
    return math.degrees(math.atan2(float(s[m].sum()), float(c[m].sum())))


def _near(comp, seeds):
    """Follow the ribbon from the arrow inside the near circle, in geodesic order.
    Returns (bearing, crossed, part, gap): the bearing of the way out that is reached first (where the ribbon
    crosses the circle, or where it runs off the bottom edge of the map), or of the point reached last if the
    ribbon ends inside; `part` is the ribbon inside the circle; `gap` is how many steps later a second way out,
    more than 60 degrees from the first, is reached (None if there is none)."""
    w = NWIN
    c = comp[w]
    sd = seeds[w]
    part = _attached(c & DISC[NEAR_R][w], sd)
    if part is None:
        return None, False, None, None
    shell = SHELL[NEAR_R][w]
    ways = (cv2.dilate(part, K3) & c & shell) | (part & BOTTOM[w].view(np.uint8))
    dom = part | ways
    cur = (sd & (part > 0)).view(np.uint8)
    G = np.full(c.shape, 999, np.int32)
    G[cur > 0] = 0
    last = cur
    for it in range(1, 200):
        nxt = cv2.dilate(cur, K3) & dom
        new = nxt & ~cur
        if not new.any():
            break
        G[new > 0] = it
        last, cur = new, nxt
    full = np.zeros(comp.shape, np.uint8)
    full[w] = part
    if not ways.any():
        return _mean_angle(last, w), False, full, None
    n, lab = cv2.connectedComponents(ways, connectivity=8)
    cl = []
    for i in range(1, n):
        m = lab == i
        cl.append((int(G[m].min()), _mean_angle(m, w), bool((m & (shell > 0)).any())))
    cl.sort()
    g0, a0, ring0 = cl[0]
    gap = None
    for g, a, _ in cl[1:]:
        if abs((a - a0 + 180) % 360 - 180) > 60:
            gap = g - g0
            break
    return a0, ring0, full, gap


def _far(comp, seeds, near):
    """Bearing where the ribbon leaves the far circle (of several exits the one closest in angle to the near
    bearing), else the bearing of its farthest point; and whether it crossed."""
    part = _attached(comp & DISC[FAR_R], seeds)
    if part is None:
        return None, False
    exits = cv2.dilate(part, K3) & comp & SHELL[FAR_R]
    if exits.any():
        n, lab = cv2.connectedComponents(exits, connectivity=8)
        if n == 2 or near is None:
            return _mean_angle(exits), True
        return min((_mean_angle(lab == i) for i in range(1, n)), key=lambda a: abs((a - near + 180) % 360 - 180)), True
    d = np.where(part > 0, DIST, -1.0)
    return _mean_angle(d >= d.max() - 2.5), False


def _on_world_line(part, s_out):
    """True if the ribbon lies on the straight continuation of a route-coloured line that is visible outside
    the map (a road marking of the game world seen through the map)."""
    n, lab, stats, _ = cv2.connectedComponentsWithStats(cv2.dilate(s_out, K3), connectivity=8)
    ys, xs = np.nonzero(part)
    for i in np.argsort(-stats[1:, cv2.CC_STAT_AREA])[:4] + 1:
        if stats[i, cv2.CC_STAT_AREA] < 40:
            break
        py, px = np.nonzero(lab == i)
        vx, vy, x0, y0 = cv2.fitLine(np.column_stack([px, py]).astype(np.float32), cv2.DIST_L2, 0, 0.01, 0.01).ravel()
        along = (px - x0) * vx + (py - y0) * vy
        across = np.abs((px - x0) * vy - (py - y0) * vx)
        if along.max() - along.min() < 15 or across.mean() * 4 > along.max() - along.min():
            continue                                               # a blob, not a line
        if (np.abs((xs - x0) * vy - (ys - y0) * vx) <= 6).mean() >= 0.6:
            return True
    return False


def _route(cls, code):
    """Features of the route-coloured ribbon attached to the arrow (code 1 = yellow, 3 = purple), or None."""
    S8 = (cls == code + 1).view(np.uint8) & ROI
    seeds = (S8 > 0) & SEED
    if np.count_nonzero(seeds) < 4:
        return None
    A = ((cls == code).view(np.uint8) & ROI) | S8
    # ribbon mask: strong pixels and the weak pixels right next to them, 1-px gaps closed
    comp = _attached(cv2.morphologyEx(S8 | (A & cv2.dilate(S8, K5)), cv2.MORPH_CLOSE, K3), seeds)
    if comp is None:
        return None
    S = S8 > 0
    seeds = (comp > 0) & SEED
    near, crossed, part, gap = _near(comp, seeds)
    if part is None:
        return None
    partb = part > 0
    f = {"near": near, "near_cross": crossed, "gap": gap}
    f["strong"] = int(np.count_nonzero(S & partb))
    if f["strong"] == 0:
        return None
    f["area"] = int(np.count_nonzero(partb))
    f["purity"] = f["strong"] / f["area"]
    f["half_width"] = float(cv2.distanceTransform(part[NWIN], cv2.DIST_L2, 3).max())
    f["start"] = float(DIST[S & partb].min())
    f["reach"] = float(DIST[comp > 0].max())
    f["n_out"] = int(np.count_nonzero(S & (comp > 0) & OUT))
    flank = (cv2.dilate(part, K7) > 0) & ~(cv2.dilate(part, K3) > 0) & INMAP
    f["halo"] = float(A[flank].mean()) if flank.any() else 1.0
    s_all = cls == code + 1
    f["clutter"] = int(np.count_nonzero(s_all & INMAP & ~(cv2.dilate(comp, K7) > 0)))
    s_out = s_all & OUT
    f["s_out"] = int(np.count_nonzero(s_out))
    f["part"], f["comp"], f["A"], f["s_out_mask"] = part, comp, A, s_out
    return f


def _accept(f, colour, loc):
    """The geometric tests.  Returns None if the ribbon is a route, else the name of the test that failed."""
    lim = ROUTE[colour]
    if f["strong"] < lim["min_strong"]:
        return "few strong pixels"
    if f["purity"] < lim["min_purity"]:
        return "impure"
    if f["halo"] > MAX_HALO:
        return "route colour beside the ribbon"
    if f["half_width"] > lim["max_half_width"]:
        return "too wide"
    if f["reach"] < MIN_REACH:
        return "too short"
    if f["n_out"] > 6:
        return "continues outside the map"
    if f["gap"] is not None and f["gap"] < SECOND_WAY_GAP:
        return "passes the arrow on both sides"
    if f["start"] > START_ON:
        clean = f["clutter"] <= 80 and f["s_out"] <= 10 and f["strong"] >= 80 and loc < LOCAL_DAMAGE_T
        if f["start"] > START_BESIDE or not clean:
            return "does not start at the arrow"
    if loc >= LOCAL_DAMAGE_T and (f["purity"] < 0.55 or f["strong"] < 80 or f["start"] > START_ON):
        return "damage around the arrow"
    if f["s_out"] >= 25 and _on_world_line(f["part"], f["s_out_mask"].view(np.uint8)):
        return "continues a line outside the map"
    return None


def _far_bearing(f, seeds):
    far, crossed = _far(f["comp"], seeds, f["near"])
    if not crossed:
        # the far part of a route is thin and pale: let it continue over weak pixels of thin structures
        A = f["A"]
        thin = A & ~cv2.morphologyEx(A, cv2.MORPH_OPEN, K_THIN)
        comp2 = _attached(cv2.morphologyEx(f["comp"] | thin, cv2.MORPH_CLOSE, K3), seeds)
        if comp2 is not None:
            far2, crossed2 = _far(comp2, seeds, f["near"])
            if crossed2:
                return far2, True
    return far, crossed


# ------------------------------------------------------------------------------------------------------- read
def _analyse(crop):
    """Everything read() needs, as a dict (also used by the debug tools)."""
    grey = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    bars = _bars(crop)
    arrow, score = _arrow(grey)
    glob, loc = _damage(grey)
    d = {"bars": bars, "arrow": arrow, "arrow_score": score, "dmg": glob, "dmg_loc": loc,
         "present": bars >= 2 or score >= ARROW_PRESENT, "route": "none", "cand": {}, "why": {}}
    if not d["present"]:
        return d
    cls = _classes(crop)
    d["cls"] = cls
    best = None
    for colour, code in (("yellow", 1), ("purple", 3)):
        f = _route(cls, code)
        if f is None:
            continue
        d["cand"][colour] = f
        why = _accept(f, colour, loc)
        d["why"][colour] = why
        if why is None and (best is None or f["strong"] > d["cand"][best]["strong"]):
            best = colour
    if best is not None:
        f = d["cand"][best]
        d["route"] = best
        d["far"], d["far_cross"] = _far_bearing(f, (f["comp"] > 0) & SEED)
    d["p_tilted"] = _tilted_prob(grey)
    return d


def _read(crop):
    d = _analyse(crop)
    corrupt = bool(d["dmg"] >= CORRUPT_T)
    if not d["present"]:
        return Reading("none", "none", None, None, None, corrupt, 0.5 if corrupt else 0.9)
    arrow = d["arrow"] if d["arrow_score"] >= ARROW_MIN else None
    if d["route"] == "none":
        conf = 0.9 if not d["cand"] else 0.7                       # a candidate was seen and rejected
        if corrupt:
            conf *= 0.6
        return Reading("tilted" if d["p_tilted"] > 0.5 else "flat", "none", None, None, arrow, corrupt, round(conf, 3))
    f = d["cand"][d["route"]]
    conf = 0.95
    if corrupt:
        conf *= 0.6
    if d["dmg_loc"] >= LOCAL_DAMAGE_T:
        conf *= 0.6
    if f["clutter"] > 150 or f["s_out"] > 30:
        conf *= 0.8                                                # other route-coloured things in the picture
    if f["start"] > START_ON:
        conf *= 0.8
    if not f["near_cross"]:
        conf *= 0.9                                                # route ends inside the near circle
    if f["gap"] is not None:
        conf *= 0.8                                                # a second way out: the route folds back
    if arrow is None:
        conf *= 0.8
    # a route is drawn only in a vehicle, where the map is tilted
    far = None if d["far"] is None else float(d["far"])
    return Reading("tilted", d["route"], float(f["near"]), far, arrow, corrupt, round(float(conf), 3))


def read(crop: np.ndarray) -> Reading:
    try:
        if getattr(crop, "shape", None) != (170, 260, 3):
            return _NONE
        return _read(np.ascontiguousarray(crop, dtype=np.uint8))
    except Exception:
        return _NONE


def debug(crop):
    """Masks and numbers for the overlay tool (not used by read)."""
    d = _analyse(np.ascontiguousarray(crop, dtype=np.uint8))
    out = {}
    if "cls" in d:
        cls = d["cls"]
        out.update(weak_y=cls == 1, strong_y=cls == 2, weak_p=cls == 3, strong_p=cls == 4)
        comp = np.zeros(cls.shape, bool)
        for f in d["cand"].values():
            comp |= f["comp"] > 0
        out["comp"] = comp
    info = [f"bars={d['bars']} arrow={d['arrow_score']:.2f} dmg={d['dmg']}/{d['dmg_loc']}"]
    if "p_tilted" in d:
        info.append(f"tilt={d['p_tilted']:.2f}")
    for colour, f in d["cand"].items():
        info.append(colour[0] + ":" + (d["why"][colour] or "OK") + " " + " ".join(
            f"{k}={f[k]:.2f}" if isinstance(f[k], float) else f"{k}={f[k]}"
            for k in ("strong", "purity", "halo", "half_width", "start", "reach", "gap", "n_out", "clutter", "s_out")))
    out["info"] = " | ".join(info)
    return out
