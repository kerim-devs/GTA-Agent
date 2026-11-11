"""damage_count.py <session> <from> <to> : how many frames of a stretch the minimap reader calls damaged."""
import json, sys, cv2
from pilot.minimap import read
import pilot.calibrate as c
d, a, b = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
times = [json.loads(l)["t"] for l in open(d + "/frames.jsonl")]
video = cv2.VideoCapture(d + "/video.mp4"); n = bad = 0; s = a
while s < b:
    i = min(range(len(times)), key=lambda k: abs(times[k] - times[0] - s))
    video.set(cv2.CAP_PROP_POS_FRAMES, i); ok, f = video.read(); s += 0.5
    if not ok: continue
    rgb = cv2.cvtColor(cv2.resize(f, (1280, 720)), cv2.COLOR_BGR2RGB)
    r = read(c.minimap_crop(rgb)); n += 1; bad += bool(r.corrupt)
print(f"{d[-15:]} {a:.0f}-{b:.0f}s damaged {bad}/{n}")
