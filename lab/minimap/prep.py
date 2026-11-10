"""Build the minimap dataset from the recordings: crops.npy, meta.json, label sheets, golden.json.
Uses av (never import cv2 in the same process: both bundle FFmpeg)."""
import json
import random
import sys
from pathlib import Path

import av
import numpy as np
from PIL import Image, ImageDraw, ImageFont

RECS = [Path(p) for p in sys.argv[2:]]
OUT = Path(sys.argv[1])
EVERY = 6
X0, Y0, X1, Y1 = 30, 530, 290, 700  # the crop in a 1280x720 frame


def pad_track(rec: Path):
    ts, lx, r2, l2 = [0.0], [0.0], [0.0], [0.0]
    for line in (rec / "pad.jsonl").read_text().splitlines():
        e = json.loads(line)
        if e["src"] != "human":
            continue
        ts.append(e["t"]); lx.append(e["left"][0]); r2.append(e["r2"]); l2.append(e["l2"])
    return np.array(ts), np.array(lx), np.array(r2), np.array(l2)


def window_mean(ts, vals, t0, t1, n=24):
    at = np.linspace(t0, t1, n)
    idx = np.clip(np.searchsorted(ts, at, side="right") - 1, 0, len(vals) - 1)
    return float(vals[idx].mean())


crops, meta = [], []
for rec in RECS:
    times = [json.loads(line)["t"] for line in (rec / "frames.jsonl").read_text().splitlines()]
    ts, lx, r2, l2 = pad_track(rec)
    with av.open(str(rec / "video.mp4")) as video:
        for i, frame in enumerate(video.decode(video=0)):
            if i % EVERY or i >= len(times):
                continue
            rgb = frame.to_ndarray(format="rgb24")
            assert rgb.shape[:2] == (720, 1280), rgb.shape
            crop = rgb[Y0:Y1, X0:X1].copy()
            t = times[i]
            c = crop[28:142, 32:215].astype(np.int32)  # roughly the map itself, without the bars
            r, g, b = c[..., 0], c[..., 1], c[..., 2]
            yellow = int(((r > 190) & (g > 170) & (b < 130) & (r - b > 90)).sum())
            purple = int(((b > 170) & (r > 110) & (g < 140) & (b - g > 60)).sum())
            meta.append({
                "k": len(crops), "rec": rec.name, "i": i, "t": round(t, 3),
                "steer": round(window_mean(ts, lx, t - 0.1, t + 0.5), 3),
                "steer_now": round(window_mean(ts, lx, t - 0.05, t + 0.05), 3),
                "r2": round(window_mean(ts, r2, t - 0.1, t + 0.5), 3),
                "l2": round(window_mean(ts, l2, t - 0.1, t + 0.5), 3),
                "yellow": yellow, "purple": purple,
            })
            crops.append(crop)
    print(rec.name, len(crops), "crops so far", flush=True)

crops = np.stack(crops)
np.save(OUT / "crops.npy", crops)
(OUT / "meta.json").write_text(json.dumps(meta))

# --- golden sample: half with route-coloured pixels, half without, spread over time
rng = random.Random(7)
yel = [m["k"] for m in meta if m["yellow"] >= 25]
pur = [m["k"] for m in meta if m["purple"] >= 25 and m["yellow"] < 25]
rest = [m["k"] for m in meta if m["yellow"] < 25 and m["purple"] < 25]
pick = rng.sample(yel, min(66, len(yel))) + rng.sample(pur, min(24, len(pur)))
pick += rng.sample(rest, 168 - len(pick))
rng.shuffle(pick)
print("strata", len(yel), len(pur), len(rest), "picked", len(pick))

SCALE, COLS, ROWS = 3, 4, 3
w, h = (X1 - X0) * SCALE, (Y1 - Y0) * SCALE
try:
    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 34)
except OSError:
    font = ImageFont.load_default()
golden = []
for s in range(0, len(pick), COLS * ROWS):
    name = f"G{s // (COLS * ROWS):02d}"
    sheet = Image.new("RGB", (COLS * w, ROWS * h))
    draw = ImageDraw.Draw(sheet)
    for n, k in enumerate(pick[s : s + COLS * ROWS]):
        tile = Image.fromarray(crops[k]).resize((w, h), Image.LANCZOS)
        x, y = (n % COLS) * w, (n // COLS) * h
        sheet.paste(tile, (x, y))
        draw.rectangle((x, y, x + w - 1, y + h - 1), outline=(255, 0, 255), width=2)
        draw.rectangle((x + 2, y + 2, x + 58, y + 44), fill=(0, 0, 0))
        draw.text((x + 8, y + 4), str(n + 1), fill=(255, 255, 0), font=font)
        golden.append({"id": f"{name}-{n + 1:02d}", "sheet": f"{name}.jpg", "tile": n + 1, "k": k,
                       "split": "dev" if (s // (COLS * ROWS)) % 7 not in (2, 5) else "held"})
    sheet.save(OUT / "sheets" / f"{name}.jpg", quality=90)
(OUT / "golden.json").write_text(json.dumps(golden, indent=1))
print("sheets", len(pick) // (COLS * ROWS), "dev", sum(g["split"] == "dev" for g in golden),
      "held", sum(g["split"] == "held" for g in golden), "crops", crops.shape)
