"""Harvest route / non-route pixels from the dev tiles using the tile labels and a loose seed rule.
Positives: loose-colour pixels inside the map rectangle whose connected component reaches the arrow
neighbourhood, in tiles labelled with that route colour.  Negatives: every map pixel of tiles labelled
route none, and in route tiles everything further than 3 px from any loose-colour pixel."""
import sys
from pathlib import Path
import numpy as np, cv2
sys.path.insert(0, str(Path(__file__).resolve().parent))
from devlabels import dev
X0, X1, Y0, Y1 = 34, 214, 28, 142   # map rectangle, half-open
AX, AY = 123, 117

def loose(c, colour):
    r, g, b = [c[..., i].astype(np.int16) for i in range(3)]
    if colour == "yellow":
        return (r > 150) & (g > 150) & (np.minimum(r, g) - b > 40) & (np.abs(r - g) < 50)
    return (b - g > 30) & (r - g > 5) & (b > 120) & (b - r > -30)

def route_mask(c, colour, reach=16):
    m = np.zeros(c.shape[:2], np.uint8)
    m[Y0:Y1, X0:X1] = loose(c, colour)[Y0:Y1, X0:X1]
    n, lab, stats, cent = cv2.connectedComponentsWithStats(m, connectivity=8)
    yy, xx = np.mgrid[:170, :260]
    near = (xx - AX) ** 2 + (yy - AY) ** 2 <= reach ** 2
    keep = np.zeros_like(m, bool)
    for i in range(1, n):
        comp = lab == i
        if stats[i, cv2.CC_STAT_AREA] >= 25 and (comp & near).any():
            keep |= comp
    return keep, m.astype(bool)

if __name__ == "__main__":
    from PIL import Image
    crops, meta, labs = dev()
    for colour in ("yellow", "purple"):
        ks = [l["k"] for l in labs if l["route"] == colour]
        tiles = []
        for k in ks:
            c = np.asarray(crops[k]).copy()
            keep, m = route_mask(c, colour)
            v = c.copy()
            v[m & ~keep] = (0, 255, 255)
            v[keep] = (255, 0, 0)
            both = np.concatenate([c, v], 1)
            tiles.append(np.asarray(Image.fromarray(both).resize((both.shape[1] * 2, both.shape[0] * 2), Image.NEAREST)))
            print(colour, k, int(keep.sum()), int(m.sum()))
        rows = [np.concatenate(tiles[i:i + 2], 1) for i in range(0, len(tiles) - 1, 2)]
        Image.fromarray(np.concatenate(rows, 0)).save(f"impl_model/look/harvest_{colour}.jpg", quality=88)
