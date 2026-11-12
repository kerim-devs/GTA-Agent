"""scan.py module.py: run the reader on all crops; list route detections as runs, and gaps inside the known drives."""
import sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import tools
mod = tools.load_impl(sys.argv[1])
crops, meta, golden = tools.load()
R = [mod.read(np.asarray(crops[k])) for k in range(len(meta))]
np.save(Path(sys.argv[1]).parent / "scan_route.npy", np.array([{"none": 0, "yellow": 1, "purple": 2}[r.route] for r in R]))
def runs(flags):
    out, s = [], None
    for i, f in enumerate(list(flags) + [False]):
        if f and s is None: s = i
        if not f and s is not None: out.append((s, i - 1)); s = None
    return out
for col in ("yellow", "purple"):
    print(col, "runs:", " ".join(f"{a}" if a == b else f"{a}-{b}" for a, b in runs([r.route == col for r in R])))
print("none inside 817..1066:", " ".join(str(k) for k in range(817, 1067) if R[k].route == "none"))
print("none inside 1385..1432:", " ".join(str(k) for k in range(1385, 1433) if R[k].route == "none"))
print("minimap rates", {c: sum(r.minimap == c for r in R) for c in ("none", "flat", "tilted")}, "corrupt", sum(r.corrupt for r in R))
