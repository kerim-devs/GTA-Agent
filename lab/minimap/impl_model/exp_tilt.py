"""Experiment: does a contrast stretch of the map before the tilt features help on washed-out frames?"""
import json, sys, math
from pathlib import Path
import numpy as np, cv2
sys.path.insert(0, str(Path(__file__).resolve().parent))
from devlabels import dev, ROOT
import tools
from train_tilt import logreg
M = tools.load_impl(str(ROOT / "impl_model" / "minimap.py"))

def stretch(m):
    h = cv2.calcHist([m], [0], None, [256], [0, 256]).ravel().cumsum()
    lo = int(np.searchsorted(h, 0.05 * h[-1])); hi = int(np.searchsorted(h, 0.95 * h[-1]))
    if hi - lo < 8:
        return m
    return cv2.convertScaleAbs(m, alpha=255.0 / (hi - lo), beta=-lo * 255.0 / (hi - lo))

def feats(grey, mode):
    m = np.ascontiguousarray(grey[M.MY0:M.MY1, M.MX0:M.MX1])
    if mode == "stretch":
        m = stretch(m)
    prev, lev = m, []
    for s in (3, 5, 9, 15):
        o = cv2.morphologyEx(m, cv2.MORPH_OPEN, M._KS[s])
        lev.append(cv2.subtract(prev, o)); prev = o
    F = np.array([[cv2.mean(l[a:b])[0] for l in lev] for a, b in M._BANDS])
    tot = F.sum(1) + 2.0
    g = m.astype(np.int16)
    dx = np.abs(g[:, 2:] - g[:, :-2]).mean(1); dy = np.abs(g[2:, :] - g[:-2, :]).mean(1)
    e = []
    for a, b in ((2, 40), (40, 76), (76, 112)):
        ex, ey = dx[a:b].mean() + 1, dy[a:b].mean() + 1
        e += [math.log(ey / ex), math.log(ex + ey)]
    e.append(float((dy * np.arange(len(dy))).sum() / (dy.sum() + 1) / 112))
    e.append(float((dx * np.arange(len(dx))).sum() / (dx.sum() + 1) / 112))
    return np.concatenate([(F[:, 0] + F[:, 1]) / tot, F[:, 3] / tot, np.log(tot), e])

crops, meta, labs = dev()
golden = json.loads((ROOT / "data" / "golden.json").read_text())
held = {g["k"] + d for g in golden if g["split"] == "held" for d in (-1, 0, 1)}
anchors = sorted((l["k"], l["minimap"]) for l in labs if l["minimap"] != "none")
lab = dict(anchors); pseudo = {}
for (k1, c1), (k2, c2) in zip(anchors, anchors[1:]):
    if c1 == c2 and k2 - k1 <= 60 and meta[k1]["rec"] == meta[k2]["rec"]:
        for k in range(k1 + 1, k2): pseudo[k] = c1
for k in list(pseudo):
    if k in held or k in lab: del pseudo[k]
ks = sorted(lab) + sorted(pseudo)
y = np.array([(lab.get(k) or pseudo[k]) == "tilted" for k in ks], float)
isdev = np.array([k in lab for k in ks]); karr = np.array(ks)
greys = [cv2.cvtColor(np.asarray(crops[k]), cv2.COLOR_RGB2GRAY) for k in ks]
for mode in ("plain", "stretch"):
    X = np.array([feats(g, mode) for g in greys])
    mu, sd = X.mean(0), X.std(0) + 1e-6; Xn = (X - mu) / sd
    for l2 in (10,):
        wrong_dev = []; wrong_all = 0
        # leave-neighbourhood-out over everything, in blocks of 40 crops
        for b0 in range(0, 2768, 40):
            te = (karr >= b0) & (karr < b0 + 40)
            if not te.any(): continue
            tr = (karr < b0 - 10) | (karr >= b0 + 50)
            w = logreg(Xn[tr], y[tr], l2)
            p = 1 / (1 + np.exp(-np.clip(np.concatenate([Xn[te], np.ones((te.sum(), 1))], 1) @ w, -30, 30)))
            bad = (p > 0.5) != y[te]
            wrong_all += int(bad.sum())
            for k, pp, bb, d in zip(karr[te], p, bad, isdev[te]):
                if bb and d: wrong_dev.append((int(k), lab[int(k)], round(float(pp), 2)))
        print(mode, "l2", l2, "block-out errors all", wrong_all, "/", len(ks), "dev", len(wrong_dev), "/", int(isdev.sum()), wrong_dev)
