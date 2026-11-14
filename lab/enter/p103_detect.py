"""Only the short decision windows used by P103, at two frames per second."""
import bisect
import json
import sys
from dataclasses import asdict
from pathlib import Path

import cv2
from pilot.objects import Detector

OUT = Path(__file__).parent
BASE = Path('/Users/kerim/recordings/pilot')
WINDOWS = {'20261114-004115': [(450.4,455)], '20261114-010438': [(160,164), (281.8,286)], '20261114-011429': [(278,281), (290,293), (316,319)]}


def main():
    cv2.setNumThreads(1)
    detector = Detector()
    path = OUT/'p103-detections.json'
    only = sys.argv[1] if len(sys.argv) > 1 else None
    samples = [s for s in json.loads(path.read_text()) if s['session'] != only] if only and path.exists() else []
    for sid, windows in WINDOWS.items():
        if only and sid != only:
            continue
        folder=BASE/sid
        play=[json.loads(l) for l in (folder/'play.jsonl').open()]
        frames=[json.loads(l) for l in (folder/'frames.jsonl').open()]
        times=[r['t'] for r in play]
        indices={r['frame_id']:r['i'] for r in frames}
        video=cv2.VideoCapture(str(folder/'video.mp4'))
        if not video.isOpened():
            print(sid, 'video not finalized; no detections reconstructed',flush=True)
            continue
        for start,end in windows:
            for n in range(int((end-start)*2)+1):
                row=play[bisect.bisect_left(times,start+n*.5)]
                i=indices[row['frame_id']]
                video.set(cv2.CAP_PROP_POS_FRAMES,i)
                ok,bgr=video.read()
                if not ok: raise RuntimeError((sid,i))
                objects, figure, own=detector.detect_split(cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB))
                samples.append({'session':sid,'t':row['t'],'video_frame':i,'reading':row['reading'],'objects':[asdict(d) for d in objects],'figure':asdict(figure) if figure else None,'figure_vehicle':asdict(own) if own else None})
        video.release()
        print(sid, 'done',flush=True)
    path.write_text(json.dumps(samples,indent=2)+'\n')


if __name__=='__main__': main()
