"""Small local frames for the three short cutting windows, decoded with cv2."""
import json
from pathlib import Path

import cv2

OUT=Path(__file__).parent
BASE=Path('/Users/kerim/recordings/pilot/20261114-011429')
cv2.setNumThreads(1)
video=cv2.VideoCapture(str(BASE/'video.mp4'))
samples=[s for s in json.loads((OUT/'p103-detections.json').read_text()) if s['session'].endswith('011429')]
for sample in samples:
    i=sample['video_frame']
    video.set(cv2.CAP_PROP_POS_FRAMES,i)
    ok,frame=video.read()
    if not ok: raise RuntimeError(i)
    sample['image']=f'p103-cutting-f{i}.jpg'
    cv2.imwrite(str(OUT/sample['image']),frame,[cv2.IMWRITE_JPEG_QUALITY,65])
video.release()
(OUT/'p103-cutting.json').write_text(json.dumps(samples,indent=2)+'\n')
