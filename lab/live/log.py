"""log.py <session>: the skills of a session in order, what went to the console, the judge's words."""

import collections
import json
import os
import sys

d = sys.argv[1]
rows = [json.loads(l) for l in open(d + "/play.jsonl")]
t0 = rows[0]["t"]
last = None
for r in rows:
    res = r.get("result") or {}
    name = r["skill"].get("name") if isinstance(r["skill"], dict) else r["skill"]
    key = (name, res.get("status"), res.get("reason"))
    if key != last:
        print(
            f"{r['t'] - t0:6.2f} {name} {res.get('status')} {res.get('reason') or ''} map={r['reading'].get('minimap')}"
        )
        last = key
sent = [r["sent_pad"] for r in rows if r.get("sent_pad")]
for stick in ("left", "right"):
    print(
        stick,
        collections.Counter(
            (round(p[stick][0], 2), round(p[stick][1], 2)) for p in sent
        ).most_common(6),
    )
print("buttons", collections.Counter(tuple(p["buttons"]) for p in sent).most_common(6))
print(
    "status",
    collections.Counter(str(r["status"]) for r in rows).most_common(4),
    "ticks",
    len(rows),
    "stale",
    sum(not r["fresh"] for r in rows),
)
if os.path.exists(d + "/judge.jsonl"):
    rows_j = [json.loads(l) for l in open(d + "/judge.jsonl")]
    j = [x for x in rows_j if "answers" in x]
    print(
        "judge failures",
        collections.Counter(
            str(x.get("error"))[:60] + " @" + str(x.get("server"))[:28]
            for x in rows_j
            if "answers" not in x
        ).most_common(3),
    )
    if j:
        span = j[-1]["t"] - j[0]["t"]
        print(
            "judge",
            len(j),
            f"{len(j) / span:.2f}/s" if span else "",
            "said",
            collections.Counter(x["answers"]["mode"]["value"] for x in j).most_common(),
            "accepted",
            collections.Counter(str(x["mode"]) for x in j).most_common(),
            "servers",
            collections.Counter(x["server"] for x in j).most_common(),
        )
