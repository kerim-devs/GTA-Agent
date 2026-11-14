"""Compact evidence index for the P105 handoff."""
import json
from collections import Counter
from pathlib import Path
import numpy as np
OUT=Path(__file__).resolve().parent
cal=json.loads((OUT/'p105-calibration.json').read_text())
for b in ['0','1','2']:
 r=cal[b];print('CAL',b,'n',r['n'],'clips',r['clips'],'base',np.round(r['base_quantiles'],3).tolist())
 for zone in ['near','middle','far','side']:print('ZONE',b,zone,'long/lat p10,p50,p90',np.round(r[zone]['forward'],2).tolist(),np.round(r[zone]['sideways'],2).tolist())
rep=json.loads((OUT/'p105-replay.json').read_text());counts=Counter()
for run,r in rep.items():
 print('REPLAY',run)
 for label in ['before','after']:print(label,r[label]['reason_share'],'limits',r[label]['limit_quantiles'])
 for j in r.get('junctions',[]):
  counts[j['status']]+=1
  print('JUNCTION',run,round(j['start'],2),round(j['end'],2),j['status'],'error',j.get('error_m'))
  for label in ['before','after']:
   if j.get(label):print(label,j[label])
print('JUNCTION COUNT',dict(counts))
sim=json.loads((OUT/'p105-simulator.json').read_text())
for label in ['before-affine','before-tilted','after-tilted']:
 for road in ['town-1','town-2','kilometre','bend-60','bend-120','exit']:
  rows=[r for r in sim if r['variant']==label and r['road']==road]
  print('SIM',label,road,'pass',sum(r['bounds_pass'] for r in rows),'maxerr',max(r['max_error'] for r in rows),'entries',max((max(r['entries']) for r in rows if r['entries']),default=None),'time median',float(np.median([r['time'] for r in rows])))
