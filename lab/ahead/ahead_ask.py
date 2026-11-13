"""Asks the local model of each collected frame whether the figure can walk on straight ahead."""
import json, math, sys, time
from pathlib import Path
import cv2
from pilot import judge

D = Path(sys.argv[1])
url, model = judge.endpoint("http://192.168.0.248:1234=qwen/qwen3-vl-8b")
QUESTION = (
    "This is a screenshot of a game. The player's character is seen from behind in the middle of the "
    "picture. Can the character walk straight ahead, away from the camera, for the next few steps?\n"
    "A: yes, the ground straight ahead of the character is open\n"
    "B: no, a wall, a building, a fence, a rock, a vehicle or another obstacle stands right in front of "
    "the character"
)
VIEWS = {
    "whole": lambda im: (im, 640),
    "middle": lambda im: (im[110:650, 290:990], 448),
}

def share(choice):
    found = judge.letters(choice)
    if not found:
        return None
    letter, top = found[0]
    w = {k: math.exp(v) for k, v in top.items() if k in "AB" and math.isfinite(v)}
    if w and sum(w.values()) > 0:
        return w.get("A", 0.0) / sum(w.values())
    return {"A": 1.0, "B": 0.0}.get(letter)

items = json.load(open(D / "list.json"))
out = []
for k, f in enumerate(items):
    im = cv2.imread(str(D / f["file"]))
    row = dict(f)
    for name, view in VIEWS.items():
        part, width = view(im)
        image = judge.encode(part, width)
        try:
            choice, took = judge.post(url, model, image, QUESTION, 3, timeout=20)
            row[name], row[name + "_s"] = share(choice), round(took, 3)
        except Exception as exc:
            row[name], row[name + "_error"] = None, f"{type(exc).__name__}: {exc}"
    out.append(row)
    if k % 30 == 0:
        print(k, row.get("whole"), row.get("middle"), flush=True)
json.dump(out, open(D / "answers.json", "w"), indent=1)
for name in VIEWS:
    for label in ("blocked", "free"):
        v = [r[name] for r in out if r["label"] == label and r[name] is not None]
        said_open = sum(x >= 0.5 for x in v)
        times = sorted(r[name + "_s"] for r in out if r.get(name + "_s"))
        print(f"{name:7s} {label:8s} n {len(v):3d} said open {said_open:3d} said blocked {len(v) - said_open:3d}  median time {times[len(times)//2]}")
