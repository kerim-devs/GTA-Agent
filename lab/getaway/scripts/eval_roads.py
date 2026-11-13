"""Road reading against blind labels: eval_roads.py [labels] ; per sector ahead/left/right."""
import json, sys
from common import KEYS, LABELS, WORK
import numpy as np
from pilot import terrain
pick = json.load(open(LABELS / 'label_pick.json'))
items = pick['random_star'] + pick['random_calm'] + pick['sheet']
labels = {}
for line in open(sys.argv[1] if len(sys.argv) > 1 else LABELS / 'road_labels.txt'):
    k, *v = line.split()
    labels[int(k[1:])] = v
cache = {}
stat = {s: [0, 0, 0, 0] for s in ('ahead', 'left', 'right')}  # tp fn fp tn
miss, false, none = [], [], []
frames = 0
for k, v in sorted(labels.items()):
    if v[0] == 'x':
        continue
    frames += 1
    n, i = items[k].split(':')
    if n not in cache:
        cache[n] = np.load(KEYS / f'{n}.npz')
    r = terrain.read(cache[n]['crops'][int(i)])
    if r is None:
        none.append(k)
        continue
    ex = r.exits
    for s, truth in zip(('ahead', 'left', 'right'), v):
        if truth == '?':
            continue
        said = ex[s]
        t = truth == '1'
        idx = 0 if t and said else 1 if t else 2 if said else 3
        stat[s][idx] += 1
        if idx == 1: miss.append(f'L{k:02d}{s[0]}')
        if idx == 2: false.append(f'L{k:02d}{s[0]}')
tp = sum(s[0] for s in stat.values()); fn = sum(s[1] for s in stat.values())
fp = sum(s[2] for s in stat.values()); tn = sum(s[3] for s in stat.values())
print(f'frames {frames}, reading none on {len(none)} {none}')
for s, (a, b, c, d) in stat.items():
    print(f'  {s}: road named {a} of {a+b}, none named {d} of {c+d}')
print(f'all: road named {tp} of {tp+fn} ({tp/max(1,tp+fn):.2f}), none named {tn} of {tn+fp} ({tn/max(1,tn+fp):.2f})')
print('missed', miss)
print('false', false)
