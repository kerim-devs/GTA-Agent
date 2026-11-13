"""trail_proto.py <session> [stride]: carry a point of the minimap along by the map's own motion.

Check 1: where the waypoint marker is read inside the map, carry its first reading along and compare
with the later readings. Check 2: the path of the figure, printed every two seconds.
"""

import json
import math
import sys

import cv2
import numpy as np

sys.path.insert(0, "/Users/kerim/Documents/ChatGPT/gta/pilot/src")
from pilot.foot import _MASK, _X0, _X1, _Y0, _Y1, crop_ok  # noqa: E402
from pilot.minimap import ACX, ACY  # noqa: E402
from pilot.waymark import find_waypoint  # noqa: E402


def motion(prev, cur):
    """The map's turn about the arrow and its shift from one crop to the next, as a 2x3 matrix."""
    if not (crop_ok(prev) and crop_ok(cur)):
        return None
    a = cv2.cvtColor(prev[_Y0:_Y1, _X0:_X1], cv2.COLOR_RGB2GRAY)
    b = cv2.cvtColor(cur[_Y0:_Y1, _X0:_X1], cv2.COLOR_RGB2GRAY)
    points = cv2.goodFeaturesToTrack(a, maxCorners=60, qualityLevel=0.02, minDistance=5, mask=_MASK)
    if points is None or len(points) < 6:
        return None
    forward, status, error = cv2.calcOpticalFlowPyrLK(a, b, points, None, winSize=(15, 15), maxLevel=3)
    if forward is None:
        return None
    back, back_status, _ = cv2.calcOpticalFlowPyrLK(b, a, forward, None, winSize=(15, 15), maxLevel=3)
    if back is None:
        return None
    valid = (status.ravel() > 0) & (back_status.ravel() > 0) & (error.ravel() < 20)
    valid &= np.linalg.norm(points - back, axis=2).ravel() < 0.8
    if valid.sum() < 6:
        return None
    centre = np.array([ACX - _X0, ACY - _Y0], np.float32)
    src = points.reshape(-1, 2)[valid] - centre
    dst = forward.reshape(-1, 2)[valid] - centre
    model, inliers = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=1.5)
    if model is None or inliers is None or int(inliers.sum()) < 6:
        return None
    scale = math.hypot(model[0, 0], model[1, 0])
    if not 0.9 < scale < 1.1:
        return None
    return model


def apply(model, p):
    return (
        model[0, 0] * p[0] + model[0, 1] * p[1] + model[0, 2],
        model[1, 0] * p[0] + model[1, 1] * p[1] + model[1, 2],
    )


def frames(session, stride):
    times = [json.loads(line)["t"] for line in open(session + "/frames.jsonl")]
    video = cv2.VideoCapture(session + "/video.mp4")
    i = 0
    while True:
        ok, frame = video.read()
        if not ok or i >= len(times):
            return
        if i % stride == 0:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            yield times[i] - times[0], rgb[530:700, 30:290].copy()
        i += 1


if __name__ == "__main__":
    session = sys.argv[1]
    stride = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    KEY_SHIFT, KEY_TURN = 3.0, 12.0
    key = None  # the crop the motion is measured from
    since_key = None  # the motion from the key to the last crop it was told for
    carried = None  # the marker's first reading inside the map, carried along: crop pixels, y down
    origin = (0.0, 0.0)  # where the figure stood at the first frame, carried along
    lost = 0
    last_print = -9
    errs = []
    for t, crop in frames(session, stride):
        if not crop_ok(crop):
            key = None
            lost += 1
            continue
        if key is None:
            key, since_key, base = crop, np.float32([[1, 0, 0], [0, 1, 0]]), (carried, origin)
            continue
        model = motion(key, crop)
        if model is None:
            # carry on from the last crop that was told
            base = (None if base[0] is None else apply(since_key, base[0]), apply(since_key, base[1]))
            key, since_key = crop, np.float32([[1, 0, 0], [0, 1, 0]])
            lost += 1
            carried, origin = base
            continue
        since_key = model
        carried = None if base[0] is None else apply(model, base[0])
        origin = apply(model, base[1])
        turn = math.degrees(math.atan2(model[1, 0], model[0, 0]))
        if math.hypot(model[0, 2], model[1, 2]) >= KEY_SHIFT or abs(turn) >= KEY_TURN:
            base = (carried, origin)
            key, since_key = crop, np.float32([[1, 0, 0], [0, 1, 0]])
        blip = find_waypoint(crop)
        if blip is not None and not blip.border:
            read = (blip.x, -blip.y)
            if carried is None:
                carried = read
                base = (apply(np.linalg.inv(np.vstack([since_key, [0, 0, 1]]))[:2], read), base[1])
                first = t
            else:
                err = math.hypot(carried[0] - read[0], carried[1] - read[1])
                errs.append((t - first, err, math.hypot(*read)))
        if t - last_print >= 2.0:
            last_print = t
            tail = ""
            if errs and abs(errs[-1][0] - (t - first)) < 0.2:
                tail = f"  marker carried {errs[-1][0]:.1f}s off by {errs[-1][1]:.2f}px at {errs[-1][2]:.0f}px"
            print(f"{t:6.1f}s start at ({origin[0]:7.1f},{origin[1]:7.1f}) {math.hypot(*origin):6.1f}px{tail}")
    print("lost", lost)
    if errs:
        print("marker: last", errs[-1], "max", max(e[1] for e in errs))
