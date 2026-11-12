"""Offline pinhole/latency model. No Remote Play or detector dependencies."""

import argparse
import json
import math
import random
import statistics
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from pilot.contract import NEUTRAL_PAD, Detection, Reading
from pilot.skills import Observation
from pilot.vehicle_entry import EnterVehicle


@dataclass(frozen=True)
class Assumptions:
    horizontal_fov: float = 70.0
    turn_degrees_per_second: float = 120.0
    aspect: float = 16 / 9
    camera_back: float = 0.8
    camera_height: float = 1.5
    walk_metres_per_second: float = 3.0
    entry_reach: float = 2.8
    command_to_picture: float = 0.14
    detector_period: float = 0.1
    detector_delay_min: float = 0.04
    detector_delay_max: float = 0.16
    box_jitter: float = 0.008
    miss_probability: float = 0.12
    false_probability: float = 0.04
    tick: float = 1 / 30


MODEL = Assumptions()


def reading(tilted=False, corrupt=False):
    return Reading("tilted" if tilted else "flat", "none", None, None, None, corrupt, 1.0)


def pixels(box):
    return (box[0] * 1280, box[1] * 720, box[2] * 1280, box[3] * 720)


def project(x, z, yaw, vehicles, rng, fov_scale):
    focal = 0.5 / math.tan(math.radians(MODEL.horizontal_fov * fov_scale) / 2)
    boxes = []
    for vx, vz, kind in vehicles:
        dx, dz = vx - x, vz - z
        side = math.cos(yaw) * dx - math.sin(yaw) * dz
        depth = math.sin(yaw) * dx + math.cos(yaw) * dz + MODEL.camera_back
        if depth <= 0.2:
            continue
        width, height = (1.8, 1.5) if kind == "car" else (0.8, 1.3)
        cx = 0.5 + focal * side / depth
        bottom = 0.5 + focal * MODEL.aspect * MODEL.camera_height / depth
        top = bottom - focal * MODEL.aspect * height / depth
        half = focal * width / (2 * depth)
        raw = (cx - half, top, cx + half, bottom)
        if raw[2] <= 0 or raw[0] >= 1 or raw[1] >= 1:
            continue
        if rng.random() < MODEL.miss_probability:
            continue
        box = tuple(max(0.0, min(1.0, v + rng.uniform(-MODEL.box_jitter, MODEL.box_jitter))) for v in raw)
        if box[0] < box[2] and box[1] < box[3]:
            boxes.append(Detection(kind, pixels(box), 0.9))
    if rng.random() < MODEL.false_probability:
        cx = rng.uniform(0.1, 0.9)
        boxes.append(Detection("car", pixels((cx - 0.03, 0.48, cx + 0.03, 0.57)), 0.65))
    rng.shuffle(boxes)
    return tuple(boxes)


def run(seed, scenario="parked", fov_scale=1.0, turn_scale=1.0):
    rng = random.Random(seed)
    skill = EnterVehicle({})
    x = z = 0.0
    yaw = math.radians(rng.uniform(-0.28, 0.28) * MODEL.horizontal_fov * fov_scale)
    distance = rng.uniform(3.0, 10.0)
    vehicles = [] if scenario in {"empty", "no_delivery"} else [(0.0, distance, "car")]
    # A second parked vehicle and a crossing vehicle exercise association/selection.
    if scenario == "parked":
        vehicles += [(4.0, distance + 5.0, "car"), (-8.0, distance + 8.0, "motorcycle")]
    deliveries = deque()
    pictures = deque()
    latest_objects, latest_time = (), None
    latest_reading = reading()
    next_detection = 0.0
    entry_at = None
    entered = False
    cancellations = 0
    presses = 0
    wait_stick_violations = 0
    max_stick_run = stick_run = 0.0
    for tick in range(math.ceil(26 / MODEL.tick)):
        now = tick * MODEL.tick
        if scenario == "away":
            vehicles = [(0.0, distance + 7.0 * now, "car")]
        elif scenario == "parked":
            vehicles[-1] = (-8.0 + 0.6 * now, distance + 8.0, "motorcycle")
        if entry_at is not None and now >= entry_at:
            entered = True
        pictures.append((now + MODEL.command_to_picture, reading(entered)))
        while pictures and pictures[0][0] <= now:
            _, latest_reading = pictures.popleft()
        if now >= next_detection and scenario != "no_delivery":
            boxes = project(x, z, yaw, vehicles, rng, fov_scale)
            delay = rng.uniform(MODEL.detector_delay_min, MODEL.detector_delay_max)
            deliveries.append((now + MODEL.command_to_picture + delay, now, boxes))
            next_detection = now + MODEL.detector_period
        # Complete in delivery order, reject late packets older than the latest capture.
        ready = [packet for packet in deliveries if packet[0] <= now]
        deliveries = deque(packet for packet in deliveries if packet[0] > now)
        for _, capture, boxes in sorted(ready):
            if latest_time is None or capture >= latest_time:
                latest_objects, latest_time = boxes, capture
        previous_phase = skill.phase
        result = skill.step(
            Observation(latest_reading, False, now, objects=latest_objects, objects_time=latest_time)
        )
        pad = result.pad
        sticks = pad.left != (0, 0) or pad.right != (0, 0)
        stick_run = stick_run + MODEL.tick if sticks else 0.0
        max_stick_run = max(max_stick_run, stick_run)
        if previous_phase == "wait" and skill.phase == "wait" and sticks:
            wait_stick_violations += 1
        if result.status != "running":
            assert pad == NEUTRAL_PAD
            assert skill.step(Observation(reading(), False, now + 1)).pad == NEUTRAL_PAD
            return {
                "seed": seed,
                "scenario": scenario,
                "fov_scale": fov_scale,
                "turn_scale": turn_scale,
                "status": result.status,
                "reason": result.reason,
                "seconds": round(now, 3),
                "presses": presses,
                "cancellations": cancellations,
                "wait_stick_violations": wait_stick_violations,
                "max_stick_run": round(max_stick_run, 3),
                "terminal_neutral": True,
            }
        if entry_at is not None and not entered and sticks:
            entry_at = None
            cancellations += 1
        if "triangle" in pad.buttons:
            presses += 1
            near = any(math.hypot(vx - x, vz - z) <= MODEL.entry_reach for vx, vz, _ in vehicles)
            if near and not sticks and scenario != "locked":
                entry_at = now + rng.uniform(0.8, 2.2)
        if not entered:
            yaw += math.radians(MODEL.turn_degrees_per_second * turn_scale) * pad.right[0] * MODEL.tick
            speed = -pad.left[1] * MODEL.walk_metres_per_second
            x += math.sin(yaw) * speed * MODEL.tick
            z += math.cos(yaw) * speed * MODEL.tick
    raise AssertionError("skill exceeded its hard limit")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=100)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.seeds < 10:
        parser.error("use at least 10 seeds")
    results = []
    summaries = []
    cases = [("parked", fov, turn) for fov in (0.5, 1.0, 2.0) for turn in (0.5, 1.0, 2.0)]
    cases += [(scenario, 1.0, 1.0) for scenario in ("empty", "away", "no_delivery", "locked")]
    passed = True
    for scenario, fov, turn in cases:
        rows = [run(seed, scenario, fov, turn) for seed in range(args.seeds)]
        results.extend(rows)
        successes = [r for r in rows if r["status"] == "done"]
        valid = all(
            r["seconds"] <= 25 and r["reason"] and r["terminal_neutral"] and not r["wait_stick_violations"]
            for r in rows
        )
        valid &= len(successes) >= 0.9 * args.seeds if scenario == "parked" else not successes
        passed &= valid
        summary = {
            "scenario": scenario,
            "fov_scale": fov,
            "turn_scale": turn,
            "successes": len(successes),
            "runs": args.seeds,
            "median_success_seconds": round(statistics.median(r["seconds"] for r in successes), 3)
            if successes
            else None,
            "max_seconds": max(r["seconds"] for r in rows),
            "reasons": {
                reason: sum(r["reason"] == reason for r in rows)
                for reason in sorted({r["reason"] for r in rows})
            },
            "passed": bool(valid),
        }
        summaries.append(summary)
        print(json.dumps(summary))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(
                {
                    "assumptions": MODEL.__dict__,
                    "summaries": summaries,
                    "runs": results,
                    "passed": bool(passed),
                },
                indent=2,
            )
            + "\n"
        )
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
