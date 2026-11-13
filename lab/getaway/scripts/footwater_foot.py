"""Water share on every on-foot key frame, one recording at a time, waiting while the console is busy."""
import sys, glob, json, os, time
from pathlib import Path
from common import KEYS, WORK, wait_while_busy
import numpy as np
from pilot import terrain
out = {}
for f in sorted(glob.glob(str(KEYS / '*.npz'))):
    wait_while_busy()
    d = np.load(f); name = Path(f).stem
    sel = [i for i in range(len(d['t'])) if d['map'][i] == 'flat' and d['screen'][i] == 'game' and not d['corrupt'][i]]
    crops = d['crops']
    for i in sel:
        m = terrain.water_mask(crops[i], on_foot=True)
        out[f'{name}:{i}'] = None if m is None else round(float(m[terrain._INSIDE].mean()), 3)
json.dump(out, open(WORK / 'footwater_foot.json', 'w'))
v = [x for x in out.values() if x is not None]
print(len(out), sum(1 for x in out.values() if x is None), sum(1 for x in v if x >= 0.02), sum(1 for x in v if x >= 0.2))
