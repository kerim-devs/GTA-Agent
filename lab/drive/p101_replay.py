"""Counterfactual commands on frozen readings; sparse boxes expire after 0.6 s."""

import csv
import gzip
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path

from p101_sim import baseline, baseline_avoid

from pilot.avoid import STALE, waits_behind
from pilot.cli import drive_config
from pilot.contract import Detection, Reading
from pilot.drive import Driver

HERE = Path(__file__).resolve().parent


def inputs(session):
    with gzip.open(HERE / f"p101-{session}-ticks.json.gz", "rt") as stream:
        rows = json.load(stream)
    detections = json.loads((HERE / f"p101-{session}-detections.json").read_text())
    # play.t is relative, GPS uses monotonic time. The newest observed fix sets
    # the origin; this preserves sample ages up to that fix's unlogged latency.
    origin = max(r["reading"]["gps_time"] - r["t"] for r in rows if r["reading"]["gps_time"] is not None)
    index = -1
    for row in rows:
        while index + 1 < len(detections) and detections[index + 1]["t"] <= row["capture_t"]:
            index += 1
        detection = None if index < 0 else detections[index]
        objects = () if detection is None else tuple(Detection(**o) for o in detection["objects"])
        at = None if detection is None else detection["t"]
        reading = Reading(**{**row["reading"], "blips": ()})
        if reading.gps_time is not None:
            reading = replace(reading, gps_time=reading.gps_time - origin)
        yield row, reading, objects, at


def replay(session, driver_type, label):
    import pilot.avoid as current_avoid

    avoid = baseline_avoid() if label == "before" else current_avoid
    driver = driver_type(drive_config(["style=bold"]))
    avoider = avoid.Avoider()
    previous_skill = None
    states, transitions = Counter(), []
    with gzip.open(HERE / f"p101-{session}-replay-{label}.csv.gz", "wt") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "t",
                "frame_id",
                "skill",
                "recorded_state",
                "moving",
                "gps_speed",
                "gps_age",
                "box_age",
                "ahead",
                "side",
                "avoid_steer",
                "avoid_pedal",
                "state",
                "steer",
                "r2",
                "l2",
            ]
        )
        for row, reading, objects, at in inputs(session):
            now = row["t"]
            skill = (row.get("skill") or {}).get("name")
            if skill == "drive_route" and previous_skill != skill:
                driver = driver_type(drive_config(["style=bold"]))
            previous_skill = skill
            ahead = waits_behind(objects, at, now)
            side = avoid.passing_side(objects, at, now)
            around = avoider.step(objects, at, now, bypass=driver.bypassing)
            # Missing sparse samples are marked unavailable, not fabricated boxes.
            # The independent stillness path needs no obstacle observation.
            fresh = at is not None and 0 <= now - at <= STALE
            command = (
                driver.step(
                    reading,
                    now,
                    row["moving"],
                    speed=reading.gps_speed,
                    ahead=ahead,
                    bypass_side=side,
                    boxes_fresh=True,
                )
                if skill == "drive_route"
                else None
            )
            writer.writerow(
                [
                    now,
                    row["frame_id"],
                    skill,
                    (row.get("result") or {}).get("driver_state"),
                    row["moving"],
                    reading.gps_speed,
                    None if reading.gps_time is None else now - reading.gps_time,
                    None if at is None else now - at,
                    ahead,
                    side,
                    around.steer,
                    around.pedal,
                    None if command is None else command.state,
                    None if command is None else command.steer,
                    None if command is None else command.throttle,
                    None if command is None else command.brake,
                ]
            )
            if command:
                states[command.state] += 1
                if not transitions or transitions[-1][1] != command.state:
                    transitions.append([round(now, 4), command.state, command.steer, fresh])
    return {"states": states, "transitions": transitions}


def main():
    result = {
        label: {session: replay(session, cls, label) for session in ("000623", "002126")}
        for label, cls in (("before", baseline()), ("after", Driver))
    }
    (HERE / "p101-replay.json").write_text(json.dumps(result, indent=2) + "\n")
    for label, sessions in result.items():
        for session, value in sessions.items():
            print(label, session, value["states"])


if __name__ == "__main__":
    main()
