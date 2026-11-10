"""Learn the arrow template: mean of the normalised grey patch (21 x 21 around the arrow) over dev tiles labelled
arrow 12 o'clock, not corrupt.  Evaluate rotated-template matching on all dev arrow labels."""
import sys
from pathlib import Path
import numpy as np, cv2
sys.path.insert(0, str(Path(__file__).resolve().parent))
from devlabels import dev
HW = 10
CX, CY = 123, 117
yy, xx = np.mgrid[-HW:HW + 1, -HW:HW + 1]
DISC = (xx ** 2 + yy ** 2) <= 9.5 ** 2
def patch(c, cx=CX, cy=CY):
    g = cv2.cvtColor(c, cv2.COLOR_RGB2GRAY).astype(np.float32)
    return g[cy - HW:cy + HW + 1, cx - HW:cx + HW + 1]
def norm(p):
    v = p[DISC]
    v = v - v.mean()
    n = np.linalg.norm(v)
    return v / n if n > 1e-3 else v
def rotations(tmpl, step=10):
    out = []
    for a in range(0, 360, step):
        M = cv2.getRotationMatrix2D((HW, HW), -a, 1.0)     # positive a = clockwise on screen
        r = cv2.warpAffine(tmpl, M, (2 * HW + 1, 2 * HW + 1), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        out.append(norm(r))
    return np.array(out)
def match(p, R, step=10):
    s = R @ norm(p)
    i = int(s.argmax())
    a, b, c = s[i - 1], s[i], s[(i + 1) % len(s)]
    off = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0.0
    ang = ((i + off) * step + 180) % 360 - 180
    return ang, float(b), s
def clock_to_deg(c):
    d = (float(c) % 12) * 30
    return d - 360 if d > 180 else d
if __name__ == "__main__":
    crops, meta, labs = dev()
    up = [l for l in labs if l["arrow_clock"] == 12 and not l["corrupt"] and l["minimap"] != "none"]
    P = np.array([patch(np.asarray(crops[l["k"]])) for l in up])
    # normalise each patch (zero mean / unit std) before averaging
    Pn = (P - P.mean((1, 2), keepdims=True)) / (P.std((1, 2), keepdims=True) + 1e-3)
    tmpl = Pn.mean(0).astype(np.float32)
    np.save("impl_model/arrow_tmpl.npy", tmpl)
    print("template from", len(up), "tiles")
    np.set_printoptions(linewidth=250, precision=1, suppress=True)
    print(np.round(tmpl * 10).astype(int))
    R = rotations(tmpl)
    errs = []
    for l in labs:
        if l["arrow_clock"] is None: continue
        ang, sc, s = match(patch(np.asarray(crops[l["k"]])), R)
        want = clock_to_deg(l["arrow_clock"])
        e = abs((ang - want + 180) % 360 - 180)
        errs.append((e, sc, l["id"], l["k"], want, ang, l["corrupt"]))
    e = np.array([x[0] for x in errs])
    print("n", len(e), "median", np.median(e), "within45", (e <= 45).mean(), "within20", (e <= 20).mean())
    for x in sorted(errs, reverse=True)[:14]:
        print("  err %.0f score %.2f %s k=%d want %.0f got %.0f %s" % (x[0], x[1], x[2], x[3], x[4], x[5], "C" if x[6] else ""))
    sc = np.array([x[1] for x in errs])
    print("score percentiles 1,5,25,50:", np.percentile(sc, [1, 5, 25, 50]))
    none = [match(patch(np.asarray(crops[l["k"]])), R)[1] for l in labs if l["minimap"] == "none"]
    print("scores on minimap none tiles:", np.round(none, 2))
