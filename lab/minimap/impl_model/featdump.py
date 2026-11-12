"""featdump.py: candidate-route features for every crop (held-out ks excluded), saved to proto/feats.json."""
import sys, json
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import tools
mod = tools.load_impl(str(ROOT / "impl_model" / "proto" / "minimap.py"))
crops, meta, golden = tools.load()
held = {g["k"] for g in golden if g["split"] == "held"}
rows = []
for k in range(len(meta)):
    if k in held: continue
    cls, res = mod.analyse(np.asarray(crops[k]))
    for col, f in res.items():
        if f is None: continue
        r = {kk: (float(v) if isinstance(v, (float, np.floating)) else int(v) if isinstance(v, (int, np.integer, bool, np.bool_)) else v) for kk, v in f.items() if kk not in ("comp", "partb")}
        r["k"] = k; r["col"] = col
        r["drive"] = (col == "yellow" and 817 <= k <= 1092) or (col == "purple" and 1389 <= k <= 1432)
        rows.append(r)
json.dump(rows, open(ROOT / "impl_model" / "proto" / "feats.json", "w"))
print(len(rows), "candidates;", sum(r["drive"] for r in rows), "inside the drives")
