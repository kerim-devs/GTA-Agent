"""Measure delayed human stick direction against recorded minimap translation."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from pilot.minimap import read


def main() -> None:
    recording = Path("/Users/kerim/Documents/ChatGPT/gta/recordings/20261110-093238")
    output = Path(__file__).resolve().parents[2] / "lab/blips"
    output.mkdir(parents=True, exist_ok=True)
    frames = [json.loads(s) for s in (recording / "frames.jsonl").read_text().splitlines()]
    pads = [json.loads(s) for s in (recording / "pad.jsonl").read_text().splitlines()]
    pt = np.array([p["t"] for p in pads])
    cap = cv2.VideoCapture(str(recording / "video.mp4"))
    observations = []
    previous = None
    previous_time = None
    # Sample at ~5 Hz, preserving recorded timestamps instead of assuming constant FPS.
    for frame in frames:
        ok, image = cap.read()
        if not ok:
            break
        t = frame["t"]
        if previous_time is not None and t - previous_time < 0.19:
            continue
        crop = image[530:700, 30:290]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        if previous is not None:
            mask = np.zeros_like(gray)
            mask[32:138, 39:209] = 255
            cv2.circle(mask, (123, 117), 20, 0, -1)
            cv2.circle(mask, (125, 39), 14, 0, -1)
            points = cv2.goodFeaturesToTrack(previous, 100, 0.03, 5, mask=mask)
            if points is not None and len(points) >= 8:
                moved, status, error = cv2.calcOpticalFlowPyrLK(previous, gray, points, None)
                back, back_status, _ = cv2.calcOpticalFlowPyrLK(gray, previous, moved, None)
                valid = (
                    (status.ravel() == 1)
                    & (back_status.ravel() == 1)
                    & (error.ravel() < 15)
                    & (np.linalg.norm(back - points, axis=2).ravel() < 0.8)
                )
                a, b = points[valid], moved[valid]
                if len(a) >= 8:
                    matrix, inliers = cv2.estimateAffinePartial2D(
                        a, b, method=cv2.RANSAC, ransacReprojThreshold=1.0
                    )
                    if matrix is not None:
                        center = np.array([123.0, 117.0])
                        motion = matrix[:, :2] @ center + matrix[:, 2] - center
                        rotation = float(np.degrees(np.arctan2(matrix[1, 0], matrix[0, 0])))
                        samples = {}
                        for delay in (0.6, 0.7, 0.8, 0.9, 1.0, 1.1):
                            indices = (
                                np.searchsorted(
                                    pt,
                                    [previous_time - delay, (previous_time + t) / 2 - delay, t - delay],
                                    side="right",
                                )
                                - 1
                            )
                            if min(indices) < 0:
                                continue
                            states = [pads[i] for i in indices]
                            sticks = np.array([s["left"] for s in states])
                            right = np.array([s["right"] for s in states])
                            if any(s["src"] != "human" for s in states):
                                continue
                            if np.max(np.linalg.norm(right, axis=1)) > 0.1:
                                continue
                            if np.min(np.linalg.norm(sticks, axis=1)) < 0.4:
                                continue
                            if np.max(np.linalg.norm(sticks - sticks.mean(axis=0), axis=1)) > 0.2:
                                continue
                            stick = sticks.mean(axis=0)
                            norm = np.linalg.norm(motion) * np.linalg.norm(stick)
                            if norm > 0:
                                cosine = float(np.clip(np.dot(-motion, stick) / norm, -1, 1))
                                samples[str(delay)] = {
                                    "stick": stick.tolist(),
                                    "angle": float(np.degrees(np.arccos(cosine))),
                                }
                        if samples:
                            reading = read(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
                            observations.append(
                                {
                                    "i": frame["i"],
                                    "t": t,
                                    "start": previous_time,
                                    "map": reading.minimap,
                                    "corrupt": reading.corrupt,
                                    "motion": motion.tolist(),
                                    "rotation": rotation,
                                    "scale": float(np.hypot(matrix[0, 0], matrix[1, 0])),
                                    "inliers": int(inliers.sum()),
                                    "points": len(a),
                                    "samples": samples,
                                }
                            )
        previous, previous_time = gray, t
    cap.release()
    (output / "camera-motion-raw.json").write_text(json.dumps(observations, indent=2) + "\n")
    print(f"{len(observations)} stable-input frame pairs written to {output}")


if __name__ == "__main__":
    main()
