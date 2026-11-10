"""viewcls.py out.jpg k...: crop next to its class map (yellow strong = red, yellow weak = orange, purple strong = blue, purple weak = cyan)."""
import sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools import load
from train import idx
def view(ks, path, lut, s=2, cols=3):
    crops, _, _ = load()
    tiles = []
    for k in ks:
        c = np.asarray(crops[k])
        cls = lut[idx(c)]
        v = (c * 0.35).astype(np.uint8)
        v[cls == 1] = (255, 160, 0); v[cls == 2] = (255, 0, 0); v[cls == 3] = (0, 255, 255); v[cls == 4] = (40, 80, 255)
        both = np.concatenate([c, v], 1)
        im = Image.fromarray(both).resize((both.shape[1] * s, both.shape[0] * s), Image.NEAREST)
        ImageDraw.Draw(im).text((4, 4), str(k), fill=(0, 255, 0))
        tiles.append(np.asarray(im))
    while len(tiles) % cols: tiles.append(np.zeros_like(tiles[0]))
    Image.fromarray(np.concatenate([np.concatenate(tiles[i:i + cols], 1) for i in range(0, len(tiles), cols)], 0)).save(path, quality=85)
if __name__ == "__main__":
    view([int(a) for a in sys.argv[2:]], sys.argv[1], np.load("impl_model/lut.npy"))
