"""ruleeval.py "<python expression over feature names>": which candidates pass, inside and outside the drives, and vs dev labels."""
import json, sys
sys.path.insert(0, "impl_model")
from devlabels import dev
rows = json.load(open("impl_model/proto/feats.json"))
expr = sys.argv[1]
keys = ["part_nS", "part_area", "purity", "halo", "dtmax", "start", "part_ext", "ext", "gap", "n_out", "clutter", "s_out", "dmg", "dmg_loc"]
def show(r):
    return f"{r['col'][0]} {r['k']:4d} " + " ".join(f"{k}={r[k]:.2f}" if isinstance(r[k], float) else f"{k}={r[k]}" for k in keys)
ok = lambda r: bool(eval(expr, {}, r))
_, _, labs = dev()
lab = {l["k"]: l for l in labs}
print("OUT-OF-DRIVE passing:")
for r in rows:
    if not r["drive"] and ok(r): print("  ", show(r))
fails = [r for r in rows if r["drive"] and not ok(r)]
print(f"IN-DRIVE failing ({len(fails)} of {sum(r['drive'] for r in rows)}):")
for r in fails: print("  ", show(r), "| dev label:", lab[r["k"]]["route"] if r["k"] in lab else "-")
have = {(r["k"], r["col"]) for r in rows if ok(r)}
print("DEV: route labels not passing:", [(l["id"], l["k"]) for l in labs if l["route"] != "none" and (l["k"], l["route"]) not in have])
print("DEV: none labels passing:", [(l["id"], l["k"]) for l in labs if l["route"] == "none" and any((l["k"], c) in have for c in ("yellow", "purple"))])
