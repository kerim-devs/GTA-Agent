import sys
from pathlib import Path
import numpy as np, cv2
sys.path.insert(0, str(Path(__file__).resolve().parent))
from devlabels import dev
from harvest import X0, X1, Y0, Y1
from train import idx, route_pixels
lut = np.load("impl_model/lut.npy")
crops, meta, labs = dev()
rows = []
for l in labs:
    c = np.asarray(crops[l["k"]])
    cls = lut[idx(c)]
    m = cls[Y0:Y1, X0:X1]
    cnt = np.bincount(m.ravel(), minlength=5)
    rec = ""
    if l["route"] != "none":
        keep, core, L = route_pixels(c, l["route"])
        code = 1 if l["route"] == "yellow" else 3
        rec = "recall core->strong %.2f  all->weak+ %.2f" % ((cls[core] == code + 1).mean() if core.any() else -1, (cls[keep] >= code).mean() if keep.any() else -1)
    rows.append((l["route"], l["id"], l["k"], cnt[1:], rec, l.get("note", "")[:60]))
for r in sorted(rows, key=lambda r: (r[0], -int(r[3][1] + r[3][3]))):
    print("%-6s %s k=%-4d yw=%-5d ys=%-5d pw=%-5d ps=%-5d %s | %s" % (r[0], r[1], r[2], r[3][0], r[3][1], r[3][2], r[3][3], r[4], r[5]))
