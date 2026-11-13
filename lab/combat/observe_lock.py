"""Look for camera snaps around quiet-stick locks; never infer target identity."""
import bisect
import json
import math
import sys
from pathlib import Path
import cv2
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'pilot/src'))
from pilot.minimap import read
cv2.setNumThreads(1)


def main():
    data=json.loads((ROOT/'lab/combat/recorded-rhythm.json').read_text())
    locks={}
    for row in data['rows']:
        if row['group']!='red' or row['left_firing']['magnitude']>.1:continue
        for m in row['lock_measurements']:
            if m['right_during']['magnitude']>.1 or not m['right_before'] or m['right_before']['magnitude']>.1:continue
            if m['interval'][1]-m['interval'][0]<.6:continue
            locks[(row['recording'],*m['interval'])]=row['lead']
    results=[]
    for rec in sorted({key[0] for key in locks}):
        base=Path('/Users/kerim/recordings/kerim')/rec
        frames=[json.loads(line) for line in (base/'frames.jsonl').read_text().splitlines()]
        times=[f['t'] for f in frames]
        cap=cv2.VideoCapture(str(base/'video.mp4'))
        try:
            for (name,start,end),lead in locks.items():
                if name!=rec:continue
                readings=[]
                for t in (start+lead-.1,start+lead+.5):
                    i=min(len(frames)-1,bisect.bisect_left(times,t));meta=frames[i]
                    cap.set(cv2.CAP_PROP_POS_FRAMES,meta['i']);ok,bgr=cap.read()
                    if not ok:raise ValueError(f'{rec}: cannot read frame {meta["i"]}')
                    r=read(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)[530:700,30:290])
                    red=[b for b in r.blips if b.color=='red']
                    angle=math.degrees(math.atan2(red[0].x,red[0].y)) if len(red)==1 and not r.corrupt and r.minimap=='flat' else None
                    readings.append({'frame':meta['i'],'t':meta['t'],'red':len(red),'angle':angle})
                before,after=(r['angle'] for r in readings)
                results.append({'recording':rec,'lock':[start,end],'samples':readings,
                                'possible_snap':before is not None and after is not None and abs(before)>12 and abs(after)<=12})
        finally:cap.release()
    candidates=[r for r in results if r['possible_snap']]
    out={'method':'Only low left-stick fire stretches and low right-stick locks; native minimap 100ms before and 500ms after L2 plus recorded lead. Exactly one red at both samples. Candidate snaps cannot identify the same enemy or isolate aim assist from automatic camera behavior.',
         'locks':len(results),'candidates':len(candidates),'max_candidate_bearing':max((abs(r['samples'][0]['angle']) for r in candidates),default=None),'rows':results}
    (ROOT/'lab/combat/lock-observations.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps({k:v for k,v in out.items() if k!='rows'}))


if __name__=='__main__':main()
