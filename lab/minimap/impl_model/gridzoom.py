"""gridzoom.py out.jpg k...: 4x zoom with the 16-px macroblock grid (crop x = 2 mod 16, y = 14 mod 16)."""
import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools import load
def run(ks, path, s=4, cols=3):
    crops, _, _ = load()
    tiles = []
    for k in ks:
        im = Image.fromarray(np.asarray(crops[k])).resize((260 * s, 170 * s), Image.NEAREST)
        d = ImageDraw.Draw(im)
        for x in range(2, 260, 16): d.line((x * s, 0, x * s, 170 * s), fill=(255, 0, 255))
        for y in range(14, 170, 16): d.line((0, y * s, 260 * s, y * s), fill=(255, 0, 255))
        d.text((3, 3), str(k), fill=(0, 255, 0))
        tiles.append(np.asarray(im))
    while len(tiles) % cols: tiles.append(np.zeros_like(tiles[0]))
    Image.fromarray(np.concatenate([np.concatenate(tiles[i:i + cols], 1) for i in range(0, len(tiles), cols)], 0)).save(path, quality=88)
if __name__ == "__main__":
    run([int(a) for a in sys.argv[2:]], sys.argv[1])
