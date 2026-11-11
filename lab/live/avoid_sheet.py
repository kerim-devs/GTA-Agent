"""avoid_sheet.py <session> <out.jpg> <seconds>... : frames with every box and what the avoider makes of them."""
import json, sys, cv2, numpy as np
from pilot.objects import Detector
from pilot.avoid import Avoider, _seen, TRACK
d, out, seconds = sys.argv[1], sys.argv[2], [float(s) for s in sys.argv[3:]]
times = [json.loads(l)["t"] for l in open(d + "/frames.jsonl")]
video = cv2.VideoCapture(d + "/video.mp4"); det = Detector(); tiles = []
for s in seconds:
    i = min(range(len(times)), key=lambda k: abs(times[k] - times[0] - s))
    video.set(cv2.CAP_PROP_POS_FRAMES, i); ok, f = video.read()
    if not ok: continue
    f = cv2.resize(f, (1280, 720)); rgb = cv2.cvtColor(f, cv2.COLOR_BGR2RGB)
    every = det.detect(rgb, exclude_player=False); objects = det.detect(rgb)
    own = [o for o in every if o not in objects]
    a = Avoider().step(objects, 0.0, 0.0)
    for o in every:
        offset, wide, near = _seen(o); x0, y0, x1, y1 = map(int, o.box)
        mine = o in own; inway = near > 0 and abs(offset) < TRACK * wide
        colour = (255, 0, 0) if mine else (0, 0, 255) if inway else (0, 255, 0)
        cv2.rectangle(f, (x0, y0), (x1, y1), colour, 2)
        cv2.putText(f, f"{o.kind[:3]} {near:.2f}", (x0, max(14, y0 - 4)), 0, 0.6, colour, 2)
    ow = [round((o.box[2] - o.box[0]) / 1280, 2) for o in own if o.kind != "person"]
    cv2.putText(f, f"{s:.0f}s steer {a.steer:+.2f} pedal {a.pedal:.2f} {'URGENT' if a.urgent else ''} own {ow}", (8, 30), 0, 0.9, (0, 255, 255), 2)
    tiles.append(cv2.resize(f, (640, 360)))
cols = 3 if len(tiles) > 4 else len(tiles)
while len(tiles) % cols: tiles.append(np.zeros_like(tiles[0]))
cv2.imwrite(out, np.vstack([np.hstack(tiles[i:i + cols]) for i in range(0, len(tiles), cols)]))
