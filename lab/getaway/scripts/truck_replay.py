"""get_away on the truck session's ticks from the moment the figure sits in the truck (truck_extract.py).

Each tick gets what the conductor gives a skill: minimap.read of the crop, `moving` from the map's motion
as loop.Pipeline makes it, hud.read of the frame, the judge's mode; no detections (the detector is not run
offline). The frame is the crop put back into a black 1280x720 picture, which is all get_away looks at.
Run A: one skill from the first tick on, over every tick in order. Run B: a fresh skill at each stretch
where the game screen shows again after the pause map, to the next screen that is not the game."""
import json, sys
from collections import Counter, deque
from pathlib import Path
from common import WORK
import numpy as np
from pilot import minimap
from pilot.contract import HUD_RECT, Hud, Observation, Pad
from pilot.getaway import GetAway
from pilot.motion import map_motion, motion_state

DIR = WORK / "truck"
crops, rows = [], []
for p in sorted(DIR.glob("piece*.npz")):
    d = np.load(p)
    crops += list(d["crops"]); rows += json.loads(str(d["rows"]))
x, y, w, h = HUD_RECT

def observations(sel):
    hist = deque()
    for k in sel:
        r, crop = rows[k], crops[k]
        t = r["t"]
        while hist and hist[0][0] < t - 1.2:
            hist.popleft()
        moving = None
        if hist and t - hist[0][0] >= 0.15:
            _, prev = min(hist, key=lambda item: abs(t - item[0] - 0.2))
            moving = motion_state(map_motion(prev, crop))
            if moving is not True and t - hist[0][0] >= 0.8:
                moving = motion_state(map_motion(hist[0][1], crop))
        hist.append((t, crop))
        frame = np.zeros((720, 1280, 3), np.uint8)
        frame[y:y + h, x:x + w] = crop
        yield r, Observation(reading=minimap.read(crop), moving=moving, time=t, frame=frame,
                             hud=Hud(wanted=r["wanted"], screen=r["screen"]), mode=r["mode"])

def run(sel, label):
    skill = GetAway({})
    out = []
    for r, obs in observations(sel):
        res = skill.step(obs)
        out.append((r, res, skill.state, skill.heading - skill.arrow))
        if res.status != "running":
            break
    first = out[0][1].pad
    buttons = sorted({b for _, res, _, _ in out for b in res.pad.buttons})
    whys = Counter(s for _, _, s, _ in out)
    end = out[-1][1]
    print(f"{label}: ticks {len(out)} from {out[0][0]['t']:.2f} to {out[-1][0]['t']:.2f} s; first tick steer "
          f"{first.left[0]:+.2f} r2 {first.r2:.2f} l2 {first.l2:.2f} buttons {list(first.buttons)}; buttons ever "
          f"{buttons}; pedal down on {sum(res.pad.r2 > 0 for _, res, st, _ in out if st.startswith('drive'))} of "
          f"{sum(st.startswith('drive') for _, _, st, _ in out)} driving ticks; end {end.status} {end.reason or '(frames end)'}"
          + (f", end pad neutral {end.pad == Pad()}" if end.status != 'running' else '') + f"; states {dict(whys)}")
    return out

print("ticks", len(rows), "from", rows[0]["t"], "screens", Counter(r["screen"] for r in rows),
      "wanted", Counter(r["wanted"] for r in rows), "modes", Counter(r["mode"] for r in rows))
a = run(range(len(rows)), "A, one skill from 8.38 s")
# stretches of the game screen after the pause map
stretches, k = [], 0
while k < len(rows):
    if rows[k]["screen"] == "game" and (k == 0 or rows[k - 1]["screen"] != "game"):
        j = k
        while j < len(rows) and rows[j]["screen"] == "game":
            j += 1
        stretches.append(range(k, j)); k = j
    else:
        k += 1
for s in stretches:
    if rows[s[-1]]["t"] - rows[s[0]]["t"] >= 0.3:
        run(s, f"B, fresh at {rows[s[0]]['t']:.2f} s")
json.dump([dict(t=r["t"], status=res.status, reason=res.reason, state=st, rel=round(rel, 1),
                steer=res.pad.left[0], r2=res.pad.r2, l2=res.pad.l2, buttons=list(res.pad.buttons),
                screen=r["screen"], wanted=r["wanted"], mode=r["mode"], pilot=r["skill"])
           for r, res, st, rel in a], open(DIR / "run_a.json", "w"))
