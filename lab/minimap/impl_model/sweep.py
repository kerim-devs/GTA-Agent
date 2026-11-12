import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
from devlabels import dev
from harvest import X0, X1, Y0, Y1
from train import idx, posteriors, NB
H = dict(np.load("impl_model/hist.npz"))
crops, meta, labs = dev()
watch = [1127, 708, 628, 705, 691, 693, 1434, 2417, 2397, 2687, 1508, 599, 655, 1310, 849, 955, 1060, 1025, 1780]
IX = {k: idx(np.asarray(crops[k]))[Y0:Y1, X0:X1].ravel() for k in watch}
neg_ix = np.concatenate([idx(np.asarray(crops[l["k"]]))[Y0:Y1, X0:X1].ravel() for l in labs if l["route"] == "none"])
for col in ("yellow", "purple"):
    core = H[col + "_core"]; al = H[col + "_all"]
    for w_out in (0.0, 0.1, 0.3):
        for pi in (0.02,):
            post, N = posteriors(H, pi=pi, w_out=w_out)
            pc, pa, Pc, Pa = post[col]
            for t in (0.2, 0.5, 0.8, 0.95):
                s = (pc > t) & (Pc > 2e-6)
                w = (pa > t) & (Pa > 5e-7)
                print(f"{col} w_out={w_out} t={t}: core recall {core[s].sum()/core.sum():.2f} all recall {al[w].sum()/al.sum():.2f} bins s={int(s.sum())} w={int(w.sum())} | neg-map strong px total {int(s[neg_ix].sum())} weak {int(w[neg_ix].sum())} | " +
                      " ".join(f"{k}:{int(s[IX[k]].sum())}" for k in watch))
