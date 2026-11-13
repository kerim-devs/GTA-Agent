"""Frames of tonight's walks with what the guard found out the hard way: held up, or running free.

A frame counts as blocked where the guard, after a second and a half of pushing, called the figure held
up (go to climb or round) while the stick pointed into the picture; as free where the walk ran on for
three seconds before and after with the stick into the picture. Written as JPEG with a list.
"""
import json, os, re, sys
from pathlib import Path
import cv2

R = Path("/Users/kerim/recordings/pilot")
out = Path(sys.argv[1]); out.mkdir(exist_ok=True)
names = sorted(n for n in os.listdir(R) if "20261113-0011" <= n <= "20261113-0230")
found = []
for n in names:
    D = R / n
    try:
        rows = []
        for l in open(D / "play.jsonl"):
            try: rows.append(json.loads(l))
            except ValueError: pass
        index = {e["frame_id"]: e["i"] for e in map(json.loads, open(D / "frames.jsonl"))}
    except OSError:
        continue
    walk = [r for r in rows if (r.get("skill") or {}).get("name") == "walk_to_point" and r.get("result")]
    if len(walk) < 60:
        continue
    def state(r):
        m = re.search(r"state=(\w+)", (r.get("skill") or {}).get("reason") or "")
        return m[1] if m else None
    def forward(r):
        x, y = r["result"]["pad"]["left"]
        return -y
    states = [state(r) for r in walk]
    times = [r["t"] for r in walk]
    picks = []
    # held up: the tick on which go turns into climb or round
    for i in range(1, len(walk)):
        if states[i - 1] == "go" and states[i] in ("climb", "round") and forward(walk[i - 1]) >= 0.7:
            picks.append((i - 1, "blocked"))
    # free: go for three seconds either side, one every eight seconds
    last = -99
    for i, r in enumerate(walk):
        t = times[i]
        if t - last < 8 or states[i] != "go" or forward(r) < 0.7:
            continue
        near = [s for s, tt in zip(states, times) if abs(tt - t) <= 3.0]
        moving = "motion=still" not in ((r.get("skill") or {}).get("reason") or "")
        if all(s == "go" for s in near) and times[0] + 3 < t < times[-1] - 3 and moving:
            picks.append((i, "free")); last = t
    if not picks:
        continue
    video = cv2.VideoCapture(str(D / "video.mp4"))
    for i, label in picks:
        r = walk[i]
        if r["frame_id"] not in index:
            continue
        video.set(cv2.CAP_PROP_POS_FRAMES, index[r["frame_id"]])
        ok, bgr = video.read()
        if not ok:
            continue
        name = f"{n}-{r['t'] - times[0]:06.1f}-{label}.jpg"
        cv2.imwrite(str(out / name), bgr, [cv2.IMWRITE_JPEG_QUALITY, 92])
        found.append({"file": name, "session": n, "t": round(r["t"] - times[0], 1), "label": label})
json.dump(found, open(out / "list.json", "w"), indent=1)
import collections
print(len(found), collections.Counter(f["label"] for f in found), "sessions", len({f["session"] for f in found}))
