import sys
sys.path.insert(0, 'tmp_g10_13')
from view import tile
from PIL import Image
# usage: zoom.py SHEET N x0 y0 x1 y1 Z
s = sys.argv[1]; n = int(sys.argv[2])
x0, y0, x1, y1 = map(int, sys.argv[3:7]); z = int(sys.argv[7])
t = tile(s, n).crop((x0, y0, x1, y1))
t = t.resize((t.size[0] * z, t.size[1] * z), Image.LANCZOS)
p = 'tmp_g10_13/zoom_%s_%02d.jpg' % (s, n)
t.save(p, quality=93)
print(p, t.size)
