"""Six extra detections around the first GPS-confirmed standstill, without repeating the scan."""

import json
from dataclasses import asdict

import cv2
import numpy as np
from p101_recordings import HERE, ROOT, lines

from pilot.avoid import Avoider, _in_lane, _seen, passing_side, waits_behind
from pilot.objects import Detector, split_player


def main():
    cv2.setNumThreads(1)
    folder = ROOT / "20261114-000623"
    path = HERE / "p101-000623-detections.json"
    detections = json.loads(path.read_text())
    frames = lines(folder / "frames.jsonl")
    detector, avoider = Detector(), Avoider()
    cap = cv2.VideoCapture(str(folder / "video.mp4"))
    thumbs = []
    for t in (715, 715.5, 716, 716.5, 717, 717.5):
        f = min(frames, key=lambda f: abs(f["t"] - t))
        if any(d["i"] == f["i"] for d in detections):
            continue
        cap.set(cv2.CAP_PROP_POS_FRAMES, f["i"])
        ok, frame = cap.read()
        assert ok
        raw = detector.detect(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), exclude_player=False)
        objects, _, own = split_player(raw)
        detections.append(
            {
                **f,
                "raw": [asdict(o) for o in raw],
                "objects": [asdict(o) for o in objects],
                "dropped_vehicle": None if own is None else asdict(own),
                "ahead": waits_behind(objects, f["t"], f["t"]),
                "side": passing_side(objects, f["t"], f["t"]),
                "around": asdict(avoider.step(objects, f["t"], f["t"])),
                "geometry": [
                    {
                        "kind": o.kind,
                        "in_lane": _in_lane(o),
                        "offset_width_near": _seen(o),
                    }
                    for o in objects
                ],
            }
        )
        image = cv2.resize(frame, (480, 270))
        cv2.putText(
            image,
            f"{f['t']:.3f}s",
            (5, 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 255),
            1,
        )
        thumbs.append(image)
    cap.release()
    detections.sort(key=lambda d: d["t"])
    path.write_text(json.dumps(detections, indent=2) + "\n")
    if thumbs:
        cv2.imwrite(
            str(HERE / "p101-000623-extra.jpg"),
            np.concatenate([np.concatenate(thumbs[i : i + 2], axis=1) for i in range(0, len(thumbs), 2)]),
        )
    receipt = json.loads((HERE / "p101-recordings.json").read_text())
    receipt["sessions"][folder.name]["detector_frames"] = len(detections)
    (HERE / "p101-recordings.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
