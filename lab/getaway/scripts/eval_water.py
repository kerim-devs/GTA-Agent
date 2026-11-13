import sys,json; from common import KEYS, LABELS, WORK
import numpy as np
from pilot import terrain
labels=json.load(open(sys.argv[1] if len(sys.argv)>1 else LABELS / 'labels_water.json'))
cache={}
tp=fn=fp=tn=0; misses=[]; fps=[]; abst=0
for l in labels:
    if l['aircraft'] or l['uncertain']: continue
    n,i=l['frame'].split(':')
    if n not in cache: cache[n]=np.load(KEYS / f'{n}.npz')
    r=terrain.read(cache[n]['crops'][int(i)])
    said = r is not None and 'ahead' in r.water_sides
    truth='ahead' in l['water']
    if r is None: abst+=1
    if truth and said: tp+=1
    elif truth: fn+=1; misses.append(l['id'])
    elif said: fp+=1; fps.append(l['id'])
    else: tn+=1
print(f'water ahead: {tp} of {tp+fn} found, missed {misses}; false alarms {fp} of {fp+tn} {fps}; abstentions {abst}')
