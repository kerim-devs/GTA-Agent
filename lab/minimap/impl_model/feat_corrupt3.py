import sys
from pathlib import Path
import numpy as np, cv2
sys.path.insert(0, str(Path(__file__).resolve().parent))
from devlabels import dev
T1, T2 = 18, 6
def grid_steps(g):
    """Clean-step maps sampled only on the block grid (on) and half a block away (off).
    Returns von, voff (170 x 32: step between x-1 and x for x = 2+8j / 6+8j) and hon, hoff (21 x 260: y = 6+8i / 2+8i)."""
    g = g.astype(np.int16)
    out = []
    for o in (0, 4):
        a, b, c, d = g[:, o:256:8], g[:, o + 1:256:8], g[:, o + 2:256:8], g[:, o + 3:256:8]
        out.append((np.abs(c - b) >= T1) & (np.abs(b - a) <= T2) & (np.abs(d - c) <= T2))
    for o in (4, 0):
        a, b, c, d = g[o:168:8], g[o + 1:168:8], g[o + 2:168:8], g[o + 3:168:8]
        out.append((np.abs(c - b) >= T1) & (np.abs(b - a) <= T2) & (np.abs(d - c) <= T2))
    return out
def feats(c):
    g = cv2.cvtColor(c, cv2.COLOR_RGB2GRAY)
    von, voff, hon, hoff = grid_steps(g)
    von[:, 4] = False          # x = 34: left edge of the map
    voff[:, 26] = False        # x = 214: right edge of the map
    # global: rows < 140 only
    glob = int(von[:140].sum()) + int(hon[:17].sum()) - int(voff[:140].sum()) - int(hoff[:17].sum())
    # local window around the arrow: x 90..154 (on cols j=11..19 -> x=90..154), y 78..142
    loc = int(von[78:142, 11:20].sum()) + int(hon[9:17, 90:154].sum()) - int(voff[78:142, 11:19].sum()) - int(hoff[10:18, 90:154].sum())
    return glob, loc
if __name__ == "__main__":
    crops, meta, labs = dev()
    for l in sorted(labs, key=lambda l: (l["route"], l["corrupt"])):
        if l["route"] == "none": continue
        print(l["route"], "C" if l["corrupt"] else "-", l["id"], l["k"], feats(np.asarray(crops[l["k"]])), l.get("note", "")[:60])
    print("FP list")
    for k in (690, 2404, 2466, 540, 600, 989, 1052, 1521, 1712, 2057, 709, 1507, 1536, 1645, 722):
        print(k, feats(np.asarray(crops[k])))
    locs = sorted(feats(np.asarray(crops[l["k"]]))[1] for l in labs if not l["corrupt"])
    print("clean tiles local excess percentiles:", np.percentile(locs, [50, 75, 90, 95, 100]))
    locs = sorted(feats(np.asarray(crops[l["k"]]))[1] for l in labs if l["corrupt"])
    print("corrupt tiles local excess percentiles:", np.percentile(locs, [0, 10, 25, 50, 75]))
