"""arrowzoom.py out.jpg k...: 14x zoom of the arrow neighbourhood (x 108..138, y 102..132)."""
import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools import load
def run(ks, path, s=14, cols=6, x0=108, y0=102, n=31):
    crops, _, _ = load()
    tiles = []
    for k in ks:
        c = np.asarray(crops[k])[y0:y0 + n, x0:x0 + n]
        im = Image.fromarray(c).resize((n * s, n * s), Image.NEAREST)
        d = ImageDraw.Draw(im)
        cx, cy = (123 - x0) * s + s // 2, (117 - y0) * s + s // 2
        d.line((cx - 5, cy, cx + 5, cy), fill=(255, 0, 0)); d.line((cx, cy - 5, cx, cy + 5), fill=(255, 0, 0))
        d.text((3, 3), str(k), fill=(0, 255, 0))
        tiles.append(np.asarray(im))
    while len(tiles) % cols: tiles.append(np.zeros_like(tiles[0]))
    Image.fromarray(np.concatenate([np.concatenate(tiles[i:i + cols], 1) for i in range(0, len(tiles), cols)], 0)).save(path, quality=90)
if __name__ == "__main__":
    run([int(a) for a in sys.argv[2:]], sys.argv[1])
