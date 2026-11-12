"""Flat vs tilted: logistic regression on a granulometry of the map (how much bright structure of which width
sits in which horizontal band; a tilted map has thin roads at the top and wide ones at the bottom).
Training set: dev labels, plus unlabelled crops between two dev tiles of the same class less than 60 crops apart
(the class changes only when the player enters or leaves a vehicle); held-out tiles +-1 are excluded."""
import json, sys
from pathlib import Path
import numpy as np, cv2
sys.path.insert(0, str(Path(__file__).resolve().parent))
from devlabels import dev, ROOT
import tools
MOD = tools.load_impl(str(ROOT / "impl_model" / "minimap.py"))
def feats(c):
    return MOD._tilt_features(cv2.cvtColor(c, cv2.COLOR_RGB2GRAY))
def logreg(X, y, l2=1.0, iters=60):
    Xb = np.concatenate([X, np.ones((len(X), 1))], 1)
    w = np.zeros(Xb.shape[1])
    reg = np.eye(Xb.shape[1]) * l2; reg[-1, -1] = 0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-np.clip(Xb @ w, -30, 30)))
        g = Xb.T @ (p - y) + reg @ w
        Hm = (Xb.T * (p * (1 - p) + 1e-6)) @ Xb + reg
        w -= np.linalg.solve(Hm, g)
    return w
if __name__ == "__main__":
    crops, meta, labs = dev()
    golden = json.loads((ROOT / "data" / "golden.json").read_text())
    held = {g["k"] + d for g in golden if g["split"] == "held" for d in (-1, 0, 1)}
    anchors = sorted((l["k"], l["minimap"]) for l in labs if l["minimap"] != "none")
    lab = {k: c for k, c in anchors}
    pseudo = {}
    for (k1, c1), (k2, c2) in zip(anchors, anchors[1:]):
        if c1 == c2 and k2 - k1 <= 60 and meta[k1]["rec"] == meta[k2]["rec"]:
            for k in range(k1 + 1, k2):
                pseudo[k] = c1
    for k in list(pseudo):
        if k in held or k in lab: del pseudo[k]
    print("dev", len(lab), "pseudo", len(pseudo), {c: sum(v == c for v in pseudo.values()) for c in ("flat", "tilted")})
    ks = sorted(lab) + sorted(pseudo)
    X = np.array([feats(np.asarray(crops[k])) for k in ks])
    y = np.array([(lab.get(k) or pseudo[k]) == "tilted" for k in ks], float)
    mu, sd = X.mean(0), X.std(0) + 1e-6; Xn = (X - mu) / sd
    isdev = np.array([k in lab for k in ks]); karr = np.array(ks)
    for l2 in (1, 10, 30):
        # leave-neighbourhood-out for the dev tiles
        wrong = []
        for i in np.nonzero(isdev)[0]:
            tr = np.abs(karr - karr[i]) > 10
            w = logreg(Xn[tr], y[tr], l2)
            p = 1 / (1 + np.exp(-(np.append(Xn[i], 1) @ w)))
            if (p > 0.5) != y[i]: wrong.append((int(karr[i]), lab[int(karr[i])], round(float(p), 2)))
        w = logreg(Xn, y, l2)
        p = 1 / (1 + np.exp(-(np.concatenate([Xn, np.ones((len(Xn), 1))], 1) @ w)))
        print(f"l2={l2}: leave-neighbourhood-out dev errors {len(wrong)}/{isdev.sum()}; training error all {((p > 0.5) != y).mean():.3f} dev {((p > 0.5) != y)[isdev].mean():.3f}")
        if l2 == 10: print("  ", wrong)
    w = logreg(Xn, y, 10)
    # fold the standardisation into the weights: z = w . ((x - mu) / sd) + b
    wx = w[:-1] / sd; b = w[-1] - (w[:-1] * mu / sd).sum()
    np.save("impl_model/tilt_w.npy", np.append(wx, b))
    print("weights", np.round(np.append(wx, b), 3).tolist())
