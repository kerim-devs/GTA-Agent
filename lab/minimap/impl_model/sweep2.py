import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from devlabels import dev
from harvest import X0, X1, Y0, Y1
from train import idx, smooth, NB
H = dict(np.load("impl_model/hist.npz"))
crops, meta, labs = dev()
watch = [1127, 708, 628, 705, 691, 693, 1434, 2417, 2397, 2687, 1508, 599, 655, 1310, 474, 849, 955, 1060, 1025, 1780]
IX = {k: idx(np.asarray(crops[k]))[Y0:Y1, X0:X1].ravel() for k in watch}
def hdr(P, q):
    o = np.argsort(-P); c = np.cumsum(P[o]); n = np.searchsorted(c, q * c[-1]) + 1
    m = np.zeros(NB, bool); m[o[:n]] = True
    return m
for col in ("yellow",):
    core = H[col + "_core"]; al = H[col + "_all"]
    for s in (0.7, 1.0, 1.5):
        Pc = smooth(core, s)
        for q in (0.5, 0.6, 0.7, 0.8, 0.9):
            m = hdr(Pc, q)
            print(f"{col} sigma={s} q={q}: bins {int(m.sum())} raw core recall {core[m].sum()/core.sum():.2f} all {al[m].sum()/al.sum():.2f} | " + " ".join(f"{k}:{int(m[IX[k]].sum())}" for k in watch))
