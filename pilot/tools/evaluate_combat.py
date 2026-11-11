"""Describe the recorded shootout without contacting the controller bridge."""

import argparse
import json
import math
import statistics
from pathlib import Path

import cv2

from pilot.combat import FRONT_DEGREES, Fight, nearest_red, readable
from pilot.minimap import read
from pilot.skills import Observation


def intervals(rows, key, start, end):
    active, since = False, None
    spans = []
    for row in rows:
        time = row["t"]
        if time > end:
            break
        value = key in row["buttons"] if key in ("r1", "circle") else row[key] > 0.5
        if value and not active:
            since = max(start, time)
        if active and not value and time > start:
            spans.append([since, min(time, end)])
        active = value
    if active:
        spans.append([since, end])
    return [span for span in spans if span[1] > span[0]]


def describe(values):
    return {
        "count": len(values),
        "min": min(values) if values else None,
        "median": statistics.median(values) if values else None,
        "max": max(values) if values else None,
        "total": sum(values),
    }


def evaluate(recording, start=0.0, end=130.0):
    frames = [json.loads(line) for line in (recording / "frames.jsonl").read_text().splitlines()]
    pads = [json.loads(line) for line in (recording / "pad.jsonl").read_text().splitlines()]
    spans = {key: intervals(pads, key, start, end) for key in ("l2", "r2", "r1", "circle")}
    rhythm = {}
    for key, values in spans.items():
        rhythm[key] = {
            "holds_seconds": describe([b - a for a, b in values]),
            "gaps_seconds": describe([values[i + 1][0] - values[i][1] for i in range(len(values) - 1)]),
            "intervals": values,
        }
    aim_leads = []
    for begin, finish in spans["l2"]:
        first = next((a for a, _ in spans["r2"] if begin <= a < finish), None)
        if first is not None:
            aim_leads.append(first - begin)
    counts = dict(
        frames=0,
        readable=0,
        corrupt=0,
        red_any=0,
        red_readable=0,
        off_cone=0,
        turns=0,
        correct_turns=0,
        wrong_turns=0,
        front_attacks=0,
        unsafe_attacks=0,
    )
    windows = {"first_attempt_5_31": [5, 31, 0, 0, 0], "retry_43_120": [43, 120, 0, 0, 0]}
    samples = []
    skill = Fight({})
    capture = cv2.VideoCapture(str(recording / "video.mp4"))
    if not capture.isOpened():
        raise ValueError("cannot decode video")
    try:
        for meta in frames:
            if meta["t"] > end:
                break
            ok, frame = capture.read()
            if not ok:
                raise ValueError(f"video ended before frame {meta['i']}")
            if meta["t"] < start:
                continue
            # P12's fixed 720p HUD rectangle; the source recording is 1280x720.
            if frame.shape[:2] != (720, 1280):
                raise ValueError("expected 1280x720 recording")
            reading = read(cv2.cvtColor(frame[530:700, 30:290], cv2.COLOR_BGR2RGB))
            target = nearest_red(reading)
            usable = readable(reading)
            angle = math.degrees(math.atan2(target.x, target.y)) if target else None
            result = skill.step(Observation(reading, None, meta["t"]))
            counts["frames"] += 1
            counts["readable"] += usable
            counts["corrupt"] += reading.corrupt
            counts["red_any"] += target is not None
            counts["red_readable"] += usable and target is not None
            counts["off_cone"] += usable and angle is not None and abs(angle) > FRONT_DEGREES
            if result.pad.right[0]:
                correct = usable and angle is not None and angle * result.pad.right[0] > 0
                counts["turns"] += 1
                counts["correct_turns"] += bool(correct)
                counts["wrong_turns"] += not correct
            if result.pad.r2:
                safe = usable and angle is not None and abs(angle) <= FRONT_DEGREES
                counts["front_attacks"] += bool(safe)
                counts["unsafe_attacks"] += not safe
            for window in windows.values():
                if window[0] <= meta["t"] <= window[1]:
                    window[2] += 1
                    window[3] += usable
                    window[4] += usable and target is not None
            samples.append(
                {
                    "frame": meta["i"],
                    "t": meta["t"],
                    "readable": usable,
                    "red": len([b for b in reading.blips if b.color == "red"]),
                    "nearest_degrees": angle,
                    "turn": result.pad.right[0],
                    "l2": result.pad.l2,
                    "r2": result.pad.r2,
                    "status": result.status,
                    "reason": result.reason,
                }
            )
            if result.status != "running":
                skill = Fight({})
    finally:
        capture.release()
    return {
        "recording": str(recording),
        "window": [start, end],
        "counts": counts,
        "red_fraction_all": counts["red_any"] / counts["frames"] if counts["frames"] else None,
        "red_fraction_readable": counts["red_readable"] / counts["readable"] if counts["readable"] else None,
        "combat_observable_red_fraction_all": counts["red_readable"] / counts["frames"]
        if counts["frames"]
        else None,
        "windows_start_end_all_readable_red": windows,
        "human_rhythm": rhythm,
        "aim_lead_seconds": describe(aim_leads),
        "limitations": (
            "Reader coverage is not ground-truth recall. "
            "Sequential skill replay restarts after each terminal result. "
            "It compares camera-relative steering signs, not counterfactual combat outcomes. "
            "Pad durations use controller timestamps; Wi-Fi picture lags inputs by 0.6-1.1s. "
            "No action/frame timing calibration is claimed."
        ),
        "frames": samples,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path)
    parser.add_argument("--start", type=float, default=0)
    parser.add_argument("--end", type=float, default=130)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 0 <= args.start < args.end or not math.isfinite(args.end):
        parser.error("require 0 <= start < finite end")
    result = evaluate(args.recording, args.start, args.end)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {key: value for key, value in result.items() if key not in ("frames", "human_rhythm")}, indent=2
        )
    )
    print(
        json.dumps(
            {
                key: {k: v for k, v in value.items() if k != "intervals"}
                for key, value in result["human_rhythm"].items()
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
