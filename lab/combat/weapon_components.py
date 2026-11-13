from pathlib import Path
import cv2
import json
import numpy as np

samples = json.load(open(str(Path(__file__).with_name("weapon-samples.json"))))["samples"]
features = []
for sample in samples:
    capture = cv2.VideoCapture(f"/Users/kerim/recordings/kerim/{sample['recording']}/video.mp4")
    capture.set(cv2.CAP_PROP_POS_FRAMES, sample["frame"])
    ok, frame = capture.read()
    capture.release()
    if not ok:
        raise ValueError(sample)
    roi = frame[20:100, 1030:1240]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array([0, 0, 180]), np.array([180, 95, 255]))
    _, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    components = [row for row in stats[1:] if 6 <= row[4] <= 350 and 5 <= row[3] <= 35 and 1 <= row[2] <= 28]
    features.append({
        **sample, "components": len(components), "ink": int(mask.sum() // 255),
        "largest": int(max([row[4] for row in components], default=0)),
    })
json.dump({
    "roi_xyxy": [1030, 20, 1240, 100],
    "hsv": {"low": [0, 0, 180], "high": [180, 95, 255]},
    "components": {"area": [6, 350], "height": [5, 35], "width": [1, 28]},
    "features": features,
}, open(str(Path(__file__).with_name("weapon-components.json")), "w"), indent=2)
