"""Fit the colour model: histograms over RGB quantised to 6 bits per channel (262144 bins).

P_core / P_all : route pixels (eroded core / every pixel of the route component) of dev tiles labelled with a route
N_in           : every pixel of dev tiles labelled without a route + pixels of dev route tiles away from the route
N_out          : pixels outside the map rectangle (never a route there) of all crops except the held-out ones (+-1)
N_unl          : map pixels of unlabelled crops outside the two drives that show a route (k 800..1110 yellow,
                 1375..1440 purple; every route reading outside them was checked by eye to be false), held-out +-1 excluded
N_mined_p      : the pixels of N_unl that a first model called purple (hard negatives: damage, blue-tinted maps)
posterior      = pi * P / (pi * P + (1 - pi) * N),  N = weighted mix of the normalised negative histograms
LUT classes    : 0 other, 1 yellow weak, 2 yellow strong, 3 purple weak, 4 purple strong
No held-out label is read."""
import json, sys
from pathlib import Path
import numpy as np, cv2
sys.path.insert(0, str(Path(__file__).resolve().parent))
from devlabels import dev, ROOT
from harvest import loose, X0, X1, Y0, Y1, AX, AY

NB = 64 ** 3
SKIP_POS = {849, 955, 1060, 1025}   # route tiles whose loose mask is polluted (grass, damage); not used as positives

def idx(c):
    c = c.astype(np.int32) >> 2
    return (c[..., 0] << 12) | (c[..., 1] << 6) | c[..., 2]

def smooth(h, sigma):
    h = h.reshape(64, 64, 64).astype(np.float32)
    if sigma > 0:
        k = int(6 * sigma + 1) | 1
        # blur over (G,B) planes, then along R
        for i in range(64):
            h[i] = cv2.GaussianBlur(h[i], (k, k), sigma, borderType=cv2.BORDER_REPLICATE)
        h2 = h.reshape(64, -1)
        h2 = cv2.GaussianBlur(h2, (1, k), sigma, borderType=cv2.BORDER_REPLICATE)
        h = h2
    return h.reshape(-1).astype(np.float64)

def route_pixels(c, colour, reach=16):
    L = np.zeros(c.shape[:2], np.uint8)
    L[Y0:Y1, X0:X1] = loose(c, colour)[Y0:Y1, X0:X1]
    D = cv2.dilate(L, np.ones((5, 5), np.uint8))
    n, lab = cv2.connectedComponents(D, connectivity=8)
    yy, xx = np.mgrid[:170, :260]
    near = (xx - AX) ** 2 + (yy - AY) ** 2 <= reach ** 2
    ids = np.unique(lab[near & (L > 0)])
    ids = ids[ids > 0]
    keep = np.isin(lab, ids) & (L > 0)
    core = cv2.erode(keep.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    return keep, core, L.astype(bool)

def harvest():
    crops, meta, labs = dev()
    golden = json.loads((ROOT / "data" / "golden.json").read_text())
    held = {g["k"] + d for g in golden if g["split"] == "held" for d in (-1, 0, 1)}
    H = {"N_in": np.zeros(NB), "N_out": np.zeros(NB)}
    for col in ("yellow", "purple"):
        H[col + "_core"] = np.zeros(NB); H[col + "_all"] = np.zeros(NB)
    for l in labs:
        c = np.asarray(crops[l["k"]])
        ix = idx(c)
        if l["route"] == "none":
            H["N_in"] += np.bincount(ix.ravel(), minlength=NB)
            continue
        col = l["route"]
        keep, core, L = route_pixels(c, col)
        far = cv2.dilate((loose(c, col)).astype(np.uint8), np.ones((9, 9), np.uint8)) == 0
        H["N_in"] += np.bincount(ix[far], minlength=NB)
        if l["k"] in SKIP_POS:
            continue
        H[col + "_core"] += np.bincount(ix[core], minlength=NB)
        H[col + "_all"] += np.bincount(ix[keep], minlength=NB)
    outside = np.ones((170, 260), bool)
    outside[Y0 - 4:Y1 + 4, X0 - 4:X1 + 4] = False
    H["N_unl"] = np.zeros(NB); H["N_mined_p"] = np.zeros(NB)
    first = np.load(Path(__file__).resolve().parent / "lut_first.npy") if (Path(__file__).resolve().parent / "lut_first.npy").exists() else None
    for k in range(len(meta)):
        if k in held:
            continue
        ix = idx(np.asarray(crops[k]))
        H["N_out"] += np.bincount(ix[outside], minlength=NB)
        if 800 <= k <= 1110 or 1375 <= k <= 1440:
            continue
        inside = ix[Y0:Y1, X0:X1].ravel()
        H["N_unl"] += np.bincount(inside, minlength=NB)
        if first is not None:
            H["N_mined_p"] += np.bincount(inside[first[inside] >= 3], minlength=NB)
    return H

MIX = {"yellow": {"N_in": 0.5, "N_unl": 0.3, "N_out": 0.2},
       "purple": {"N_in": 0.4, "N_unl": 0.25, "N_out": 0.2, "N_mined_p": 0.15}}

def posteriors(H, s_pos=1.5, s_neg=0.8, pi=0.02, mix=MIX):
    Ns = {}
    for name in ("N_in", "N_unl", "N_out", "N_mined_p"):
        h = smooth(H[name], s_neg)
        Ns[name] = h / max(h.sum(), 1e-9)
    out = {}
    for col in ("yellow", "purple"):
        N = sum(w * Ns[name] for name, w in mix[col].items())
        Pc = smooth(H[col + "_core"], s_pos); Pc /= Pc.sum()
        Pa = smooth(H[col + "_all"], s_pos); Pa /= Pa.sum()
        out[col] = (pi * Pc / (pi * Pc + (1 - pi) * N + 1e-12), pi * Pa / (pi * Pa + (1 - pi) * N + 1e-12), Pc, Pa)
    return out, None

def build(H, t_strong=0.5, t_weak=0.15, min_pc=2e-6, min_pa=5e-7, **kw):
    post, N = posteriors(H, **kw)
    lut = np.zeros(NB, np.uint8)
    for code, col in ((1, "yellow"), (3, "purple")):
        pc, pa, Pc, Pa = post[col]
        lut[(pa > t_weak) & (Pa > min_pa)] = code
        lut[(pc > t_strong) & (Pc > min_pc)] = code + 1
    return lut

if __name__ == "__main__":
    H = harvest()
    for k, v in H.items():
        print(k, int(v.sum()), "bins used", int((v > 0).sum()))
    np.savez_compressed("impl_model/hist.npz", **H)
    lut = build(H)
    np.save("impl_model/lut.npy", lut)
    print("lut classes", np.bincount(lut, minlength=5))
