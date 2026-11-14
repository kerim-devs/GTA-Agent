"""Bounded contact sheets: one frame for every lifted second in the two town windows."""
import bisect
import json
from pathlib import Path

import cv2
import numpy as np
from pilot.replay import hud_crop

ROOT=Path(__file__).resolve().parents[2]
cv2.setNumThreads(1)
audit=json.loads((ROOT/"lab/drive/p102-audit.json").read_text())
for name,recording in [("town","20261114-010438"),("incident","20261114-011017")]:
    seconds=sorted({row["second"] for group in [audit[name]["recorded_lifted_seconds"],audit[name]["before"]["lifted_seconds"],audit[name]["after"]["lifted_seconds"]] for row in group})
    directory=Path("/Users/kerim/recordings/pilot")/recording
    frames=[json.loads(line) for line in (directory/"frames.jsonl").open()];times=[f["t"] for f in frames]
    cap=cv2.VideoCapture(str(directory/"video.mp4"));tiles=[]
    for second in seconds:
        frame=frames[bisect.bisect_left(times,second+.5)]
        cap.set(cv2.CAP_PROP_POS_FRAMES,frame["i"]);ok,bgr=cap.read();assert ok
        tile=np.zeros((288,768,3),dtype=np.uint8);tile[:,:512]=cv2.resize(bgr,(512,288))
        tile[70:240,508:768]=cv2.cvtColor(hud_crop(bgr),cv2.COLOR_RGB2BGR)
        cv2.putText(tile,f'{recording} {frame["t"]:.2f}s',(5,23),cv2.FONT_HERSHEY_SIMPLEX,.6,(0,255,255),2);tiles.append(tile)
    for page,offset in enumerate(range(0,len(tiles),8)):
        group=tiles[offset:offset+8]
        while len(group)%2:group.append(np.zeros_like(group[0]))
        sheet=np.concatenate([np.concatenate(group[i:i+2],axis=1) for i in range(0,len(group),2)])
        cv2.imwrite(str(ROOT/"lab/drive"/f"p102-audit-{name}-{page}.jpg"),sheet,[cv2.IMWRITE_JPEG_QUALITY,75])
    cap.release()
    print(name,seconds)
