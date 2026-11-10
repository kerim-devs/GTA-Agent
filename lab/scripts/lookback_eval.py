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
def at(x):
    return small[min(range(len(t)), key=lambda k: abs(t[k] - x))]
presses = [r["t"] for r in pad if "r3" in r["buttons"]]
releases = [r["t"] for r in pad if not r["buttons"] and r["t"] > presses[0]]
base = at(presses[0] - 0.15)
print("hold  view changed while held   back to normal after release")
ok = 0
for n, p in enumerate(presses):
    rel = next(x for x in releases if x > p)
    held = float(np.abs(at(p + 0.5) - base).mean())
    after = float(np.abs(at(rel + 0.5) - base).mean())
    good = held > 12 and after < 12
    ok += good
    print(f"{n + 1:3d}   {held:6.1f}                    {after:6.1f}   {'ok' if good else 'MISSED'}")
print(f"{ok} of {len(presses)} holds arrived and were released")
