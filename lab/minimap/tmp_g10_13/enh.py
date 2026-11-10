import sys
sys.path.insert(0, 'tmp_g10_13')
from view import tile
from PIL import Image, ImageOps
import numpy as np
s = sys.argv[1]
g = float(sys.argv[2])
for n in sys.argv[3:]:
    n = int(n)
    t = tile(s, n)
    a = np.asarray(t).astype(float) / 255.0
    a = a ** g
    e = Image.fromarray((a * 255).clip(0, 255).astype('uint8'))
    e = ImageOps.autocontrast(e, cutoff=1)
    e = e.resize((t.size[0] * 2, t.size[1] * 2), Image.LANCZOS)
    p = 'tmp_g10_13/enh_%s_%02d.jpg' % (s, n)
    e.save(p, quality=92)
    print(p)
