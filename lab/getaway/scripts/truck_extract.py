"""The truck session's ticks from the moment the figure sits in the truck: per play.jsonl tick the HUD crop
of its frame, what hud.read says, and the judge's latest mode. Pieces of 10 s of session time, saved one by
one; exits 3 while P68_BUSY exists, and a rerun goes on where it stopped."""
import json, sys, time
from pathlib import Path
from common import WORK, busy
import cv2
import numpy as np
from pilot import hud
from pilot.foot import hud_crop

S = Path("/Users/kerim/recordings/pilot/20261112-221857")
OUT = WORK / "truck"
START = 8.38  # enter_vehicle done in play.jsonl
OFFSET = 388152.944473333  # head.jsonl's startup request, monotonic, is play.jsonl's first tick
play = [json.loads(l) for l in open(S / "play.jsonl")]
index = {json.loads(l)["frame_id"]: json.loads(l)["i"] for l in open(S / "frames.jsonl")}
judge = [json.loads(l) for l in open(S / "judge.jsonl")]
ticks = [r for r in play if r["t"] >= START - 0.01]
cap = cv2.VideoCapture(str(S / "video.mp4"))
pos = 0
for piece in range(int(START // 10), 8):
    out = OUT / f"piece{piece}.npz"
    sel = [r for r in ticks if piece * 10 <= r["t"] < piece * 10 + 10]
    if out.exists() or not sel:
        continue
    if busy():
        print("console-busy: stopped before piece", piece); sys.exit(3)
    t0 = time.time()
    crops, rows = [], []
    for r in sel:
        i = index[r["frame_id"]]
        if i < pos:
            cap.set(cv2.CAP_PROP_POS_FRAMES, i); pos = i
        while pos < i:
            cap.grab(); pos += 1
        ok, bgr = cap.read(); pos += 1
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        h = hud.read(rgb)
        mode = None
        for j in judge:
            if j["t"] - OFFSET <= r["t"]:
                mode = j["answers"].get("mode", {}).get("value")
        crops.append(hud_crop(rgb).copy())
        rows.append(dict(t=r["t"], frame_id=r["frame_id"], wanted=h.wanted, screen=h.screen, mode=mode,
                         minimap=r["reading"]["minimap"], skill=(r.get("skill") or {}).get("name"),
                         buttons=(r.get("sent_pad") or {}).get("buttons")))
    np.savez_compressed(out, crops=np.array(crops), rows=json.dumps(rows))
    print("piece", piece, len(sel), "ticks", round(time.time() - t0, 1), "s", flush=True)
