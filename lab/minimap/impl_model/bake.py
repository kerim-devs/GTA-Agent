"""bake.py: write the learnt parameters (lut.npy, tilt_w.npy, arrow parameters) into minimap.py as constants."""
import base64, re, zlib, json
from pathlib import Path
import numpy as np
here = Path(__file__).resolve().parent
src = (here / "minimap.py").read_text()
lut = np.load(here / "lut.npy").astype(np.uint8)
z = base64.b64encode(zlib.compress(lut.tobytes(), 9)).decode()
lines = ['_LUT_Z = (']
for i in range(0, len(z), 100):
    lines.append('    "%s"' % z[i:i + 100])
lines.append(')')
tw = np.load(here / "tilt_w.npy") if (here / "tilt_w.npy").exists() else np.zeros(0)
lines.append("_TILT_W = (" + ", ".join("%.5f" % v for v in tw) + ("," if len(tw) == 1 else "") + ")")
arrow = json.loads((here / "arrow.json").read_text()) if (here / "arrow.json").exists() else dict(tip=5.2, bx=3.4, by=3.2, notch=1.8, ow=1.0, cy=-0.5)
lines.append("_ARROW = dict(" + ", ".join(f"{k}={v}" for k, v in arrow.items()) + ")")
block = "# BAKED-BEGIN\n" + "\n".join(lines) + "\n# BAKED-END"
src = re.sub(r"# BAKED-BEGIN.*?# BAKED-END", lambda m: block, src, flags=re.S)
(here / "minimap.py").write_text(src)
print("baked: LUT %d bytes compressed to %d chars, %d tilt weights" % (lut.size, len(z), len(tw)))
