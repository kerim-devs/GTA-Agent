"""Read-only local recording evidence; sparse detector frames and every fresh tick."""

import gzip
import hashlib
import json
from collections import Counter, deque
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

from pilot.avoid import _in_lane, _seen, waits_behind
from pilot.motion import map_motion, motion_state
from pilot.objects import MODEL, Detector, split_player
from pilot.replay import hud_crop

HERE = Path(__file__).resolve().parent
ROOT = Path("/Users/kerim/recordings/pilot")
SESSIONS = {
    "20261114-000623": (
        700,
        [
            700,
            705,
            705.25,
            705.5,
            705.75,
            706,
            707,
            710,
            720,
            733,
            737,
            750,
            765,
            780,
            813,
            815.8,
            816.75,
            817.3,
            823.8,
            830.8,
            841.6,
            864.4,
            875,
        ],
    ),
    "20261114-002126": (
        0,
        [
            0,
            12.1,
            15,
            16.8,
            18.1,
            20,
            25,
            27,
            36,
            39,
            48.3,
            59.2,
            65.5,
            75,
            95,
            100,
            113,
            125,
            136,
            152,
            165,
            169,
        ],
    ),
}


def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def main():
    from p101_sim import baseline_avoid

    old = baseline_avoid()
    cv2.setNumThreads(1)
    detector = Detector()
    summary = {
        "model_sha256": hashlib.sha256(MODEL.read_bytes()).hexdigest(),
        "confidence": 0.4,
        "sessions": {},
    }
    for session, (start, times) in SESSIONS.items():
        folder = ROOT / session
        rows = [r for r in lines(folder / "play.jsonl") if r["t"] >= start]
        frames = lines(folder / "frames.jsonl")
        selected = {r["frame_id"]: r for r in rows if r.get("fresh") and r.get("reading")}
        detect_frames = {min(frames, key=lambda f: abs(f["t"] - t))["i"] for t in times}
        cap = cv2.VideoCapture(str(folder / "video.mp4"))
        first = min(f["i"] for f in frames if f["t"] >= max(0, start - 1.2))
        cap.set(cv2.CAP_PROP_POS_FRAMES, first)
        history, ticks, detections, thumbs = deque(), [], [], []
        avoider = old.Avoider()
        for f in frames[first:]:
            if not cap.grab():
                raise RuntimeError(f"Missing frame {session}:{f['i']}")
            if f["frame_id"] not in selected and f["i"] not in detect_frames:
                continue
            ok, bgr = cap.retrieve()
            if not ok:
                raise RuntimeError(f"Decode failed {session}:{f['i']}")
            if f["i"] in detect_frames:
                raw = detector.detect(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), exclude_player=False)
                objects, _, own = split_player(raw)
                around = avoider.step(objects, f["t"], f["t"])
                item = {
                    **f,
                    "raw": [asdict(o) for o in raw],
                    "objects": [asdict(o) for o in objects],
                    "dropped_vehicle": None if own is None else asdict(own),
                    "ahead": waits_behind(objects, f["t"], f["t"]),
                    "side": old.passing_side(objects, f["t"], f["t"]),
                    "around": asdict(around),
                    "geometry": [
                        {
                            "kind": o.kind,
                            "in_lane": _in_lane(o),
                            "offset_width_near": _seen(o),
                        }
                        for o in objects
                    ],
                }
                detections.append(item)
                image = cv2.resize(bgr, (480, 270))
                for obj in raw:
                    x0, y0, x1, y1 = (round(v * 0.375) for v in obj.box)
                    color = (0, 0, 255) if obj is own else (0, 255, 255)
                    cv2.rectangle(image, (x0, y0), (x1, y1), color, 1)
                    cv2.putText(
                        image,
                        obj.kind,
                        (x0, max(24, y0)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.4,
                        color,
                        1,
                    )
                cv2.rectangle(image, (0, 0), (480, 23), (0, 0, 0), -1)
                cv2.putText(
                    image,
                    f"{session[-6:]} {f['t']:.2f}s ahead={item['ahead']} side={item['side']}",
                    (4, 16),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.42,
                    (255, 255, 255),
                    1,
                )
                thumbs.append(image)
            if f["frame_id"] not in selected:
                continue
            crop = hud_crop(bgr)
            while history and history[0][0] < f["t"] - 1.2:
                history.popleft()
            moving = None
            flow = None
            if history and f["t"] - history[0][0] >= 0.15:
                _, previous = min(history, key=lambda h: abs(f["t"] - h[0] - 0.2))
                flow = map_motion(previous, crop)
                moving = motion_state(flow)
                if moving is not True and f["t"] - history[0][0] >= 0.8:
                    flow = map_motion(history[0][1], crop)
                    moving = motion_state(flow)
            history.append((f["t"], crop.copy()))
            ticks.append(
                {
                    **selected[f["frame_id"]],
                    "capture_t": f["t"],
                    "i": f["i"],
                    "moving": moving,
                    "flow": flow,
                }
            )
        cap.release()
        with gzip.open(HERE / f"p101-{session[-6:]}-ticks.json.gz", "wt") as stream:
            json.dump(ticks, stream, separators=(",", ":"))
        (HERE / f"p101-{session[-6:]}-detections.json").write_text(json.dumps(detections, indent=2) + "\n")
        for offset in range(0, len(thumbs), 8):
            group = thumbs[offset : offset + 8]
            if len(group) % 2:
                group.append(np.zeros_like(group[0]))
            cv2.imwrite(
                str(HERE / f"p101-{session[-6:]}-frames-{offset // 8 + 1}.jpg"),
                np.concatenate(
                    [np.concatenate(group[i : i + 2], axis=1) for i in range(0, len(group), 2)],
                    axis=0,
                ),
            )
        summary["sessions"][session] = {
            "ticks": len(ticks),
            "detector_frames": len(detections),
            "states": dict(
                Counter(
                    (r.get("result") or {}).get("driver_state")
                    or (r.get("skill") or {}).get("name")
                    or "none"
                    for r in ticks
                )
            ),
            "motion": dict(Counter(str(r["moving"]) for r in ticks)),
            "sha256": {
                name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                for name in ("play.jsonl", "frames.jsonl")
            },
        }
        print(json.dumps(summary["sessions"][session]), flush=True)
        (HERE / "p101-recordings.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
