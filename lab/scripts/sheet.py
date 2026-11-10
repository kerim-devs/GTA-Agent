import json, sys
import av
import numpy as np
from PIL import Image

folder, out = sys.argv[1], sys.argv[2]
times = [float(x) for x in sys.argv[3:]]
frames = [json.loads(l) for l in open(folder + "/frames.jsonl") if l.strip()]
want = {}
for t in times:
    i = min(range(len(frames)), key=lambda k: abs(frames[k]["t"] - t))
    want[i] = t
tiles = {}
with av.open(folder + "/video.mp4") as c:
    for n, frame in enumerate(c.decode(video=0)):
        if n in want:
            tiles[n] = frame.to_ndarray(format="rgb24")
            if len(tiles) == len(want):
                break
order = sorted(tiles)
w, h = 640, 360
cols = 3
rows = (len(order) + cols - 1) // cols
sheet = Image.new("RGB", (cols * w, rows * h))
for k, n in enumerate(order):
    im = Image.fromarray(tiles[n]).resize((w, h))
    sheet.paste(im, ((k % cols) * w, (k // cols) * h))
    print(f"tile {k}: frame {n} at {want[n]:.0f} s")
sheet.save(out, quality=80)
