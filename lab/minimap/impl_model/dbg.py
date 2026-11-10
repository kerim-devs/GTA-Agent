"""dbg.py module.py out.jpg k...  -- crop | class map with the reader's debug masks and bearings (3x)."""
import sys, math
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(Path(__file__).resolve().parent))
import tools
from msheet import parse
def run(mod, ks, path, s=3, cols=2):
    crops, _, _ = tools.load()
    tiles = []
    for k in ks:
        c = np.asarray(crops[k])
        r = mod.read(c)
        dbg = mod.debug(c) if hasattr(mod, "debug") else {}
        v = (c * 0.4).astype(np.uint8)
        for name, colour in (("weak_y", (150, 110, 0)), ("strong_y", (255, 60, 0)), ("weak_p", (0, 120, 140)), ("strong_p", (60, 90, 255)), ("comp", None), ("damage", None)):
            m = dbg.get(name)
            if m is None: continue
            if name == "comp":
                v[m] = np.maximum(v[m], (0, 200, 0))
            elif name == "damage":
                v[m] = (v[m] * 0.5 + np.array([120, 0, 120])).astype(np.uint8)
            else:
                v[m] = colour
        both = np.concatenate([c, v], 1)
        im = Image.fromarray(both).resize((both.shape[1] * s, both.shape[0] * s), Image.NEAREST)
        d = ImageDraw.Draw(im)
        for off in (0, 260 * s):
            ax, ay = off + 123 * s, 117 * s
            for ang, R, colr in ((r.bearing, 30, (0, 255, 0)), (r.far_bearing, 60, (0, 255, 255))):
                if ang is not None:
                    rad = math.radians(ang)
                    ex, ey = ax + math.sin(rad) * R * s, ay - math.cos(rad) * R * s
                    d.line((ax, ay, ex, ey), fill=colr, width=2); d.ellipse((ex - 4, ey - 4, ex + 4, ey + 4), outline=colr, width=2)
            if r.arrow is not None:
                rad = math.radians(r.arrow)
                d.line((ax, ay, ax + math.sin(rad) * 14 * s, ay - math.cos(rad) * 14 * s), fill=(255, 255, 255), width=2)
        txt = f"{k} {r.minimap} {r.route}{' CORRUPT' if r.corrupt else ''} c={r.confidence:.2f}"
        if r.bearing is not None: txt += f" b={r.bearing:.0f} f={r.far_bearing:.0f}"
        d.rectangle((0, 0, 260 * s * 2, 13), fill=(0, 0, 0)); d.text((3, 1), txt + "  " + str(dbg.get("info", "")), fill=(255, 255, 0))
        tiles.append(np.asarray(im))
    while len(tiles) % cols: tiles.append(np.zeros_like(tiles[0]))
    Image.fromarray(np.concatenate([np.concatenate(tiles[i:i + cols], 1) for i in range(0, len(tiles), cols)], 0)).save(path, quality=85)
if __name__ == "__main__":
    run(tools.load_impl(sys.argv[1]), parse(sys.argv[3:]), sys.argv[2])
