"""Fit the projective distance of complete interior routes; last five arrivals are held out."""
import json
from pathlib import Path
import numpy as np
from collections import defaultdict
OUT=Path(__file__).resolve().parent
rows=json.loads((OUT/'p105-destinations.json').read_text())
# One observation per five seconds limits repeated pictures of the same route.
last={}; samples=[]
for r in rows:
 if r['t']-last.get(r['run'],-100)<5: continue
 last[r['run']]=r['t']; samples.append(r)
# Fit absolute GPS distance including the whole visible path, not its chord.
def length(row,k,ratio):
 p=np.asarray([[0,0],*row['path']]); z=np.maximum(.2,1-k*p[:,1]); q=p*np.array([ratio,1])/z[:,None]
 return np.linalg.norm(np.diff(q,axis=0),axis=1).sum()
train=[r for r in samples if r['run']<'20261114-024431']
for r in samples:r['band']=0 if r['speed']<8 else 1 if r['speed']<16 else 2
best=None
for k in np.arange(0,.00801,.0005):
 for ratio in np.arange(.4,1.11,.05):
  factors=np.asarray([r['distance']/length(r,k,ratio) for r in train]); bands=np.asarray([r['band'] for r in train])
  med=[np.median(factors[bands==b]) for b in range(3)]
  score=np.median(np.abs(np.log(factors/np.take(med,bands))))
  if best is None or score<best[0]: best=score,k,ratio,med
score,k,ratio,med=best
print('FIT',len(train),len(samples),'k',k,'ratio',ratio,'score',score,'medians',med)
for subset, group in [('training',train),('heldout',[r for r in samples if r not in train])]:
 for b in range(3):
  rr=[r for r in group if r['band']==b]; factors=[r['distance']/length(r,k,ratio) for r in rr]
  print(subset,b,len(rr),np.percentile(factors,[0,10,50,90,100]).round(3).tolist() if factors else [])
bins=defaultdict(list)
for r in samples:
 p=np.array(r['path']); x,y=p[-1]; zone='side' if abs(x)>25 else 'near' if y<35 else 'middle' if y<60 else 'far'
 bins[(r['band'],zone)].append(r['distance']/length(r,0,1))
for key,val in sorted(bins.items()): print(key,len(val),np.percentile(val,[10,50,90]).round(3).tolist())
result=dict(k=float(k),ratio=float(ratio),medians=[float(x) for x in med],samples=samples)
(OUT/'p105-fit.json').write_text(json.dumps(result,separators=(',',':'))+'\n')
