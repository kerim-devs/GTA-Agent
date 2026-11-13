"""Frames of a session inside a room: what the local model says about a way out in each third of the picture."""
import json, math, sys
from pathlib import Path
import cv2, numpy as np
from pilot import judge
from pilot.sides import open_share

folder, out = Path(sys.argv[1]), Path(sys.argv[2])
times = [float(v) for v in sys.argv[3:]]
url, model = judge.endpoint("http://192.168.0.248:1234=qwen/qwen3-vl-8b")
Q = (
    "This is part of a screenshot of a game, taken inside a room. Does it show a door or doorway through "
    "which a person could walk out of the room to the outside?\n"
    "A: yes, an exit to the outside is in this picture\n"
    "B: no, only walls, windows, furniture or people"
)
video = cv2.VideoCapture(str(folder / "video.mp4"))
fps = video.get(cv2.CAP_PROP_FPS) or 60
tiles, rows = [], []
for at in times:
    video.set(cv2.CAP_PROP_POS_FRAMES, round(at * fps))
    ok, bgr = video.read()
    if not ok:
        continue
    shares = []
    for lo, hi in ((0, 520), (380, 900), (760, 1280)):
        part = bgr[60:640, lo:hi]
        choice, took = judge.post(url, model, judge.encode(part, 448), Q, 3, timeout=20)
        shares.append(open_share(choice))
    whole, took = judge.post(url, model, judge.encode(bgr, 640), Q.replace("part of a", "a"), 3, timeout=20)
    w = open_share(whole)
    rows.append({"t": at, "left": shares[0], "middle": shares[1], "right": shares[2], "whole": w})
    im = cv2.resize(bgr, (426, 240))
    text = f"{at:.0f}s L{shares[0]:.2f} M{shares[1]:.2f} R{shares[2]:.2f} all{w:.2f}"
    cv2.putText(im, text, (4, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)
    tiles.append(im)
    print(text, flush=True)
while len(tiles) % 4:
    tiles.append(np.zeros_like(tiles[0]))
cv2.imwrite(str(out / "sheet.jpg"), np.vstack([np.hstack(tiles[i:i + 4]) for i in range(0, len(tiles), 4)]))
json.dump(rows, open(out / "answers.json", "w"), indent=1)
