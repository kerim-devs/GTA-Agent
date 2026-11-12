"""zoom.py out.jpg k [k..]  -- 5x enlarged crops with a 10px grid and axis numbers (nearest neighbour)."""
import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools import load
def zoom(ks, path, s=5, cols=2, mask_fn=None):
    crops, _, _ = load()
    H, W = 170 * s + 14, 260 * s + 20
    rows = (len(ks) + cols - 1) // cols
    out = Image.new("RGB", (cols * W, rows * H), (0, 0, 0))
    d = ImageDraw.Draw(out)
    for n, k in enumerate(ks):
        c = np.asarray(crops[k])
        if mask_fn is not None:
            c = mask_fn(c)
        im = Image.fromarray(c).resize((260 * s, 170 * s), Image.NEAREST)
        x0, y0 = (n % cols) * W + 20, (n // cols) * H + 14
        out.paste(im, (x0, y0))
        for x in range(0, 260, 10):
            d.line((x0 + x * s, y0, x0 + x * s, y0 + 170 * s), fill=(255, 0, 255) if x % 50 == 0 else (90, 0, 90), width=1)
            if x % 20 == 0:
                d.text((x0 + x * s + 1, y0 - 12), str(x), fill=(255, 255, 0))
        for y in range(0, 170, 10):
            d.line((x0, y0 + y * s, x0 + 260 * s, y0 + y * s), fill=(255, 0, 255) if y % 50 == 0 else (90, 0, 90), width=1)
            d.text((x0 - 19, y0 + y * s), str(y), fill=(255, 255, 0))
        d.text((x0 + 4, y0 + 4), "k=%d" % k, fill=(0, 255, 0))
    out.save(path, quality=90)
if __name__ == "__main__":
    zoom([int(a) for a in sys.argv[2:]], sys.argv[1])
