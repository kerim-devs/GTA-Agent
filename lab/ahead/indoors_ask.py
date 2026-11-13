"""Asks the local model whether a frame was taken indoors, and of outdoor frames the exit question too."""
import json, sys
from pathlib import Path
import cv2
from pilot import judge
from pilot.sides import open_share

url, model = judge.endpoint("http://192.168.0.248:1234=qwen/qwen3-vl-8b")
INDOORS = (
    "This is a screenshot of a game. Is the player's character inside a building, in a room?\n"
    "A: yes, indoors, in a room\n"
    "B: no, outdoors"
)
EXIT = (
    "This is a screenshot of a game, taken inside a room. Does it show a door or doorway through "
    "which a person could walk out of the room to the outside?\n"
    "A: yes, an exit to the outside is in this picture\n"
    "B: no, only walls, windows, furniture or people"
)
def ask(bgr, q):
    return open_share(judge.post(url, model, judge.encode(bgr, 640), q, 3, timeout=20)[0])

D = Path(sys.argv[1])
out = []
for f in json.load(open(D / "list.json"))[::3]:
    im = cv2.imread(str(D / f["file"]))
    out.append(("outdoors", f["file"], ask(im, INDOORS), ask(im, EXIT)))
video = cv2.VideoCapture(sys.argv[2] + "/video.mp4")
for at in range(2, 64, 2):
    video.set(cv2.CAP_PROP_POS_FRAMES, at * 60)
    ok, im = video.read()
    if ok:
        out.append(("indoors", f"shop-{at}s", ask(im, INDOORS), ask(im, EXIT)))
for label in ("outdoors", "indoors"):
    v = [r for r in out if r[0] == label]
    print(label, "n", len(v), "| called indoors:", sum(r[2] >= 0.5 for r in v), "| exit seen (>=0.9):", sum(r[3] >= 0.9 for r in v), "| exit >=0.5:", sum(r[3] >= 0.5 for r in v))
    odd = [(r[1][-28:], round(r[2], 2), round(r[3], 2)) for r in v if (r[2] >= 0.5) != (label == "indoors") or (label == "indoors" and r[3] >= 0.5)]
    print("   ", odd[:14])
json.dump(out, open(D / "indoors.json", "w"), indent=1)
