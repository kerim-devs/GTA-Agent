"""Check interior route termini against the printed destination distance."""
import json
from collections import defaultdict
from pathlib import Path
import cv2
import numpy as np
from pilot.replay import hud_crop

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'lab/drive'
samples=[]; pictures=[]
for run in sorted(Path('/Users/kerim/recordings/pilot').glob('20261114-*')):
 if run.name > '20261114-025645' or not (run/'play.jsonl').exists(): continue
 rows=[]; last=-1
 for line in (run/'play.jsonl').open():
  r=json.loads(line); rd=r.get('reading') or {}; p=rd.get('path') or []; d=rd.get('gps_distance'); sk=r.get('skill') or {}
  if sk.get('name')!='drive_route' or not p or d is None or rd.get('corrupt') or not 20<=d<=240 or rd.get('gps_speed') is None: continue
  if max(abs(q[0]) for q in p)>76 or max(q[1] for q in p)>78 or min(q[1] for q in p)<-8: continue
  if r['t']-last<1: continue
  last=r['t']; rows.append(r)
 if not rows: continue
 samples.extend(dict(run=run.name,t=r['t'],distance=r['reading']['gps_distance'],speed=r['reading']['gps_speed'],path=r['reading']['path'], frame_id=r['frame_id']) for r in rows)
 if run.name[-6:] in ['024431','024817','025007','025345','025645']:
  frames={f['frame_id']:f for f in map(json.loads,(run/'frames.jsonl').open())}
  cap=cv2.VideoCapture(str(run/'video.mp4'))
  for r in rows[::max(1,len(rows)//3)][:3]:
   cap.set(cv2.CAP_PROP_POS_FRAMES,frames[r['frame_id']]['i']); ok,bgr=cap.read()
   if ok:
    crop=cv2.cvtColor(hud_crop(bgr),cv2.COLOR_RGB2BGR)
    cv2.putText(crop,f"{run.name[-6:]} {r['t']:.1f}s {r['reading']['gps_distance']:.0f}m",(3,13),cv2.FONT_HERSHEY_SIMPLEX,.38,(0,255,255),1)
    pictures.append(crop)
  cap.release()
while len(pictures)%3: pictures.append(np.zeros_like(pictures[0]))
cv2.imwrite(str(OUT/'p105-destinations.jpg'),np.concatenate([np.concatenate(pictures[i:i+3],axis=1) for i in range(0,len(pictures),3)]))
(OUT/'p105-destinations.json').write_text(json.dumps(samples,separators=(',',':'))+'\n')
print('samples',len(samples),'runs',len({s['run'] for s in samples}))
