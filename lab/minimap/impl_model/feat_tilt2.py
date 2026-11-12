import sys
from pathlib import Path
import numpy as np, cv2
sys.path.insert(0, str(Path(__file__).resolve().parent))
from devlabels import dev
K = {s: np.ones((s, s), np.uint8) for s in (3, 5, 9, 15)}
BANDS = [(2, 24), (24, 46), (46, 68), (68, 90), (90, 112)]
def feats(c):
    g = cv2.cvtColor(c, cv2.COLOR_RGB2GRAY)
    m = g[28:142, 34:214]
    o = {s: cv2.morphologyEx(m, cv2.MORPH_OPEN, K[s]).astype(np.float32) for s in K}
    mf = m.astype(np.float32)
    f = []
    for a, b in BANDS:
        t3 = (mf[a:b] - o[3][a:b]).mean(); t5 = (o[3][a:b] - o[5][a:b]).mean(); t9 = (o[5][a:b] - o[9][a:b]).mean(); t15 = (o[9][a:b] - o[15][a:b]).mean()
        f += [t3, t5, t9, t15]
    return np.array(f)
def logreg(X, y, l2=1.0, iters=300):
    w = np.zeros(X.shape[1]); b = 0.0
    for _ in range(iters):   # Newton / IRLS
        z = X @ w + b; p = 1 / (1 + np.exp(-z))
        g = X.T @ (p - y) + l2 * w; gb = (p - y).sum()
        W = p * (1 - p) + 1e-6
        Hm = (X.T * W) @ X + l2 * np.eye(X.shape[1]); hb = (X.T @ W); hbb = W.sum()
        Hf = np.block([[Hm, hb[:, None]], [hb[None, :], np.array([[hbb]])]])
        step = np.linalg.solve(Hf, np.concatenate([g, [gb]]))
        w -= step[:-1]; b -= step[-1]
    return w, b
if __name__ == "__main__":
    crops, meta, labs = dev()
    L = [l for l in labs if l["minimap"] != "none"]
    F = np.array([feats(np.asarray(crops[l["k"]])) for l in L])
    y = np.array([l["minimap"] == "tilted" for l in L], float)
    def design(F):
        F = F.reshape(len(F), 5, 4)
        tot = F.sum(2) + 2.0
        thin = (F[:, :, 0] + F[:, :, 1]) / tot          # share of thin bright structure per band
        wide = (F[:, :, 3]) / tot
        return np.concatenate([thin, wide, np.log(tot)], 1)
    X = design(F); mu, sd = X.mean(0), X.std(0) + 1e-6; Xn = (X - mu) / sd
    for l2 in (0.3, 1, 3, 10):
        wrong = []
        for i in range(len(L)):
            tr = np.arange(len(L)) != i
            w, b = logreg(Xn[tr], y[tr], l2)
            p = 1 / (1 + np.exp(-(Xn[i] @ w + b)))
            if (p > 0.5) != y[i]: wrong.append((L[i]["id"], L[i]["k"], L[i]["minimap"], "C" if L[i]["corrupt"] else "-", round(float(p), 2)))
        print("l2", l2, "LOO errors", len(wrong), "of", len(L)); 
        if l2 == 3: print(wrong)
