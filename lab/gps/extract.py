"""Dump what the text recogniser reads in the distance corner of the minimap, frame by frame.

Run with the pilot interpreter: extract.py <recording> <from s> <to s> <out.jsonl> [seconds between reads].
Each row has the time since the first frame, the map displacement speed in pixels per second (None when
the motion check abstains), the minimap reading, the raw recognised strings and a first parse in metres.
"""
import json, re, sys
from collections import deque
from pathlib import Path
import cv2, numpy as np
from pilot.contract import HUD_RECT
from pilot.minimap import read
from pilot.motion import map_motion, map_speed
from pilot.replay import hud_crop

rec = Path(sys.argv[1]); t0, t1 = float(sys.argv[2]), float(sys.argv[3]); out = Path(sys.argv[4])
every = float(sys.argv[5]) if len(sys.argv) > 5 else 0.0
import Quartz, Vision

def ocr(rgb):
    h, w = rgb.shape[:2]
    data = np.ascontiguousarray(rgb).tobytes()
    provider = Quartz.CGDataProviderCreateWithData(None, data, len(data), None)
    image = Quartz.CGImageCreate(w, h, 8, 24, w * 3, Quartz.CGColorSpaceCreateDeviceRGB(), 0, provider, None, False, 0)
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setUsesLanguageCorrection_(False)
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(image, {})
    ok, err = handler.performRequests_error_([req], None)
    return [str(o.topCandidates_(1)[0].string()) for o in (req.results() or ()) if o.topCandidates_(1)]

def metres(texts):
    for text in texts:
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*(km|m)\b", text.replace("O", "0").replace("o", "0"), re.I)
        if m:
            v = float(m.group(1).replace(",", "."))
            return v * 1000 if m.group(2).lower() == "km" else v
    return None

frames = [json.loads(l) for l in (rec / "frames.jsonl").open()]
first = frames[0]["t"]
cap = cv2.VideoCapture(str(rec / "video.mp4"))
hist = deque(); rows = []; last_ocr = -9
for item in frames:
    ok, bgr = cap.read()
    if not ok: break
    t = item["t"] - first
    if t < t0 - 0.5: continue
    if t > t1: break
    crop = hud_crop(bgr)
    while hist and hist[0][0] < t - 0.4: hist.popleft()
    speed = None
    if hist and t - hist[0][0] >= 0.15:
        pt, prev = min(hist, key=lambda it: abs(t - it[0] - 0.2))
        speed = map_speed(map_motion(prev, crop), t - pt)
    hist.append((t, crop.copy()))
    row = {"t": round(t, 3), "map_px_per_s": None if speed is None else round(speed, 2)}
    if t - last_ocr >= every:
        last_ocr = t
        r = read(crop)
        row.update(minimap=r.minimap, route=r.route, corrupt=r.corrupt)
        # the distance sits in the lower left corner of the map; enlarge it for the recogniser
        x, y, w, h = HUD_RECT
        sy, sx = bgr.shape[0] / 720, bgr.shape[1] / 1280
        patch = bgr[round((y + 118) * sy):round((y + 142) * sy), round((x + 36) * sx):round((x + 120) * sx)]
        patch = cv2.cvtColor(cv2.resize(patch, None, fx=5, fy=5, interpolation=cv2.INTER_CUBIC), cv2.COLOR_BGR2RGB)
        texts = ocr(patch)
        row.update(texts=texts, metres=metres(texts))
    rows.append(row)
out.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
print("frames", len(rows), "with a distance", sum(r.get("metres") is not None for r in rows))
