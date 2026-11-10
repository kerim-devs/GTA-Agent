"""Aid only: colour profile along a circle. usage: prof.py SHEET N K deg0 deg1 [cx cy]"""
import sys, math
sys.path.insert(0, 'tmp_g10_13')
from view import tile
import numpy as np
s = sys.argv[1]; n = int(sys.argv[2]); k = float(sys.argv[3]); d0 = int(sys.argv[4]); d1 = int(sys.argv[5])
cx = int(sys.argv[6]) if len(sys.argv) > 6 else 370
cy = int(sys.argv[7]) if len(sys.argv) > 7 else 350
a = np.asarray(tile(s, n)).astype(int)
H, W = a.shape[:2]
R = 90.0 * k
for deg in range(d0, d1 + 1, 2):
    t = math.radians(deg)
    px = []
    for rr in np.arange(R - 3, R + 3.1, 1.0):
        x = int(round(cx + rr * math.sin(t))); y = int(round(cy - rr * math.cos(t)))
        if 0 <= x < W and 0 <= y < H:
            px.append(a[y, x])
    if not px:
        continue
    m = np.mean(px, 0)
    r, g, b = m
    tag = ''
    if r > 150 and g > 150 and (min(r, g) - b) > 45:
        tag = 'YELLOWISH'
    if b - g > 25 and r > g:
        tag = 'PURPLISH'
    print('%4d deg (%5.2fh)  rgb %3d %3d %3d  %s' % (deg, (deg % 360) / 30.0, r, g, b, tag))
