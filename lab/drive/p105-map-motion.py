"""Calibrate tilt from road texture correspondences, independently of route corners."""
import json
from pathlib import Path
import cv2
import numpy as np
from pilot.replay import hud_crop
OUT=Path(__file__).resolve().parent
WINDOWS=[('024431',170,180),('024431',202,214),('021738',100,111),('021738',590,605),('005357',400,412),('015901',264,274),('014037',260,274),('024817',82,94),('025345',143,153)]


def unproject(p,k,ratio):
 return p*np.array([ratio,1])/np.maximum(.15,1-k*p[:,1,None])


def similarity(a,b):
 ac=a-a.mean(0);bc=b-b.mean(0);u,s,v=np.linalg.svd(ac.T@bc);rot=u@v
 scale=s.sum()/np.sum(ac**2); translation=b.mean(0)-scale*a.mean(0)@rot
 residual=np.linalg.norm(scale*a@rot+translation-b,axis=1)
 return scale,translation,residual,rot


def main():
 data=[]
 for run,start,end in WINDOWS:
  base=Path('/Users/kerim/recordings/pilot')/f'20261114-{run}'
  frames=list(map(json.loads,(base/'frames.jsonl').open()))
  rows=[r for r in map(json.loads,(base/'play.jsonl').open()) if r.get('reading')]
  cap=cv2.VideoCapture(str(base/'video.mp4'));prev=None
  for t in np.arange(start,end+.1,1):
   f=min(frames,key=lambda f:abs(f['t']-t));cap.set(cv2.CAP_PROP_POS_FRAMES,f['i']);ok,img=cap.read()
   if not ok:continue
   crop=hud_crop(img); gray=cv2.cvtColor(crop,cv2.COLOR_RGB2GRAY)
   if prev:
    old,old_f=prev
    mask=np.zeros_like(gray);mask[33:131,39:209]=255;mask[101:131,108:138]=0
    p=cv2.goodFeaturesToTrack(old,300,.02,4,mask=mask)
    q,status,err=cv2.calcOpticalFlowPyrLK(old,gray,p,None,winSize=(15,15),maxLevel=2)
    back,bs,be=cv2.calcOpticalFlowPyrLK(gray,old,q,None,winSize=(15,15),maxLevel=2)
    valid=(status[:,0]>0)&(bs[:,0]>0)&(np.linalg.norm(p[:,0]-back[:,0],axis=1)<.5)&(err[:,0]<20)
    a,b=p[valid,0],q[valid,0]
    if len(a)>=15:
     h,inliers=cv2.findHomography(a,b,cv2.RANSAC,1.0)
     if inliers is not None:
      a,b=a[inliers[:,0]>0],b[inliers[:,0]>0]
      a=(a-[123.3,116.8])*[1,-1];b=(b-[123.3,116.8])*[1,-1]
      ra=min(rows,key=lambda r:abs(r['t']-old_f['t']));rb=min(rows,key=lambda r:abs(r['t']-f['t']))
      data.append(dict(run=run,t0=old_f['t'],t1=f['t'],a=a.tolist(),b=b.tolist(),
                       speed0=ra['reading'].get('gps_speed'),speed1=rb['reading'].get('gps_speed'),
                       d0=ra['reading'].get('gps_distance'),d1=rb['reading'].get('gps_distance'),
                       age0=(ra.get('skill') or {}).get('distance_age'),age1=(rb.get('skill') or {}).get('distance_age')))
   prev=gray,f
  cap.release()
 best=None
 for k in np.arange(0,.0121,.00025):
  for ratio in np.arange(.3,1.31,.025):
   errors=[]
   for r in data:
    a,b=[unproject(np.array(r[key]),k,ratio) for key in ('a','b')]
    s,tr,err,rot=similarity(a,b)
    errors.append(np.median(err)/np.linalg.norm(tr) if np.linalg.norm(tr)>1 else np.nan)
   score=np.nanmedian(errors)
   if best is None or score<best[0]:best=score,k,ratio
 score,k,ratio=best
 print('fit',score,k,ratio,'pairs',len(data))
 results=[]
 for r in data:
  a,b=[unproject(np.array(r[key]),k,ratio) for key in ('a','b')]
  s,tr,err,rot=similarity(a,b)
  dist=np.linalg.norm(tr); dm=None
  if all(r[key] is not None for key in ('d0','d1','age0','age1','speed0','speed1')):
   dm=r['d0']-r['d1']-r['age0']*r['speed0']+r['age1']*r['speed1']
  result={key:v for key,v in r.items() if key not in ('a','b')}
  result.update(n=len(a),zoom=float(s),translation=float(dist),residual=float(np.median(err)),metres=dm,
                scale=dm/dist if dm is not None and dist>1 else None)
  results.append(result)
  print(r['run'],round(r['t0'],2),r['speed0'], 'zoom',round(s,3),'pix',round(dist,2),'err',round(np.median(err),2),'metres',round(dm,1) if dm is not None else None,'scale',round(dm/dist,2) if dm is not None and dist>1 else None)
 (OUT/'p105-motion-points.json').write_text(json.dumps(data,separators=(',',':'))+'\n')
 (OUT/'p105-motion.json').write_text(json.dumps(dict(tilt=float(k),ratio=float(ratio),score=float(score),rows=results),indent=2)+'\n')
if __name__=='__main__':main()
