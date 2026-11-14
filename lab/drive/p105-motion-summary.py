"""Aggregate texture motion over contiguous intervals before using quantized GPS metres."""
import json
from collections import defaultdict
from pathlib import Path
import numpy as np
OUT=Path(__file__).resolve().parent
source=json.loads((OUT/'p105-motion.json').read_text())
rows=source['rows'];clips=[];current=[]
for r in rows:
 good=(all(r[key] is not None for key in ('d0','d1','age0','age1','speed0','speed1')) and r['n']>=20 and r['residual']<1 and r['residual']/max(1,r['translation'])<.25)
 if current and (not good or r['run']!=current[-1]['run'] or abs(r['t0']-current[-1]['t1'])>.1):
  clips.append(current);current=[]
 if good:current.append(r)
if current:clips.append(current)
samples=[];valid=[]
for clip in clips:
 # Only use an endpoint with a fresh fix. Discard timing correction where speed is absent.
 while clip and (clip[0]['d0'] is None or clip[0]['speed0'] is None or clip[0]['age0'] is None):clip=clip[1:]
 while clip and (clip[-1]['d1'] is None or clip[-1]['speed1'] is None or clip[-1]['age1'] is None):clip=clip[:-1]
 if len(clip)<3:continue
 first,last=clip[0],clip[-1];dm=first['d0']-last['d1']-first['age0']*first['speed0']+last['age1']*last['speed1']
 if dm<15:continue
 zoom=1.;trans=0.;scales=[]
 for r in clip:
  zoom*=r['zoom'];trans+=r['translation']/zoom;scales.append(zoom)
 base=dm/trans
 entry=dict(run=first['run'],start=first['t0'],end=last['t1'],metres=dm,base=base,n=len(clip))
 valid.append(entry)
 for r,zoom in zip(clip,scales):
  if r['speed1'] is None:continue
  samples.append(dict(run=r['run'],t=r['t1'],speed=r['speed1'],base=base/zoom,zoom=r['zoom'],clip=len(valid)-1))
summary=dict(tilt=source['tilt'],horizontal_ratio=source['ratio'],clips=valid)
for band,(lo,hi) in enumerate(((0,8),(8,16),(16,100))):
 group=[s for s in samples if lo<=s['speed']<hi]
 values=np.array([s['base'] for s in group]);summary[str(band)]=dict(n=len(group),clips=len({s['clip'] for s in group}),base_quantiles=np.percentile(values,[0,10,50,90,100]).tolist())
 for zone,x,y in [('near',0,20),('middle',0,45),('far',0,75),('side',50,30)]:
  k,ratio=source['tilt'],source['ratio'];z=1-k*y
  # Directional Jacobian: longitudinal street and transverse street are not interchangeable.
  forward=values*np.hypot(ratio*k*x,1)/z**2;sideways=values*ratio/z
  summary[str(band)][zone]=dict(forward=np.percentile(forward,[10,50,90]).tolist(),sideways=np.percentile(sideways,[10,50,90]).tolist())
summary['samples']=samples
(OUT/'p105-calibration.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps({k:v for k,v in summary.items() if k!='samples'},indent=2))
