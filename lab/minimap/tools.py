"""Shared helpers: load the data, render enlarged tiles with an optional overlay of a reader's output.

  .venv/bin/python tools.py sheet out.jpg 12 400 1933            # tiles of crops 12, 400, 1933
  .venv/bin/python tools.py overlay impl_x/minimap.py out.jpg 12 400 1933

Never import `av` in a process that imports `cv2` (both bundle FFmpeg and crash each other).
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from contract import ARROW_XY, FAR_R, NEAR_R  # noqa: E402


def load():
    """crops (N x 170 x 260 x 3 uint8, memory-mapped), meta (list of dicts, index = k), golden (list)."""
    crops = np.load(ROOT / "data" / "crops.npy", mmap_mode="r")
    meta = json.loads((ROOT / "data" / "meta.json").read_text())
    golden = json.loads((ROOT / "data" / "golden.json").read_text())
    return crops, meta, golden


def load_impl(path: str):
    spec = importlib.util.spec_from_file_location("impl_" + Path(path).parent.name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _font(size: int):
    try:
        return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)
    except OSError:
        return ImageFont.load_default()


def sheet(indices, path, read=None, scale: int = 3, cols: int = 4) -> None:
    """Tiles of the crops `indices`, `scale` times enlarged, each tagged with its k. With `read`
    (a reader's function) its output is drawn on top: near bearing green, far bearing cyan, arrow white."""
    crops, _, _ = load()
    h, w = crops.shape[1] * scale, crops.shape[2] * scale
    rows = (len(indices) + cols - 1) // cols
    out = Image.new("RGB", (cols * w, rows * h))
    draw = ImageDraw.Draw(out)
    font, small = _font(24), _font(20)
    for n, k in enumerate(indices):
        crop = np.asarray(crops[k])
        x, y = (n % cols) * w, (n // cols) * h
        out.paste(Image.fromarray(crop).resize((w, h), Image.LANCZOS), (x, y))
        draw.rectangle((x, y, x + w - 1, y + h - 1), outline=(255, 0, 255), width=2)
        draw.rectangle((x + 2, y + 2, x + 92, y + 32), fill=(0, 0, 0))
        draw.text((x + 6, y + 4), str(k), fill=(255, 255, 0), font=font)
        if read is None:
            continue
        r = read(crop)
        ax, ay = x + ARROW_XY[0] * scale, y + ARROW_XY[1] * scale
        for angle, radius, colour in ((r.bearing, NEAR_R, (0, 255, 0)), (r.far_bearing, FAR_R, (0, 255, 255))):
            if angle is not None:
                rad = math.radians(angle)
                ex, ey = ax + math.sin(rad) * radius * scale, ay - math.cos(rad) * radius * scale
                draw.line((ax, ay, ex, ey), fill=colour, width=3)
                draw.ellipse((ex - 5, ey - 5, ex + 5, ey + 5), outline=colour, width=2)
        if r.arrow is not None:
            rad = math.radians(r.arrow)
            draw.line((ax, ay, ax + math.sin(rad) * 14 * scale, ay - math.cos(rad) * 14 * scale),
                      fill=(255, 255, 255), width=2)
        text = f"{r.minimap} {r.route}" + (" CORRUPT" if r.corrupt else "") + f" c={r.confidence:.2f}"
        if r.bearing is not None:
            text += f" b={r.bearing:.0f}"
        draw.rectangle((x + 2, y + h - 28, x + w - 3, y + h - 3), fill=(0, 0, 0))
        draw.text((x + 6, y + h - 27), text, fill=(255, 255, 255), font=small)
    out.save(path, quality=88)


if __name__ == "__main__":
    if sys.argv[1] == "sheet":
        sheet([int(a) for a in sys.argv[3:]], sys.argv[2])
    elif sys.argv[1] == "overlay":
        sheet([int(a) for a in sys.argv[4:]], sys.argv[3], load_impl(sys.argv[2]).read)
    else:
        sys.exit(__doc__)
