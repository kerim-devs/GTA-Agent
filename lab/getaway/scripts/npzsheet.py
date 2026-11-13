"""npzsheet.py <out-prefix> <npz> [...]: sheets of 12 crops, labelled F<n>, with the water mask beside when --mask."""
import sys, math
import common  # noqa: F401  (pilot on the path)
import numpy as np, cv2
args = sys.argv[1:]
mask = '--mask' in args; foot = '--foot' in args; args = [a for a in args if a not in ('--mask', '--foot')]
prefix, files = args[0], args[1:]
crops = np.concatenate([np.load(f)['crops'] for f in files])
if mask:
    from pilot import terrain
cells = []
for n, c in enumerate(crops):
    big = cv2.resize(cv2.cvtColor(c, cv2.COLOR_RGB2BGR), (390, 255), interpolation=cv2.INTER_CUBIC)
    if mask:
        m = terrain.water_mask(c, on_foot=foot)
        if m is None:
            cv2.putText(big, 'NONE', (300, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
        else:
            tint = big.copy(); tint[cv2.resize(m.astype(np.uint8), (390, 255), interpolation=cv2.INTER_NEAREST) > 0] = (255, 100, 0)
            big = cv2.addWeighted(big, 0.5, tint, 0.5, 0)
    cv2.rectangle(big, (0, 0), (50, 18), (0, 0, 0), -1)
    cv2.putText(big, f'F{n:02d}', (3, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    cells.append(big)
for s in range(0, len(cells), 12):
    g = cells[s:s + 12]
    while len(g) < 12: g.append(np.zeros_like(cells[0]))
    cv2.imwrite(f'{prefix}-{s // 12:02d}.jpg', np.vstack([np.hstack(g[i:i + 3]) for i in range(0, 12, 3)]), [cv2.IMWRITE_JPEG_QUALITY, 85])
print(len(cells))
