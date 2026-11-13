"""compass.py <session> <from> <to> [every]: the arrow, the north disc and their difference over a stretch."""
import json, sys
import cv2, numpy as np
from pilot.foot import north_bearing, crop_ok
d, a, b = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
every = float(sys.argv[4]) if len(sys.argv) > 4 else 0.25
rows = [json.loads(l) for l in open(d + "/play.jsonl")]
frames = [json.loads(l) for l in open(d + "/frames.jsonl")]
by_id = {f.get("frame_id", f.get("id")): i for i, f in enumerate(frames)}
video = cv2.VideoCapture(d + "/video.mp4")
t0 = rows[0]["t"]
last = -9
seen = told = 0
for r in rows:
    t = r["t"] - t0
    if t < a or t > b:
        continue
    i = by_id.get(r["frame_id"])
    if i is None:
        continue
    video.set(cv2.CAP_PROP_POS_FRAMES, i)
    ok, bgr = video.read()
    if not ok:
        continue
    crop = np.ascontiguousarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)[530:700, 30:290])
    north = north_bearing(crop)
    arrow = r["reading"]["arrow"]
    seen += 1
    told += north is not None and arrow is not None
    if t - last >= every:
        last = t
        head = None if north is None or arrow is None else (arrow - north + 180) % 360 - 180
        pad = (r.get("result") or {}).get("pad") or {}
        print(f"{t:6.2f} ok={crop_ok(crop)} arrow={str(None if arrow is None else round(arrow)):>5} north={str(None if north is None else round(north)):>5} heading={str(None if head is None else round(head)):>5} left={[round(v,1) for v in pad.get('left',[0,0])]} right={pad.get('right')}")
print("ticks", seen, "with both", told)
