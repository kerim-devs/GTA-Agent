import sys
from pathlib import Path
import numpy as np, cv2
sys.path.insert(0, str(Path(__file__).resolve().parent))
from devlabels import dev
def steps(g, axis, T1=18, T2=6):
    """bool map of 'clean step' pixels: a jump between neighbours with flat pixels on both sides (along `axis`)."""
    g = g.astype(np.int16)
    if axis == 0: g = g.T
    d = np.abs(np.diff(g, axis=1))               # d[:, i] = |g[:, i+1] - g[:, i]|
    st = np.zeros(g.shape, bool)
    st[:, 2:-1] = (d[:, 1:-1] >= T1) & (d[:, :-2] <= T2) & (d[:, 2:] <= T2)   # st[:, x]: step between x-1 and x
    return st.T if axis == 0 else st
def feats(c):
    g = c.max(axis=2)  # brightest channel
    sv = steps(g, 1); sh = steps(g, 0)
    xs = np.arange(260); ys = np.arange(170)
    von = sv[:140][:, (xs % 8 == 2) & (xs != 34)].sum(); voff = sv[:140][:, (xs % 8 == 6) & (xs != 214)].sum()
    hon = sh[(ys % 8 == 6) & (ys < 140)].sum(); hoff = sh[(ys % 8 == 2) & (ys < 140)].sum()
    return von, voff, hon, hoff
if __name__ == "__main__":
    crops, meta, labs = dev()
    rows = []
    for l in labs:
        f = feats(np.asarray(crops[l["k"]]))
        rows.append((bool(l["corrupt"]), l["id"], l["k"], f, l.get("note", "")[:70]))
    for r in sorted(rows, key=lambda r: (r[0], (r[3][0] + r[3][2]) - (r[3][1] + r[3][3]))):
        von, voff, hon, hoff = r[3]
        print("C" if r[0] else "-", r[1], "k=%4d" % r[2], f"v on/off {von:4d}/{voff:4d}  h on/off {hon:4d}/{hoff:4d}  excess {von + hon - voff - hoff:5d}", "|", r[4])
