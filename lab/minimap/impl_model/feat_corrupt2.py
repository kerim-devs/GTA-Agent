import sys
from pathlib import Path
import numpy as np, cv2
sys.path.insert(0, str(Path(__file__).resolve().parent))
from devlabels import dev
XS = np.arange(260); YS = np.arange(170)
VON = (XS % 8 == 2) & (XS != 34); VOFF = (XS % 8 == 6) & (XS != 214)
HON = (YS % 8 == 6) & (YS < 140); HOFF = (YS % 8 == 2) & (YS < 140)
def stepmaps(c, T1, T2, mode):
    if mode == "max": g = c.max(axis=2).astype(np.int16)[..., None]
    elif mode == "grey": g = cv2.cvtColor(c, cv2.COLOR_RGB2GRAY).astype(np.int16)[..., None]
    else: g = c.astype(np.int16)
    dx = np.abs(np.diff(g, axis=1)).max(axis=2); dy = np.abs(np.diff(g, axis=0)).max(axis=2)
    sv = np.zeros(c.shape[:2], bool); sh = np.zeros(c.shape[:2], bool)
    sv[:, 2:-1] = (dx[:, 1:-1] >= T1) & (dx[:, :-2] <= T2) & (dx[:, 2:] <= T2)
    sh[2:-1, :] = (dy[1:-1, :] >= T1) & (dy[:-2, :] <= T2) & (dy[2:, :] <= T2)
    return sv, sh
def feats(c, T1=18, T2=6, mode="max", run=6):
    sv, sh = stepmaps(c, T1, T2, mode)
    svr = cv2.erode(sv.view(np.uint8), np.ones((run, 1), np.uint8)); shr = cv2.erode(sh.view(np.uint8), np.ones((1, run), np.uint8))
    on = sv[:140][:, VON].sum() + sh[HON].sum(); off = sv[:140][:, VOFF].sum() + sh[HOFF].sum()
    ron = svr[:140][:, VON].sum() + shr[HON].sum(); roff = svr[:140][:, VOFF].sum() + shr[HOFF].sum()
    return on, off, ron, roff
def auc(pos, neg):
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    return float(((pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()) / (len(pos) * len(neg)))
if __name__ == "__main__":
    crops, meta, labs = dev()
    y = np.array([bool(l["corrupt"]) for l in labs])
    for mode in ("max", "grey", "rgb"):
        for T1, T2 in ((18, 6), (24, 6), (30, 8), (40, 10)):
            for run in (4, 6, 8):
                F = np.array([feats(np.asarray(crops[l["k"]]), T1, T2, mode, run) for l in labs])
                ex = F[:, 0] - F[:, 1]; rex = F[:, 2] - F[:, 3]
                print(f"{mode} T1={T1} T2={T2} run={run}: AUC excess {auc(ex[y], ex[~y]):.3f}  run-excess {auc(rex[y], rex[~y]):.3f}  run-on {auc(F[y, 2], F[~y, 2]):.3f}")
