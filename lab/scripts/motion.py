"""Is the car moving? Frame-to-frame change of a road patch beside the car, per phase of the loop's input."""
import json, statistics, sys
import av
import numpy as np

d = sys.argv[1]
fr = [json.loads(l) for l in open(d + "/frames.jsonl") if l.strip()]
pad = [json.loads(l) for l in open(d + "/pad.jsonl") if l.strip() and '"agent"' in l]
patches = []
with av.open(d + "/video.mp4") as c:
    for f in c.decode(video=0):
        patches.append(f.to_ndarray(format="gray")[400:540:2, 150:480:2].astype(np.int16))
change = [0.0] + [float(np.abs(b - a).mean()) for a, b in zip(patches, patches[1:])]
t = [r["t"] for r in fr]
# phases from the recorded agent states
spans = []
for a, b in zip(pad, pad[1:] + [{"t": t[-1]}]):
    kind = "gas" if a["r2"] > 0 else "brake" if a["l2"] > 0 else "rest"
    spans.append((kind, a["t"], b["t"]))
print("phase   from    to   frames  median change")
for kind, t0, t1 in spans:
    lo = t0 + (0.45 if kind != "brake" else 0.0)  # skip the first moment of a phase
    vals = [c for c, x in zip(change, t) if lo <= x < t1]
    if vals:
        print(f"{kind:6} {t0:5.1f} {t1:5.1f}  {len(vals):4d}   {statistics.median(vals):6.2f}")
