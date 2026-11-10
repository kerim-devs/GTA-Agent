"""Dump minimap crops of a recording as contact sheets: mini.py <recording> <outdir> [every_n]"""
import sys
from pathlib import Path

import av
import numpy as np
from PIL import Image, ImageDraw

rec, out, every = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else 150
X0, Y0, X1, Y1 = 30, 530, 290, 700
SCALE, COLS, ROWS = 2, 6, 4
crops = []
with av.open(str(rec / "video.mp4")) as video:
    for i, frame in enumerate(video.decode(video=0)):
        if i % every:
            continue
        rgb = frame.to_ndarray(format="rgb24")
        crops.append((i, rgb[Y0:Y1, X0:X1].copy()))
w, h = (X1 - X0) * SCALE, (Y1 - Y0) * SCALE
for page in range(0, len(crops), COLS * ROWS):
    sheet = Image.new("RGB", (COLS * w, ROWS * h))
    draw = ImageDraw.Draw(sheet)
    for k, (i, crop) in enumerate(crops[page : page + COLS * ROWS]):
        tile = Image.fromarray(crop).resize((w, h), Image.LANCZOS)
        x, y = (k % COLS) * w, (k // COLS) * h
        sheet.paste(tile, (x, y))
        draw.text((x + 4, y + 4), str(i), fill=(255, 255, 0))
    name = out / f"mini-{page // (COLS * ROWS):02d}.jpg"
    sheet.save(name, quality=85)
    print(name, sheet.size)
print(len(crops), "crops")
