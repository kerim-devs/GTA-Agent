"""Replay recorded observations only while their inputs agree with the new skill.

Run from pilot with env -u PS5_HOST .venv/bin/python ../lab/waypoint/p35_replay.py.
No recording can supply the consequence of a different input; stop neutral there.
"""

import json
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

from pilot.contract import HUD_RECT, Observation
from pilot.hud import read as read_hud
from pilot.minimap import read as read_minimap
from pilot.scene import TextReader
from pilot.waypoint import SetWaypoint, read_map


def replay(stamp, target):
    root = Path("/Users/kerim/recordings/pilot") / f"20261111-{stamp}"
    frames = {
        row["frame_id"]: row for row in map(json.loads, (root / "frames.jsonl").read_text().splitlines())
    }
    ticks = [
        row
        for row in map(json.loads, (root / "play.jsonl").read_text().splitlines())
        if (row.get("skill") or {}).get("name") == "set_waypoint"
    ]
    skill = SetWaypoint({"target": target, "direction": "north"})
    reader = TextReader()
    capture = cv2.VideoCapture(str(root / "video.mp4"))
    trace, events = [], []
    previous = None
    last_frame = None
    x, y, w, h = HUD_RECT
    for tick in ticks:
        meta = frames.get(tick.get("frame_id"))
        if meta is None:
            continue
        if meta["frame_id"] != last_frame:
            capture.set(cv2.CAP_PROP_POS_FRAMES, meta["i"])
            ok, bgr = capture.read()
            assert ok
            frame = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            text = reader.read(frame)
            reading = read_minimap(frame[y : y + h, x : x + w])
            hud = read_hud(frame, text)
            last_frame = meta["frame_id"]
        skill._picture = lambda image, text=text: read_map(image, text)
        result = skill.step(Observation(reading, False, tick["t"], frame, hud=hud))
        actual = tick["result"]["pad"]
        proposed = asdict(result.pad)
        row = {
            "t": tick["t"],
            "frame_id": meta["frame_id"],
            "phase": skill.phase,
            "proposed": proposed,
            "recorded": actual,
            "status": result.status,
            "reason": result.reason,
        }
        trace.append(row)
        if proposed != previous:
            events.append(row)
            previous = proposed
        same = list(result.pad.buttons) == actual["buttons"] and np.allclose(
            result.pad.left, actual["left"], atol=0.01
        )
        if not same:
            result = skill.stop("recorded-input-diverged; use live-zoom simulation for the new consequence")
            break
        if result.status != "running":
            break
    else:
        result = skill.stop("recorded-visit-ended")
    capture.release()
    return {
        "recording": root.name,
        "target": target,
        "final": asdict(result),
        "events": events,
        "trace": trace,
    }


results = [
    replay("124637", "mission"),
    replay("123334", "away"),
    replay("125537", "away"),
    replay("133505", "away"),
    replay("132729", "away"),
]
Path(__file__).with_name("p35-replay.json").write_text(json.dumps(results, indent=2) + "\n")
for result in results:
    print(json.dumps({key: value for key, value in result.items() if key != "trace"}))
