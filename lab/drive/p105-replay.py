"""P105 paired open-loop replay; it cannot predict new trip times or new entry speeds."""
import csv,gzip,json
from collections import Counter
from math import hypot,sqrt
from pathlib import Path
from statistics import median
import numpy as np
from p98_replay import baseline
from pilot.cli import drive_config
from pilot.contract import Reading
from pilot.drive import Driver
OUT=Path(__file__).resolve().parent
RUNS=['024431','024817','025007','025345','025645','005357']


def replay(cls,cfg,source):
 driver=cls(cfg);previous=None;attempt=None;out=[]
 for row in source:
  sk=row.get('skill') or {};rd=row.get('reading') or {}
  if sk.get('name')!='drive_route':previous=None;continue
  if previous is None or row['t']-previous>2 or sk.get('attempt_id')!=attempt:
   driver=cls(cfg)
  dt=0 if previous is None else max(0,min(.1,row['t']-previous))
  previous=row['t'];attempt=sk.get('attempt_id')
  speed=rd.get('gps_speed');path=rd.get('path') or []
  driver._turn_remaining-=(speed if speed is not None else 4)*dt
  if driver._turn_remaining<=0:driver._turn_limit=None
  driver._road_heading=rd.get('arrow') or 0
  limit=None
  if rd.get('minimap')=='tilted' and len(path)>=3 and not rd.get('corrupt'):
   limit=driver._speed_limit(path,0,speed)
   reason=driver.speed_reason
  else:reason='unusable-picture'
  out.append(dict(t=row['t'],speed=speed,distance=rd.get('gps_distance'),
                  limit=limit,reason=reason,attempt=attempt,brake=None))
 return out


def summary(rows):
 reasons=Counter(r['reason'] for r in rows);limits=[r['limit'] for r in rows if r['limit'] is not None]
 return dict(ticks=len(rows),reason_share={k:round(v/len(rows),4) for k,v in sorted(reasons.items())},
             limit_quantiles=np.percentile(limits,[10,50,90]).round(3).tolist(),
             below_recorded_speed=sum(r['limit'] is not None and r['speed'] is not None and r['limit']<r['speed'] for r in rows))


def junctions(run,source,before,after):
 # Cluster the independently fitted corner tracks; a gap or speed change is not a new junction.
 tracks=json.loads((OUT/'p105-tracks.json').read_text()); groups=[]
 for tr in tracks:
  if not tr['run'].endswith(run):continue
  r=tr['rows'];key=r[0]['turn']>0
  if groups and r[0]['t']-groups[-1][-1]['t']<5 and (groups[-1][-1]['turn']>0)==key:
   groups[-1].extend(r)
  else:groups.append(r.copy())
 results=[]
 for group in groups:
  if len(group)<5:continue
  # A GPS intercept from the closest visible 12-35 px approach, independent of the chosen law.
  close=[r for r in group if 12<=hypot(r['x'],r['y'])<=35 and abs(r['x'])<15]
  if len(close)<4 or max(r['distance'] for r in close)-min(r['distance'] for r in close)<8:
   results.append(dict(start=group[0]['t'],end=group[-1]['t'],status='unresolved passage',samples=len(group)))
   continue
  ys=np.array([r['y'] for r in close]);ds=np.array([r['distance'] for r in close]);slopes=[]
  for i in range(len(close)):
   for j in range(i+1,len(close)):
    if abs(ys[i]-ys[j])>=5:
     slopes.append((ds[i]-ds[j])/(ys[i]-ys[j]))
  if not slopes:continue
  scale=float(np.median(slopes))
  if not .5<scale<5:
   results.append(dict(start=group[0]['t'],end=group[-1]['t'],status='unstable GPS intercept',samples=len(group)));continue
  end_distance=float(np.median(ds-scale*ys));scatter=float(np.median(abs(ds-(end_distance+scale*ys))))
  # Extrapolation under the arrow adds 10 m to residual and GPS quantum; no invented exact crossing.
  error=10+2*scatter+max(r['quantum'] for r in close)
  result=dict(start=group[0]['t'],end=group[-1]['t'],status='GPS-intercept estimate',
              samples=len(group),end_distance=round(end_distance,2),error_m=round(error,2))
  for label,rows in [('before',before),('after',after)]:
   eligible=[r for r in rows if group[0]['t']<=r['t']<=group[-1]['t'] and r['limit'] is not None and r['speed'] is not None and r['distance'] is not None]
   fall=next((r for r in eligible if r['limit']<r['speed']),None)
   if fall:
    need=max(0,(fall['speed']**2-6**2)/(2*2))
    distance=fall['distance']-end_distance
    result[label]=dict(t=round(fall['t'],3),distance_m=round(distance,2),needed_m=round(need,2),
                       margin_m=round(distance-need,2),reason=fall['reason'],left_censored=fall==eligible[0])
   else:result[label]=None
  results.append(result)
 return results


def main():
 old,oldcfg=baseline();results={}
 with gzip.open(OUT/'p105-replay.csv.gz','wt') as f:
  writer=csv.writer(f);writer.writerow(['run','t','speed','gps_distance','before_limit','before_reason','after_limit','after_reason','before_brake','after_brake'])
  for run in RUNS:
   source=list(map(json.loads,(Path('/Users/kerim/recordings/pilot')/f'20261114-{run}'/'play.jsonl').open()))
   before=replay(old,oldcfg,source);after=replay(Driver,drive_config(['style=bold']),source)
   if run=='005357':before=[r for r in before if 400<=r['t']<=520];after=[r for r in after if 400<=r['t']<=520]
   for a,b in zip(before,after,strict=True):
    writer.writerow([run,round(a['t'],3),a['speed'],a['distance'],a['limit'],a['reason'],b['limit'],b['reason'],a['brake'],b['brake']])
   results[run]=dict(before=summary(before),after=summary(after))
   if run!='005357':results[run]['junctions']=junctions(run,source,before,after)
   else:
    for label,rows in [('before',before),('after',after)]:
     live=[r for r in rows if r['limit'] is not None and r['speed'] is not None]
     results[run][label]['speed_quantiles']=np.percentile([r['speed'] for r in live],[10,50,90]).round(3).tolist()
     results[run][label]['limit_at_least_speed_share']=round(sum(r['limit']>=min(28,r['speed']) for r in live)/len(live),4)
   print(run,json.dumps({k:v for k,v in results[run].items() if k!='junctions'}),flush=True)
 (OUT/'p105-replay.json').write_text(json.dumps(results,indent=2)+'\n')
if __name__=='__main__':main()
