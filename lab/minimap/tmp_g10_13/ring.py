"""Aid only: where do route-coloured pixels sit on the two circles? usage: ring.py SHEET N[:cx:cy] ..."""
import sys, math
sys.path.insert(0, 'tmp_g10_13')
from view import tile
import numpy as np

def mask(a):
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    yel = (r > 170) & (g > 170) & (b < 150) & (r - b > 70) & (abs(r - g) < 60)
    pur = (b - g > 35) & (b > 150) & (r > g + 5)
    return yel, pur

s = sys.argv[1]
for spec in sys.argv[2:]:
    p = spec.split(':'); n = int(p[0])
    cx = int(p[1]) if len(p) > 1 else 370
    cy = int(p[2]) if len(p) > 2 else 350
    a = np.asarray(tile(s, n)).astype(int)
    H, W = a.shape[:2]
    yel, pur = mask(a)
    R = 90.0
    for name, m in (('yellow', yel), ('purple', pur)):
        tot = int(m[cy-200:cy+90, cx-230:cx+230].sum())
        if tot < 150:
            continue
        print('%s-%02d %s total px near map: %d' % (s, n, name, tot))
        for k in (1, 2):
            hits = {}
            for deg in range(0, 360, 2):
                t = math.radians(deg)
                c = 0
                for rr in np.arange(R*k-4, R*k+4.1, 1.0):
                    x = int(round(cx + rr*math.sin(t))); y = int(round(cy - rr*math.cos(t)))
                    if 0 <= x < W and 0 <= y < H and m[y, x]:
                        c += 1
                if c >= 3:
                    hits[deg] = c
            # group contiguous
            groups = []
            for d in sorted(hits):
                if groups and d - groups[-1][-1] <= 4:
                    groups[-1].append(d)
                else:
                    groups.append([d])
            out = []
            for g in groups:
                mid = (g[0] + g[-1]) / 2.0
                out.append('%d..%d deg (mid %.0f = %.2fh)' % (g[0], g[-1], mid, (mid/30.0) if mid/30.0 >= 0.25 else 12 + mid/30.0))
            print('   circle x%d:' % k, '; '.join(out) if out else 'none')
