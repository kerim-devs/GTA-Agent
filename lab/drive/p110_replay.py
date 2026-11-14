"""Replay frozen 110629 readings and frame-derived motion, never console inputs."""

import argparse
import gzip
import json
from collections import Counter, deque
from dataclasses import replace
from pathlib import Path
from statistics import median

import cv2
import numpy as np

from p101_sim import baseline
from pilot.cli import drive_config
from pilot.contract import Reading
from pilot.drive import Driver
from pilot.motion import map_motion, motion_state
from pilot.replay import hud_crop

HERE = Path(__file__).resolve().parent
ROOT = Path("/Users/kerim/recordings/pilot/20261114-110629")
CACHE = HERE / "p110-replay-inputs.json.gz"


def extract():
    ticks = [json.loads(line) for line in (ROOT / "play.jsonl").open()]
    origin = median(
        r["reading"]["gps_time"] + r["result"]["distance_age"] - r["t"]
        for r in ticks
        if (r.get("reading") or {}).get("gps_time") is not None
        and (r.get("result") or {}).get("distance_age") is not None
    )
    selected = {r["frame_id"]: r for r in ticks if 36 <= r["t"] <= 57 and r.get("fresh")}
    frames = [json.loads(line) for line in (ROOT / "frames.jsonl").open()]
    frames = [r for r in frames if r["frame_id"] in selected]
    cap = cv2.VideoCapture(str(ROOT / "video.mp4"))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frames[0]["i"])
    index = frames[0]["i"]
    history, rows, thumbs = deque(), [], []
    marks = iter([38.5, 42.5, 44.4, 47, 52, 56])
    mark = next(marks, None)
    for frame in frames:
        while index < frame["i"]:
            assert cap.grab()
            index += 1
        ok, bgr = cap.read()
        assert ok
        index += 1
        crop = hud_crop(bgr)
        while history and history[0][0] < frame["t"] - 1.2:
            history.popleft()
        flow, moving = None, None
        if history and frame["t"] - history[0][0] >= 0.15:
            _, old = min(history, key=lambda h: abs(frame["t"] - h[0] - 0.2))
            flow = map_motion(old, crop)
            moving = motion_state(flow)
            if moving is not True and frame["t"] - history[0][0] >= 0.8:
                flow = map_motion(history[0][1], crop)
                moving = motion_state(flow)
        history.append((frame["t"], crop.copy()))
        row = selected[frame["frame_id"]]
        if row["t"] >= 38:
            reading = dict(row["reading"], blips=[])
            if reading["gps_time"] is not None:
                reading["gps_time"] -= origin
            rows.append(
                dict(
                    t=row["t"],
                    frame_id=row["frame_id"],
                    capture_t=frame["t"],
                    reading=reading,
                    moving=moving,
                    flow=flow,
                    recorded_state=row["result"].get("driver_state"),
                    recorded_pad=row["result"]["pad"],
                )
            )
        if mark is not None and row["t"] >= mark:
            thumb = cv2.resize(bgr, (480, 270))
            cv2.rectangle(thumb, (0, 0), (480, 25), (0, 0, 0), -1)
            cv2.putText(
                thumb,
                f"{row['t']:.2f}s {row['result'].get('driver_state')}",
                (5, 18),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),
                1,
            )
            thumbs.append(thumb)
            mark = next(marks, None)
    cap.release()
    with gzip.open(CACHE, "wt") as f:
        json.dump(dict(origin=origin, rows=rows), f, separators=(",", ":"))
    sheet = np.vstack([np.hstack(thumbs[i : i + 2]) for i in range(0, 6, 2)])
    cv2.imwrite(str(HERE / "p110-110629-sheet.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 65])
    print("extracted", len(rows), "ticks; motion", Counter(str(r["moving"]) for r in rows))


def replay(driver_type=Driver):
    with gzip.open(CACHE, "rt") as f:
        rows = json.load(f)["rows"]
    driver = driver_type(drive_config(["style=bold"]))
    commands = []
    for row in rows:
        reading = replace(Reading(**row["reading"]), blips=())
        command = driver.step(reading, row["t"], row["moving"], speed=reading.gps_speed)
        commands.append(
            dict(t=row["t"], state=command.state, steer=command.steer, r2=command.throttle, l2=command.brake)
        )
    return commands


def held(commands, field, threshold):
    start, sign, longest = None, 0, 0
    for i, row in enumerate(commands):
        value = row[field]
        current = (1 if value > 0 else -1) if abs(value) >= threshold else 0
        if current != sign:
            start = row["t"] if current else None
        sign = current
        until = commands[i + 1]["t"] if i + 1 < len(commands) else row["t"]
        if start is not None:
            longest = max(longest, until - start)
    return longest


def summary(commands):
    return dict(
        full_lock_s=held(commands, "steer", 0.999),
        full_l2_s=held(commands, "l2", 0.999),
        strong_lock_s=held(commands, "steer", 0.9),
        states=Counter(r["state"] for r in commands),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--extract", action="store_true")
    args = parser.parse_args()
    if args.extract:
        extract()
    results = {}
    for label, cls in [("before", baseline()), ("after", Driver)]:
        commands = replay(cls)
        results[label] = summary(commands)
        with gzip.open(HERE / f"p110-replay-{label}.json.gz", "wt") as f:
            json.dump(commands, f, separators=(",", ":"))
    (HERE / "p110-replay.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))
