"""Geometry sensitivity on held-out recording groups, from the saved feature pairs."""
import json,runpy
from pathlib import Path
import numpy as np
OUT=Path(__file__).resolve().parent
api=runpy.run_path(str(OUT/'p105-map-motion.py'));unproject=api['unproject'];similarity=api['similarity']
data=json.loads((OUT/'p105-motion-points.json').read_text());errors=[];configs=[]
for k in np.arange(.0035,.00901,.0005):
 for aspect in np.arange(.4,.801,.05):
  e=[]
  for row in data:
   a,b=[unproject(np.array(row[key]),k,aspect) for key in ['a','b']]
   z,t,r,rot=similarity(a,b)
   e.append(np.median(r)/np.linalg.norm(t) if np.linalg.norm(t)>2 and len(a)>=20 else np.nan)
  errors.append(e);configs.append((round(float(k),5),round(float(aspect),3)))
errors=np.array(errors);groups=np.array([r['run'] for r in data]);out=[]
for run in sorted(set(groups)):
 train=groups!=run;scores=np.nanmedian(errors[:,train],axis=1);i=int(np.nanargmin(scores));test=errors[i,~train];test=test[np.isfinite(test)]
 out.append(dict(excluded_run=run,tilt=configs[i][0],aspect=configs[i][1],heldout_relative_residual=np.percentile(test,[10,50,90]).tolist() if len(test) else None))
print(json.dumps(out,indent=2));(OUT/'p105-uncertainty.json').write_text(json.dumps(out,indent=2)+'\n')
