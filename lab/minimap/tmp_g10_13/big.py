import sys
sys.path.insert(0, 'tmp_g10_13')
from view import tile
from PIL import Image
s = sys.argv[1]
for n in sys.argv[2:]:
    n = int(n)
    t = tile(s, n)
    t = t.resize((t.size[0] * 2, t.size[1] * 2), Image.LANCZOS)
    p = 'tmp_g10_13/big_%s_%02d.jpg' % (s, n)
    t.save(p, quality=92)
    print(p)
