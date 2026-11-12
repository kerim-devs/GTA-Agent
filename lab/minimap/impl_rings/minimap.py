"""GTA V minimap reader, RING SCAN variant.

Route.  A per-pixel route-colour score (yellow, purple) is sampled on 33 concentric circles around the
player arrow (radius 6, 8, .. 70 px, 240 angles each, sample coordinates precomputed).  Every circle is cut
into angular runs of route colour (the peaks); dynamic programming links the runs from the innermost
circles outwards (cost for lateral jumps and for skipped circles, so icons on the route and block damage
are bridged).  The ends of the resulting tree are the candidate paths.  They are ranked by a quality that
counts wide stretches for little (a route is a 4..8 px line, markings of the game world that shine through
the map are wider), and the best one must pass the tests of a route: it comes out from under the arrow
(or begins right beside it and is then flawless), it is supported on nearly all of its circles, it is
saturated next to the arrow, it is not wide, and it is not one arm of a straight line that goes on behind
or beside the arrow (that is a marking of the world).  A refused path takes its variants with it.
The bearings are the path's angles on the circles NEAR_R and FAR_R (its end point if it is shorter).

Arrow.  Normalised correlation of the arrow window with 48 rendered, rotated dart templates; the match
quality, together with the three bars below the map, also says whether a minimap is there at all.
Flat or tilted: a small logistic model on texture features (perspective packs thin horizontal lines into
the upper part of the map).  Corrupt: 16 px pieces of the codec's block grid that are clean steps, compared
with the same count off the grid.

Confidence is how far to trust `route` and `bearing`: high for a clean, complete line and for "none" on a
clean picture with nothing route-like at the arrow, lower on damaged pictures and after a refused path,
0 without a minimap.

Self-contained: numpy and cv2 only, no files read at run time, pure function `read(crop) -> Reading`.
"""

from __future__ import annotations

import math

import cv2
import numpy as np

from contract import FAR_R, NEAR_R, Reading

# ----------------------------------------------------------------------------------------------- geometry
H, W = 170, 260
CX, CY = 123.5, 116.0  # measured centre of the player arrow (tip 123.5/111, feet 119..128/121)
MX0, MX1, MY0, MY1 = 35, 213, 29, 140  # map rectangle that is safe to sample (inclusive)

R0, RSTEP, NR = 6, 2, 33  # rings at 6, 8, .. 70 px
RADII = R0 + RSTEP * np.arange(NR)
NA = 240  # angles per full turn (1.5 degrees)
PAD = 24  # the angular axis is extended by PAD bins on both sides so that runs never wrap
NC = NA + 2 * PAD
DEG = 360.0 / NA
ANG0 = -180.0 - PAD * DEG  # angle of column 0; 0 degrees = up, clockwise positive
_ang = np.deg2rad(ANG0 + DEG * np.arange(NC))
_xs = CX + RADII[:, None] * np.sin(_ang)[None, :]
_ys = CY - RADII[:, None] * np.cos(_ang)[None, :]
_xi = np.rint(_xs).astype(np.int64)
_yi = np.rint(_ys).astype(np.int64)
RING_OK = (_xi >= MX0) & (_xi <= MX1) & (_yi >= MY0) & (_yi <= MY1)
RING_IDX = np.where(RING_OK, _yi * W + _xi, 0)
ARC = RADII * math.radians(DEG)  # px per angular bin on every ring
I_NEAR = (NEAR_R - R0) // RSTEP
I_FAR = (FAR_R - R0) // RSTEP

# ------------------------------------------------------------------------------------------ route tracing
RUN_THR = 90  # ring score (0..255) that counts as route colour
START_R = 12  # the path has to begin on a ring of at most this radius (the route can start abeam of the arrow)
N_LEAVES = 8  # candidate paths looked at per colour
# what a path must show to count as a route (measured on about 310 route frames of the recordings)
MIN_R1 = 22  # it reaches at least this radius
MIN_SUP = 0.85  # share of its rings that carry route colour (true ones: yellow >= 0.94, purple >= 0.88)
MIN_SUP_CORRUPT = 0.9  # the same on a damaged picture, where a smear easily bridges to something else
MIN_SUP_OFFSET = 0.95  # the same for a path that begins beside the arrow (true ones: 1.0)
MIN_NEAR_Y, MIN_NEAR_P = 0.72, 0.6  # mean score of its runs up to NEAR_R (true: yellow >= 0.73, purple >= 0.60)
MAX_WID = 10.5  # median line width in px (true ones: 3.4 .. 9.3, one 10.2)
MAX_ANTI = 0.5  # share of rings with route colour straight opposite, behind the arrow (true ones: <= 0.36)
MAX_MIRROR = 0.25  # the same for the mirror arm of a path that begins beside the arrow (true ones: <= 0.10)
MAX_GAP = 5  # rings a path may skip (icons on the route, block damage)
GAP_COST = 0.7
LAT_COST = 0.15  # per px of lateral jump between consecutive runs
MAX_RUNS = 400


def _score_maps(crop: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per-pixel route-colour scores (uint8, 3x3 smoothed): yellow, purple."""
    c = crop.astype(np.int16)
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    mn = np.minimum(r, g)
    sy = mn - b - np.abs(r - g)
    sy = np.clip((sy - 25) * 5, 0, 255)
    sy[mn < 150] = 0
    sp = np.minimum(r, b) - g - np.maximum(r - b, 0)
    sp = np.clip((sp - 20) * 6, 0, 255)
    return cv2.blur(sy.astype(np.uint8), (3, 3)), cv2.blur(sp.astype(np.uint8), (3, 3))


def _trace(score: np.ndarray):
    """Ring scan + DP.  Returns a list of candidate paths, best first.  A path is a list of
    (ring index, first bin, end bin (exclusive), mean score 0..1)."""
    ring = score.ravel()[RING_IDX]
    ring[~RING_OK] = 0
    on = ring >= RUN_THR
    if not on[: (START_R - R0) // RSTEP + 1].any():
        return [], on
    d = np.diff(on.astype(np.int8), axis=1, prepend=0, append=0)
    rr, a0 = np.nonzero(d == 1)
    a1 = np.nonzero(d == -1)[1]
    n = len(rr)
    if n == 0 or n > MAX_RUNS:
        return [], on
    cs = np.zeros((NR, NC + 1), np.int32)
    np.cumsum(ring, axis=1, out=cs[:, 1:])
    mean = (cs[rr, a1] - cs[rr, a0]) / ((a1 - a0) * 255.0)
    rr, a0, a1, mean = rr.tolist(), a0.tolist(), a1.tolist(), mean.tolist()
    i_start = (START_R - R0) // RSTEP
    arc = ARC.tolist()
    # nodes reached so far, per ring: (a0, a1, value, node id)
    reached: list[list[tuple[int, int, float, int]]] = [[] for _ in range(NR)]
    pred = [-1] * n
    val = [0.0] * n
    has_succ = [False] * n
    for k in range(n):
        i, s, e = rr[k], a0[k], a1[k]
        best = -(i * 0.5) if i <= i_start else -1e9
        bp = -1
        for j in range(i - 1, max(i - 2 - MAX_GAP, -1), -1):
            row = reached[j]
            if not row:
                continue
            skipped = i - j - 1
            lat_max = 3.0 + 3.0 * skipped
            for (bs, be, bv, bk) in row:
                gbin = s - be if s >= be else (bs - e if bs >= e else -1)
                lat = (gbin + 1) * arc[i]
                if lat > lat_max:
                    continue
                v = bv - GAP_COST * skipped - LAT_COST * lat
                if v > best:
                    best, bp = v, bk
        if best > -1e8:
            v = best + mean[k]
            val[k] = v
            pred[k] = bp
            if bp >= 0:
                has_succ[bp] = True
            reached[i].append((s, e, v, k))
    leaves = [k for row in reached for (_, _, _, k) in row if not has_succ[k]]
    leaves.sort(key=lambda k: -val[k])
    paths, seen = [], []
    for k in leaves[:40]:
        ids = []
        while k >= 0:
            ids.append(k)
            k = pred[k]
        if len(ids) < 4:
            continue
        sid = set(ids)
        if any(len(sid & o) > 0.75 * len(ids) for o in seen):
            continue  # the same path with another tail
        seen.append(sid)
        ids.reverse()
        paths.append([(rr[k], a0[k], a1[k], mean[k]) for k in ids])
        if len(paths) >= N_LEAVES:
            break
    return paths, on


def _bin_to_deg(a: float) -> float:
    d = ANG0 + DEG * a
    return (d + 180.0) % 360.0 - 180.0


def _node_angles(path) -> list[float]:
    """Representative angular position (in bins) of the path on each of its rings."""
    out = []
    n = len(path)
    for q in range(n):
        i, s, e, _ = path[q]
        c = 0.5 * (s + e - 1)
        if (e - s) * ARC[i] > 9.0:  # wide run: the route runs along the circle; use where it leaves
            if q + 1 < n:
                _, s2, e2, _ = path[q + 1]
                lo, hi = max(s, s2), min(e, e2)
                c = 0.5 * (lo + hi - 1) if hi > lo else (e - 1 if s2 >= e else s)
            elif q > 0:
                prev = out[-1]
                c = e - 1 - 3.0 / ARC[i] if abs(e - 1 - prev) > abs(s - prev) else s + 3.0 / ARC[i]
        out.append(c)
    return out


def _angle_at(path, angles, i_ring: int) -> float:
    """Path angle (bins) at a ring; interpolated in gaps, the end point when the path ends earlier."""
    prev = None
    for q, node in enumerate(path):
        i = node[0]
        if i == i_ring:
            return angles[q]
        if i > i_ring:
            if prev is None:
                return angles[q]
            ip, ap = prev
            t = (i_ring - ip) / (i - ip)
            return ap + t * (angles[q] - ap)
        prev = (i, angles[q])
    return angles[-1]


def _path_xy(path, angles) -> list[tuple[float, float]]:
    pts = []
    for (i, _, _, _), a in zip(path, angles):
        t = math.radians(ANG0 + DEG * a)
        r = R0 + RSTEP * i
        pts.append((CX + r * math.sin(t), CY - r * math.cos(t)))
    return pts


_ANTI_TOL = [int(math.ceil(math.degrees(2.0 * math.asin(min(1.0, 5.0 / r))) / DEG)) + 2 for r in RADII.tolist()]
W_NARROW, W_WIDE = 8.0, 11.0  # px: a route is at most about 8 px wide, markings of the world are wider


def _path_features(path, angles, on: np.ndarray) -> dict:
    """What a candidate path looks like: where it begins and ends, how completely and how strongly it is
    supported, how wide the line is, and whether it is part of a straight line that misses the arrow."""
    n = len(path)
    i_last = path[-1][0]
    pts = _path_xy(path, angles)
    f = {
        "r0": R0 + RSTEP * path[0][0],
        "r1": R0 + RSTEP * i_last,
        "n": n,
        "sup": n / (i_last - path[0][0] + 1),
    }
    near = [p[3] for p in path if p[0] <= I_NEAR]
    f["mnear"] = sum(near) / len(near) if near else 0.0
    # true line width per node: the angular width shrinks with the angle between path and radius
    tw = []
    q = 0.0
    prev_i = path[0][0] - 1
    for j, (i, s, e, m) in enumerate(path):
        x, y = pts[j]
        (xa, ya), (xb, yb) = pts[max(j - 2, 0)], pts[min(j + 2, n - 1)]
        dx, dy, ux, uy = xb - xa, yb - ya, x - CX, y - CY
        dl = math.hypot(dx, dy)
        c = abs(dx * ux + dy * uy) / (dl * math.hypot(ux, uy)) if dl > 0.5 else 1.0
        w = (e - s) * ARC[i] * c
        tw.append(w)
        g = 1.0 if w <= W_NARROW else (0.2 if w >= W_WIDE else 1.0 - 0.8 * (w - W_NARROW) / (W_WIDE - W_NARROW))
        q += m * g - GAP_COST * (i - prev_i - 1)
        prev_i = i
    f["q"] = q  # what the path is worth as a route: its score, wide stretches counted for little
    tws = sorted(tw)
    f["wid"] = tws[n // 2]
    f["ns"] = sum(1 for w in tw if w <= W_NARROW + 0.5) / n
    # markings of the world that only look like a route are straight lines that do not end at the arrow.
    # (1) does the colour go on behind the arrow, opposite to the path, ring by ring?
    hit = cnt = 0
    for (i, _, _, _), a in zip(path, angles):
        if i < 5 or i > 22:
            continue
        ap = (a - PAD + NA // 2) % NA + PAD
        c = int(ap + 0.5)
        if not RING_OK[i, c]:
            continue
        t = _ANTI_TOL[i]
        cnt += 1
        if on[i, max(c - t, 0): c + t + 1].any():
            hit += 1
    f["anti"] = hit / cnt if cnt >= 4 else 0.0
    f["antin"] = cnt
    # (2) a path that begins beside the arrow: is it one arm of a line that passes by?  Then the other
    # arm is its mirror image about the radius through the starting point.
    i0, s0, e0, _ = path[0]
    f["mir"] = 0.0
    if i0 > 0:
        a_start = 0.5 * (s0 + e0 - 1)
        hit = cnt = 0
        for (i, s, e, _) in path[1:]:
            if i > i0 + 13:
                break
            if i < i0 + 2:
                continue
            c = int(2.0 * a_start - 0.5 * (s + e - 1) + 0.5)
            c = (c - PAD) % NA + PAD
            t = int(3.0 / ARC[i]) + 2
            if not RING_OK[i, c] or (c + t >= s and c - t < e):
                continue  # outside the map, or the path itself
            cnt += 1
            if on[i, max(c - t, 0): c + t + 1].any():
                hit += 1
        f["mir"] = hit / cnt if cnt >= 4 else -1.0
        f["mirn"] = cnt
    return f


# ------------------------------------------------------------------------------------------- player arrow
# The arrow is a dart (blunt tip, notched base) with a dark outline and a white inside.  Outlines measured
# on upright arrows, in px relative to the point the sprite turns about, y down.
ARROW_C = (123.3, 116.0)  # tuned on on-foot frames (best mean correlation, fewest heading jumps)
ARROW_SCALE = 0.95
_ARROW_OUTER = [(-1.3, -5.9), (1.3, -5.9), (4.95, 3.2), (4.95, 5.1), (3.0, 5.1), (2.5, 4.5), (0.0, 4.3),
                (-2.5, 4.5), (-3.0, 5.1), (-4.95, 5.1), (-4.95, 3.2)]
_ARROW_INNER = [(0.0, -4.0), (3.2, 2.6), (3.2, 3.2), (1.4, 3.2), (0.0, 2.0), (-1.4, 3.2), (-3.2, 3.2), (-3.2, 2.6)]
AX0, AY0, AW, AH = 115, 108, 18, 18  # arrow window: x 115..132, y 108..125
NT = 48  # arrow headings tried (7.5 degrees apart)
_SHIFTS = [(dx, dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1)]


def _make_arrow_templates():
    up = 8
    ts, ms = [], []
    for j in range(NT):
        t = math.radians(j * 360.0 / NT)
        c, sn = math.cos(t), math.sin(t)

        def poly(pts, grow=0.0):
            out = []
            for x, y in pts:
                x, y = x * ARROW_SCALE, y * ARROW_SCALE
                if grow:
                    n = math.hypot(x, y - 1.0)
                    x, y = x + grow * x / n, y + grow * (y - 1.0) / n
                xr, yr = x * c - y * sn, x * sn + y * c
                out.append(((ARROW_C[0] + xr - AX0 + 0.5) * up - 0.5, (ARROW_C[1] + yr - AY0 + 0.5) * up - 0.5))
            return np.round(np.array(out)).astype(np.int32)

        img = np.zeros((AH * up, AW * up), np.float32)
        msk = np.zeros((AH * up, AW * up), np.float32)
        cv2.fillPoly(msk, [poly(_ARROW_OUTER, 1.6)], 1.0)
        cv2.fillPoly(img, [poly(_ARROW_OUTER, 1.6)], 0.2)
        cv2.fillPoly(img, [poly(_ARROW_OUTER)], -2.0)
        cv2.fillPoly(img, [poly(_ARROW_INNER)], 1.0)
        img = cv2.resize(img, (AW, AH), interpolation=cv2.INTER_AREA)
        m = (cv2.resize(msk, (AW, AH), interpolation=cv2.INTER_AREA) > 0.5).astype(np.float32)
        img = (img - (img * m).sum() / m.sum()) * m
        img /= np.linalg.norm(img)
        ts.append(img.ravel())
        ms.append(m.ravel())
    return np.array(ts, np.float32), np.array(ms, np.float32)


_ARROW_T, _ARROW_M = _make_arrow_templates()
_ARROW_N = _ARROW_M.sum(axis=1)


def _arrow(white: np.ndarray) -> tuple[float, float]:
    """Heading of the player arrow in degrees and the match quality (normalised correlation, -1..1).
    `white` is min(R, G, B) as float32."""
    patches = np.empty((len(_SHIFTS), AH * AW), np.float32)
    for n, (dx, dy) in enumerate(_SHIFTS):
        patches[n] = white[AY0 + dy:AY0 + dy + AH, AX0 + dx:AX0 + dx + AW].ravel()
    num = patches @ _ARROW_T.T
    s1 = patches @ _ARROW_M.T
    s2 = (patches * patches) @ _ARROW_M.T
    var = np.maximum(s2 - s1 * s1 / _ARROW_N, 1e-3)
    ncc = num / np.sqrt(var)
    j = int(np.argmax(ncc))
    q = float(ncc.flat[j])
    row, t = divmod(j, NT)
    # parabolic refinement between neighbouring headings
    a, b, c = float(ncc[row, (t - 1) % NT]), q, float(ncc[row, (t + 1) % NT])
    den = a - 2 * b + c
    off = 0.5 * (a - c) / den if den < -1e-6 else 0.0
    deg = (t + off) * 360.0 / NT
    return (deg + 180.0) % 360.0 - 180.0, q


# ------------------------------------------------------------------------------------- minimap class
_KV = np.ones((5, 1), np.uint8)
_KH = np.ones((1, 5), np.uint8)


def _bars(crop: np.ndarray) -> int:
    """How many of the three bars under the map (health, armour, special) show their colour."""
    seg = crop[146:150]
    h = np.median(seg[:, 38:118].reshape(-1, 3), axis=0)
    a = np.median(seg[:, 129:165].reshape(-1, 3), axis=0)
    s = np.median(seg[:, 174:211].reshape(-1, 3), axis=0)
    n = 0
    if h[1] - max(h[0], h[2]) >= 15 or h[0] - max(h[1], h[2]) >= 40:  # green, or red when hurt
        n += 1
    if a[2] - a[0] >= 8 and a[1] - a[0] >= 5:
        n += 1
    if min(s[0], s[1]) - s[2] >= 50 and s[0] - s[1] >= 2:
        n += 1
    return n


def _tilt_features(gray: np.ndarray) -> tuple[float, float, float, float]:
    """Texture cues for the perspective map: thin bright lines pile up in the upper part.
    Returns (share of thin-horizontal-line pixels on top, thin horizontal lines top vs bottom,
    thin horizontal vs thin vertical lines on top, thin horizontal lines on top relative to contrast)."""
    roi = gray[30:140, 38:210]
    smh = cv2.blur(roi, (5, 1))
    smv = cv2.blur(roi, (1, 5))
    thh = cv2.subtract(smh, cv2.morphologyEx(smh, cv2.MORPH_OPEN, _KV))
    thv = cv2.subtract(smv, cv2.morphologyEx(smv, cv2.MORPH_OPEN, _KH))
    top = thh[:36]
    hht = float(top.mean())
    hhb = float(thh[72:].mean())
    hvt = float(thv[:36].mean())
    sd = float(cv2.meanStdDev(roi)[1][0, 0])
    cht = float(cv2.countNonZero(cv2.compare(top, 18, cv2.CMP_GT))) / top.size
    return cht, hht / (hht + hhb + 2.0), hht / (hht + hvt + 2.0), hht / (sd + 5.0)


_XB = np.array([x for x in range(1, 259, 16) if x != 33])  # steps between x and x+1 on the 16 px block grid
_YB = np.array([y for y in range(13, 169, 16) if y not in (29, 141)])
_XC = np.concatenate([_XB[:-1] + 6, _XB[:-1] + 10])  # control lines off the grid
_YC = np.concatenate([_YB[:-1] + 6, _YB[:-1] + 10])


def _damage(gray: np.ndarray) -> tuple[float, float, float]:
    """Block damage: 16 px pieces of block-grid lines that are a clean step, compared with the same count
    on lines off the grid.  Returns (pieces on the grid, pieces off the grid (scaled), the same excess
    counted only around the arrow)."""
    g = gray.astype(np.int16)
    dx = np.abs(g[:160, 1:] - g[:160, :-1]) > 12  # 160 rows = 10 pieces
    dy = np.abs(g[1:, :256] - g[:-1, :256]) > 12  # 256 columns = 16 pieces
    cb = dx[:, _XB].reshape(10, 16, -1).sum(axis=1) >= 12  # (piece, line)
    cc = dx[:, _XC].reshape(10, 16, -1).sum(axis=1) >= 12
    rb = dy[_YB].reshape(len(_YB), 16, 16).sum(axis=2) >= 12  # (line, piece)
    rc = dy[_YC].reshape(len(_YC), 16, 16).sum(axis=2) >= 12
    on = float(cb.sum() + rb.sum())
    off = float(cc.sum()) * len(_XB) / len(_XC) + float(rc.sum()) * len(_YB) / len(_YC)
    # around the arrow: x 65..193, y 45..141 -> grid columns 4..11 (x 65..177), pieces 3..8; rows 2..7
    loc = float(cb[3:9, 4:12].sum() + rb[2:8, 4:12].sum()) - 0.5 * float(cc[3:9, 4:12].sum() + cc[3:9, 19:27].sum()) \
        - 0.5 * float(rc[2:7, 4:12].sum() + rc[9:14, 4:12].sum())
    return on, off, loc


# flat/tilted: logistic weights fitted on a few thousand frames whose class is known from the recording
_TILT_W = (12.748, 4.582, 4.263, 9.977)
_TILT_B = -6.484
TILT_THR = -0.5  # errors of both kinds are about equally frequent here


def _analyse(crop: np.ndarray) -> dict:
    out: dict = {"route": "none", "bearing": None, "far": None, "conf": 0.0, "path": None, "cands": []}
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    white = crop.min(axis=2).astype(np.float32)
    arrow, arrow_q = _arrow(white)
    bars = _bars(crop)
    out["arrow"], out["arrow_q"], out["bars"] = arrow, arrow_q, bars
    present = arrow_q >= 0.52 or (arrow_q >= 0.4 and bars >= 2) or bars == 3
    on, off, loc = _damage(gray)
    grid = on - off
    corrupt = grid >= 10 and on >= 1.6 * off + 5
    out["corrupt"], out["grid"], out["loc"] = corrupt, grid, loc
    if not present:
        out["minimap"] = "none"
        return out
    tf = _tilt_features(gray)
    logit = _TILT_B + sum(w * x for w, x in zip(_TILT_W, tf))
    out["tilt_logit"] = logit

    sy, sp = _score_maps(crop)
    cands = []
    for name, score in (("yellow", sy), ("purple", sp)):
        paths, on_ring = _trace(score)
        for path in paths:
            ang = _node_angles(path)
            f = _path_features(path, ang, on_ring)
            if f["r1"] < MIN_R1:
                continue
            # a line straight through the arrow, or one that passes beside it
            line = (f["anti"] >= MAX_ANTI and f["antin"] >= 8) or not (0.0 <= f["mir"] <= MAX_MIRROR)
            ok = (f["wid"] <= MAX_WID and not line and f["sup"] >= (MIN_SUP_CORRUPT if corrupt else MIN_SUP)
                  and f["mnear"] >= (MIN_NEAR_Y if name == "yellow" else MIN_NEAR_P))
            if f["r0"] > R0:  # begins beside the arrow: only a flawless line on a clean picture
                ok = ok and not corrupt and f["sup"] >= MIN_SUP_OFFSET
            cands.append({"colour": name, "f": f, "ok": ok, "line": line, "path": path, "ang": ang,
                          "b": _bin_to_deg(_angle_at(path, ang, I_NEAR))})
    # best explanation first; a rejected path takes its variants with it (same direction, and for a line
    # through the arrow its other arm), so that no leftover of a refused path is read as a route
    cands.sort(key=lambda c: -c["f"]["q"])
    out["cands"] = cands
    best = None
    refused: list[tuple[str, float, bool]] = []
    for c in cands:
        shadow = False
        for (col, b0, line) in refused:
            if col == c["colour"]:
                d = abs((c["b"] - b0 + 180.0) % 360.0 - 180.0)
                if d < 30.0 or (line and d > 150.0):
                    shadow = True
                    break
        if c["ok"] and not shadow:
            best = c
            break
        if not c["ok"]:
            refused.append((c["colour"], c["b"], c["line"]))
    if best is not None:
        f, path, ang = best["f"], best["path"], best["ang"]
        near_min = MIN_NEAR_Y if best["colour"] == "yellow" else MIN_NEAR_P
        conf = ((0.5 + 0.5 * min(1.0, max(0.0, (f["sup"] - 0.85) / 0.15)))  # holes in the line
                * (0.6 + 0.4 * min(1.0, (f["mnear"] - near_min) / 0.08))  # pale next to the arrow
                * (0.5 + 0.5 * min(1.0, (f["r1"] - 6) / 24.0))  # short
                * (0.7 + 0.3 * f["ns"]))  # mixed up with something wide
        if f["r0"] > R0:
            conf *= 0.8
        if corrupt:
            conf *= 0.45 if loc >= 15 else 0.6
        out.update(route=best["colour"], conf=conf, path=path, feat=f, bearing=best["b"],
                   far=_bin_to_deg(_angle_at(path, ang, I_FAR)))
    else:
        # no route: sure on a clean picture with nothing route-like at the arrow, less so otherwise
        conf = 0.9
        if corrupt:
            conf = 0.3 if loc >= 10 else 0.5
        if refused:
            conf = min(conf, 0.3 if corrupt else 0.5)
        out["conf"] = conf
    # a route was only ever seen on the tilted (vehicle) map
    out["minimap"] = "tilted" if (logit > TILT_THR or out["route"] != "none") else "flat"
    return out


def read(crop: np.ndarray) -> Reading:
    a = _analyse(crop)
    return Reading(minimap=a["minimap"], route=a["route"], bearing=a["bearing"], far_bearing=a["far"],
                   arrow=a["arrow"] if (a["minimap"] != "none" and a["arrow_q"] >= 0.5) else None,
                   corrupt=bool(a["corrupt"]), confidence=float(a["conf"]))
