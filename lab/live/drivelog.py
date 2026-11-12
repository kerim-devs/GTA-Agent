"""drivelog.py <session>: pedals, route and distance of a drive in a few lines."""

import collections
import json
import sys

d = sys.argv[1]
rows = [json.loads(l) for l in open(d + "/play.jsonl")]
t0 = rows[0]["t"]
name = lambda r: r["skill"].get("name") if isinstance(r["skill"], dict) else r["skill"]
ends = [
    (
        round(r["t"] - t0, 1),
        name(r),
        r["result"].get("status"),
        r["result"].get("reason"),
    )
    for r in rows
    if r["result"].get("status") in ("done", "failed") and name(r)
]
print("ends", ends[:8])
print(
    "route",
    collections.Counter(r["reading"]["route"] for r in rows).most_common(),
    "| r2",
    collections.Counter(round(r["sent_pad"]["r2"], 1) for r in rows).most_common(5),
    "| l2",
    collections.Counter(round(r["sent_pad"]["l2"], 1) for r in rows).most_common(4),
)
dist = [
    (round(r["t"] - t0), r["reading"]["gps_distance"])
    for r in rows
    if r["reading"].get("gps_distance")
]
print("distance", dist[:: max(1, len(dist) // 12)])
head = [json.loads(l) for l in open(d + "/head.jsonl")]
print(
    "head",
    [
        (round(h["t"] - head[0]["t"]), [e.get("kind") for e in h["request"]["events"]])
        for h in head
        if h["type"] == "request"
    ][:12],
)
