"""place_replay.py <session> <from> <to> <every>: what the model says of the place, frame by frame."""
import json, sys, time
import cv2
from pilot import judge
from pilot.ahead import INDOORS, WIDTH
from pilot.sides import open_share

url, model = judge.endpoint("http://192.168.0.248:1234=qwen/qwen3-vl-8b")
d, a, b, every = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4])
times = [json.loads(l)["t"] for l in open(d + "/frames.jsonl")]
video = cv2.VideoCapture(d + "/video.mp4")
out, took = [], []
t = a
while t <= b:
    i = min(range(len(times)), key=lambda k: abs(times[k] - times[0] - t))
    video.set(cv2.CAP_PROP_POS_FRAMES, i)
    ok, bgr = video.read()
    if not ok:
        break
    began = time.monotonic()
    share = open_share(judge.post(url, model, judge.encode(bgr, WIDTH), INDOORS, 3, timeout=20)[0])
    took.append(time.monotonic() - began)
    out.append((round(t, 1), None if share is None else round(share, 2)))
    t += every
print(d[-15:], " ".join(f"{t}:{s}" for t, s in out))
room = [t for t, s in out if s is not None and s >= 0.9]
mid = [t for t, s in out if s is not None and 0.5 <= s < 0.9]
print("   n", len(out), "room>=0.9", len(room), "between", len(mid), "median answer", round(sorted(took)[len(took) // 2], 2), "s")
