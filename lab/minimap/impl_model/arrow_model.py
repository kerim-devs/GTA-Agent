"""Arrow heading by matching a rendered dart (white inside, dark outline) at 24 rotations.
The dart's dimensions are fitted on the dev arrow labels (grid search)."""
import sys, itertools
from pathlib import Path
import numpy as np, cv2
sys.path.insert(0, str(Path(__file__).resolve().parent))
HW = 9            # patch half width: 19 x 19 around the arrow
SS = 8            # supersampling
def render(theta_deg, tip=5.7, bx=3.0, by=2.8, notch=1.3, ow=1.3, cx=0.0, cy=0.0):
    """(template, weight) 19x19: +1 inside the dart, -1 on its outline, weight 0 elsewhere."""
    n = (2 * HW + 1) * SS
    pts = np.array([[0, -tip], [bx, by], [0, notch], [-bx, by]], np.float64)
    t = np.radians(theta_deg)
    R = np.array([[np.cos(t), -np.sin(t)], [np.sin(t), np.cos(t)]])
    p = pts @ R.T + [cx, cy]
    q = np.round((p + HW + 0.5) * SS).astype(np.int32)
    inner = np.zeros((n, n), np.uint8)
    cv2.fillPoly(inner, [q], 1)
    k = int(round(ow * SS)) * 2 + 1
    outer = cv2.dilate(inner, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    ring = outer - inner
    down = lambda m: m.reshape(2 * HW + 1, SS, 2 * HW + 1, SS).mean((1, 3))
    a, b = down(inner.astype(np.float64)), down(ring.astype(np.float64))
    return a - b, a + b
def bank(step=15, **kw):
    T, W = [], []
    for ang in range(0, 360, step):
        t, w = render(ang, **kw)
        w = w.ravel(); t = t.ravel()
        mu = (w * t).sum() / w.sum()
        tt = w * (t - mu)
        T.append(tt / np.sqrt((w * (t - mu) ** 2).sum()))
        W.append(w)
    return np.array(T, np.float32), np.array(W, np.float32)
def match(p, T, W, step=15):
    p = p.astype(np.float32).ravel()
    num = T @ p
    sw = W.sum(1)
    var = W @ (p * p) - (W @ p) ** 2 / sw
    s = num / np.sqrt(np.maximum(var, 1e-3))
    i = int(s.argmax())
    a, b, c = s[i - 1], s[i], s[(i + 1) % len(s)]
    den = a - 2 * b + c
    off = 0.5 * (a - c) / den if den < 0 else 0.0
    return ((i + off) * step + 180) % 360 - 180, float(b)
def patch(c, cx=123, cy=117):
    return cv2.cvtColor(c, cv2.COLOR_RGB2GRAY)[cy - HW:cy + HW + 1, cx - HW:cx + HW + 1]
def clock_to_deg(c):
    d = (float(c) % 12) * 30
    return d - 360 if d > 180 else d
if __name__ == "__main__":
    from devlabels import dev
    crops, meta, labs = dev()
    L = [l for l in labs if l["arrow_clock"] is not None]
    P = [patch(np.asarray(crops[l["k"]])) for l in L]
    want = np.array([clock_to_deg(l["arrow_clock"]) for l in L])
    best = None
    for tip, bx, by, notch, ow, cy in itertools.product((5.2, 5.7, 6.2), (2.6, 3.0, 3.4), (2.4, 2.8, 3.2), (0.8, 1.3, 1.8), (1.0, 1.3), (-0.5, 0.0)):
        T, W = bank(tip=tip, bx=bx, by=by, notch=notch, ow=ow, cy=cy)
        res = [match(p, T, W) for p in P]
        e = np.abs((np.array([r[0] for r in res]) - want + 180) % 360 - 180)
        key = ((e <= 45).mean(), -np.mean(np.minimum(e, 90)))
        if best is None or key > best[0]:
            best = (key, dict(tip=tip, bx=bx, by=by, notch=notch, ow=ow, cy=cy), e, res)
    key, par, e, res = best
    print("best", par, "within45 %.3f median %.1f mean(min(e,90)) %.1f" % ((e <= 45).mean(), np.median(e), -key[1]))
    for i in np.argsort(-e)[:12]:
        print("  err %.0f score %.2f %s k=%d want %.0f got %.0f %s" % (e[i], res[i][1], L[i]["id"], L[i]["k"], want[i], res[i][0], "C" if L[i]["corrupt"] else ""))
    sc = np.array([r[1] for r in res])
    print("score pcts 1,5,25,50:", np.round(np.percentile(sc, [1, 5, 25, 50]), 2))
    T, W = bank(**par)
    print("scores on minimap none:", np.round([match(patch(np.asarray(crops[l["k"]])), T, W)[1] for l in labs if l["minimap"] == "none"], 2))
