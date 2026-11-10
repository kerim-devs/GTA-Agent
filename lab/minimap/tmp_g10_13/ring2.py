"""Aid only: weighted mean bearing of route-coloured pixels inside an annulus, per angular cluster.
usage: ring2.py SHEET N colour(y|p) k [cx cy] [loose]"""
import sys, math
sys.path.insert(0, 'tmp_g10_13')
from view import tile
import numpy as np
s = sys.argv[1]; n = int(sys.argv[2]); col = sys.argv[3]; k = float(sys.argv[4])
cx = int(sys.argv[5]) if len(sys.argv) > 5 else 369
cy = int(sys.argv[6]) if len(sys.argv) > 6 else 351
loose = len(sys.argv) > 7
a = np.asarray(tile(s, n)).astype(int)
H, W = a.shape[:2]
r, g, b = a[..., 0], a[..., 1], a[..., 2]
if col == 'y':
    if loose:
        m = (r > 150) & (g > 150) & (np.minimum(r, g) - b > 40)
    else:
        m = (r > 170) & (g > 170) & (b < 150) & (r - b > 70) & (abs(r - g) < 60)
else:
    if loose:
        m = (b - g > 22) & (r > g)
    else:
        m = (b - g > 35) & (b > 150) & (r > g + 5)
R = 90.0 * k
yy, xx = np.mgrid[0:H, 0:W]
d = np.hypot(xx - cx, yy - cy)
ann = m & (d >= R - 3) & (d <= R + 3) & (yy < cy + 60)
ys, xs = np.nonzero(ann)
ang = np.degrees(np.arctan2(xs - cx, -(ys - cy)))
order = np.argsort(ang)
ang = ang[order]
if len(ang) == 0:
    print('%s-%02d %s x%g: nothing' % (s, n, col, k)); sys.exit()
groups = [[ang[0]]]
for v in ang[1:]:
    if v - groups[-1][-1] > 5:
        groups.append([v])
    else:
        groups[-1].append(v)
for gset in groups:
    if len(gset) < 8:
        continue
    mean = float(np.mean(gset)); med = float(np.median(gset))
    h = (mean % 360) / 30.0
    print('%s-%02d %s x%g: %4d px  %.0f..%.0f deg  mean %.1f  median %.1f  => %.2fh' % (s, n, col, k, len(gset), gset[0], gset[-1], mean, med, h if h >= 0.25 else h + 12))
