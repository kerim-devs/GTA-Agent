"""summ.py dev.json: print the summary and the route/bearing disagreements only."""
import json, sys
r = json.load(open(sys.argv[1]))
print(json.dumps({k: v for k, v in r.items() if k not in ("disagreements",)}, indent=None))
skip = sys.argv[2:] 
for d in r["disagreements"]:
    diffs = [x for x in d["diff"] if not any(x.startswith(s) for s in skip)]
    if diffs:
        print(" ", d["id"], "k=%d" % d["k"], "; ".join(diffs))
