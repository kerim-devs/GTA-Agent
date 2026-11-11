import json
from pathlib import Path

import cv2
import numpy as np

from pilot.waypoint import map_shift

root = Path("/Users/kerim/recordings/pilot")


def frame_get(d, fs, t):
    f = min(fs, key=lambda z: abs(z["t"] - t))
    cap = cv2.VideoCapture(str(d / "video.mp4"))
    cap.set(cv2.CAP_PROP_POS_FRAMES, f["i"])
    ok, img = cap.read()
    cap.release()
    assert ok
    return f, cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def phase(a, b, box):
    x0, x1, y0, y1 = box
    a = cv2.cvtColor(a, cv2.COLOR_RGB2GRAY)[y0:y1, x0:x1].astype(np.float32)
    b = cv2.cvtColor(b, cv2.COLOR_RGB2GRAY)[y0:y1, x0:x1].astype(np.float32)
    a = cv2.Sobel(a, cv2.CV_32F, 1, 0) + cv2.Sobel(a, cv2.CV_32F, 0, 1)
    b = cv2.Sobel(b, cv2.CV_32F, 1, 0) + cv2.Sobel(b, cv2.CV_32F, 0, 1)
    return cv2.phaseCorrelate(a, b)


def attempts(stamp):
    d = root / f"20261111-{stamp}"
    rows = [json.loads(x) for x in (d / "play.jsonl").read_text().splitlines()]
    fs = [json.loads(x) for x in (d / "frames.jsonl").read_text().splitlines()]
    active = [r for r in rows if (r.get("skill") or {}).get("name") == "set_waypoint"]
    groups = []
    g = []
    last = -99
    for r in active:
        if r["t"] - last > 0.7 and g:
            groups.append(g)
            g = []
        g.append(r)
        last = r["t"]
    if g:
        groups.append(g)
    out = []
    for g in groups:
        presses = []
        run = None
        for r in g:
            left = r["result"]["pad"]["left"]
            sig = tuple(round(x, 2) for x in left)
            if sig != (0, 0) and run is None:
                run = [r["t"], r["t"], sig]
            elif run is not None and sig == run[2]:
                run[1] = r["t"]
            elif run is not None:
                presses.append(run)
                run = None
        if run:
            presses.append(run)
        vals = []
        for s, e, stick in presses:
            f1, a = frame_get(d, fs, s - 0.18)
            f2, b = frame_get(d, fs, e + 0.23)
            (v1, q1) = phase(a, b, (250, 980, 165, 565))
            (v2, q2) = phase(a, b, (700, 980, 165, 565))
            old = map_shift(a, b)
            vals.append(
                {
                    "pad_start": round(s, 3),
                    "pad_end": round(e, 3),
                    "seconds": round(e - s, 3),
                    "left": stick,
                    "before": {"t": round(f1["t"], 4), "frame_id": f1["frame_id"]},
                    "after": {"t": round(f2["t"], 4), "frame_id": f2["frame_id"]},
                    "old_shift": None if old is None else [round(x, 2) for x in old],
                    "broad_dxdy": [round(x, 2) for x in v1],
                    "broad_response": round(q1, 3),
                    "right_dxdy": [round(x, 2) for x in v2],
                    "right_response": round(q2, 3),
                }
            )
        final = next(
            (r for r in reversed(g) if (r["skill"] or {}).get("status") in ("failed", "done")), g[-1]
        )
        out.append(
            {
                "start": round(g[0]["t"], 3),
                "end": round(g[-1]["t"], 3),
                "result": (final["skill"] or {}).get("reason"),
                "pushes": vals,
            }
        )
    return out


allx = {s: attempts(s) for s in ["123334", "123938", "125537"]}
Path(__file__).with_name("p35-push-inventory.json").write_text(json.dumps(allx, indent=2) + "\n")
for st, groups in allx.items():
    print("\n", st)
    for n, g in enumerate(groups, 1):
        print(n, g["start"], g["end"], g["result"])
        for p in g["pushes"]:
            print(
                " ",
                p["pad_start"],
                p["pad_end"],
                p["left"],
                "=>",
                p["broad_dxdy"],
                p["broad_response"],
                "/",
                p["right_dxdy"],
                p["right_response"],
            )
