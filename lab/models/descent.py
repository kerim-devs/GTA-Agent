"""Kerim's walk out of the door and down the stairs: the place and the stairs question, frame by frame.

    descent.py <video> <t0> <t1> <step> <out.json> [model]
"""
import json, sys
sys.path.insert(0, "/Users/kerim/Documents/ChatGPT/gta/pilot/src")
import cv2
from pilot import ahead, judge
from pilot.sides import open_share

video, t0, t1, step, out = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), sys.argv[5]
URL, MODEL = "http://192.168.0.248:1234", sys.argv[6] if len(sys.argv) > 6 else "qwen/qwen3-vl-4b"
EXTRA = sys.argv[7] if len(sys.argv) > 7 else None
cap = cv2.VideoCapture(video)
rows, at = [], t0
while at <= t1 + 1e-6:
    cap.set(cv2.CAP_PROP_POS_FRAMES, round(at * 60))
    ok, bgr = cap.read()
    if not ok:
        break
    whole = judge.encode(bgr, ahead.WIDTH)
    where = ahead.places(judge.post(URL, MODEL, whole, ahead.WHERE, 3, timeout=20)[0])
    place = ahead.PLACES[max(range(3), key=lambda i: where[i])] if where else None
    stairs = open_share(judge.post(URL, MODEL, whole, ahead.STAIRS.format(what="a screenshot"), 3, timeout=20)[0])
    parts = [open_share(judge.post(URL, MODEL, judge.encode(bgr[ahead.PART_ROWS, part], ahead.PART_WIDTH), ahead.STAIRS.format(what="part of a screenshot"), 3, timeout=20)[0]) for part in ahead.PARTS]
    rows.append({"t": at, "place": place, "where": where, "stairs": stairs, "parts": parts})
    print(f"{at:6.2f}s {place or '?':8s} {max(where) if where else 0:.2f} | stairs {stairs:.2f}  L {parts[0]:.2f} M {parts[1]:.2f} R {parts[2]:.2f}", flush=True)
    at += step
json.dump(rows, open(out, "w"), indent=1)
