import json, sys
import av
import numpy as np
d = sys.argv[1]
fr = [json.loads(l) for l in open(d + "/frames.jsonl") if l.strip()]
pad = [json.loads(l) for l in open(d + "/pad.jsonl") if l.strip() and '"agent"' in l]
small = []
with av.open(d + "/video.mp4") as c:
    for f in c.decode(video=0):
        small.append(f.to_ndarray(format="gray")[::8, ::8].astype(np.int16))
t = [r["t"] for r in fr]
events = [(r["t"], "press" if "r3" in r["buttons"] else "release") for r in pad]
events = [e for k, e in enumerate(events) if k == 0 or e[1] != events[k - 1][1]]
if events[0][1] == "release":
    events = events[1:]
for when, kind in events:
    k0 = max(k for k in range(len(t)) if t[k] <= when)
    ref = small[k0]
    flip = next((k for k in range(k0 + 1, len(t)) if float(np.abs(small[k] - ref).mean()) > 15), None)
    if flip is None:
        print(f"{kind:8} at {when:6.2f} s: the picture never changed")
    else:
        print(f"{kind:8} at {when:6.2f} s: picture changed after {1000 * (t[flip] - when):5.0f} ms")
gaps = [b - a for a, b in zip(t, t[1:])]
print(f"frames {len(t)} in {t[-1]:.1f} s; longest gap {1000 * max(gaps):.0f} ms; gaps over 150 ms: {sum(g > 0.15 for g in gaps)}")
