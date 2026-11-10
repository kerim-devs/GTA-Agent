import sys
from pathlib import Path
import numpy as np, cv2
sys.path.insert(0, str(Path(__file__).resolve().parent))
from devlabels import dev
crops, meta, labs = dev()
K3 = np.ones((3, 3), np.uint8); K5 = np.ones((5, 5), np.uint8)
def feats(c):
    g = cv2.cvtColor(c, cv2.COLOR_RGB2GRAY)
    m = g[28:142, 34:214]
    th3 = cv2.morphologyEx(m, cv2.MORPH_TOPHAT, K3).astype(np.float32)   # bright structures thinner than 3 px
    th5 = cv2.morphologyEx(m, cv2.MORPH_TOPHAT, K5).astype(np.float32)
    bh5 = cv2.morphologyEx(m, cv2.MORPH_BLACKHAT, K5).astype(np.float32)
    bands = [(2, 30), (30, 58), (58, 86), (86, 112)]
    f = []
    for a, b in bands:
        f += [th3[a:b].mean(), th5[a:b].mean(), bh5[a:b].mean(), float(m[a:b].std())]
    return np.array(f)
rows = []
for l in labs:
    f = feats(np.asarray(crops[l["k"]]))
    rows.append((l["minimap"], l["corrupt"], l["id"], l["k"], f))
np.set_printoptions(linewidth=220, suppress=True, precision=1)
for cls in ("flat", "tilted", "none"):
    F = np.array([r[4] for r in rows if r[0] == cls])
    print(cls, len(F)); print(" median", np.median(F, 0)); print(" p10   ", np.percentile(F, 10, 0)); print(" p90   ", np.percentile(F, 90, 0))
print()
for r in sorted(rows, key=lambda r: (r[0], r[4][1] / (r[4][13] + 1))):
    f = r[4]
    print(r[0], "C" if r[1] else "-", r[2], r[3], "th5 bands %5.1f %5.1f %5.1f %5.1f | th3 %5.1f %5.1f %5.1f %5.1f | ratio top/bot th5 %.2f th3 %.2f" % (f[1], f[5], f[9], f[13], f[0], f[4], f[8], f[12], f[1] / (f[13] + 1), f[0] / (f[12] + 1)))
