"""Offline P23 experiment; world-distance hits are independent of box thresholds.

All movement, camera, reach and detector constants below are estimates, not
console measurements. No controller, network, model or gameplay connection.
"""

import argparse
import json
import random
import sys
from collections import Counter, deque
from dataclasses import asdict, dataclass
from math import atan2, cos, hypot, pi, radians, sin, tan
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pilot.contract import NEUTRAL_PAD, Detection, Hud, Pad, Reading
from pilot.punch import Punch
from pilot.skills import Observation


@dataclass(frozen=True)
class Assumptions:
    horizontal_fov: float = 70.0
    turn_degrees_per_second: float = 120.0
    camera_back: float = 0.8
    camera_height: float = 1.5
    walk_metres_per_second: float = 3.0
    person_height: float = 1.7
    person_width: float = 0.5
    punch_reach: float = 1.6
    punch_cone_degrees: float = 25.0
    walking_speed: float = 1.4
    runaway_speed: float = 4.0
    command_to_picture: float = 0.14
    detector_period: float = 0.1
    detector_delay_min: float = 0.04
    detector_delay_max: float = 0.16
    box_jitter: float = 0.006
    miss_probability: float = 0.12
    false_probability: float = 0.04
    tick: float = 1 / 30


MODEL = Assumptions()
CASES = ("standing", "walking", "runaway", "two_people", "nobody", "player_leak")
SCALES = (0.5, 1.0, 2.0)


def project(player, target, fov_scale, rng):
    x, z, yaw = player
    dx, dz = target[0] - x, target[1] - z
    side = cos(yaw) * dx - sin(yaw) * dz
    depth = sin(yaw) * dx + cos(yaw) * dz + MODEL.camera_back
    if depth <= 0.2:
        return None
    focal = 0.5 / tan(radians(MODEL.horizontal_fov * fov_scale) / 2)
    cx = 0.5 + focal * side / depth
    bottom = 0.5 + focal * (16 / 9) * MODEL.camera_height / depth
    top = bottom - focal * (16 / 9) * MODEL.person_height / depth
    half_width = focal * MODEL.person_width / (2 * depth)
    box = (cx - half_width, top, cx + half_width, bottom)
    if box[2] <= 0 or box[0] >= 1 or box[3] <= 0 or box[1] >= 1:
        return None
    values = [max(0, min(1, v + rng.uniform(-1, 1) * MODEL.box_jitter)) for v in box]
    if values[2] <= values[0] or values[3] <= values[1]:
        return None
    return Detection("person", tuple(v * s for v, s in zip(values, (1280, 720, 1280, 720), strict=True)), 0.9)


def in_reach(player, target):
    dx, dz = target[0] - player[0], target[1] - player[1]
    angle = (atan2(dx, dz) - player[2] + pi) % (2 * pi) - pi
    return hypot(dx, dz) <= MODEL.punch_reach and abs(angle) <= radians(MODEL.punch_cone_degrees)


def run(case, seed, fov_scale, turn_scale):
    rng = random.Random(seed)
    skill = Punch({})
    player = [0.0, 0.0, rng.uniform(-0.10, 0.10)]
    targets = [] if case == "nobody" else [[rng.uniform(-0.45, 0.45), rng.uniform(5, 7)]]
    if case == "two_people":
        targets.append([targets[0][0] + 1.4, targets[0][1] + 0.5])
    hits = [0 for _ in targets]
    delivered = ()
    stamp = None
    pending = deque()
    next_capture = 0.0
    missed_results = 0
    false_results = 0
    applied = NEUTRAL_PAD
    previously_pressed = False
    attempts = []
    result = None
    for tick in range(int((skill.limit + MODEL.tick * 2) / MODEL.tick) + 1):
        now = tick * MODEL.tick
        if tick:
            player[2] += radians(MODEL.turn_degrees_per_second * turn_scale) * applied.right[0] * MODEL.tick
            speed = -applied.left[1] * MODEL.walk_metres_per_second
            player[0] += sin(player[2]) * speed * MODEL.tick
            player[1] += cos(player[2]) * speed * MODEL.tick
            if case == "walking":
                targets[0][0] += MODEL.walking_speed * MODEL.tick
            if case == "runaway" and hits[0]:
                dx, dz = targets[0][0] - player[0], targets[0][1] - player[1]
                distance = max(hypot(dx, dz), 0.001)
                targets[0][0] += dx / distance * MODEL.runaway_speed * MODEL.tick
                targets[0][1] += dz / distance * MODEL.runaway_speed * MODEL.tick
        if now + 1e-9 >= next_capture:
            next_capture += MODEL.detector_period
            boxes = []
            for target in targets:
                box = project(player, target, fov_scale, rng)
                if rng.random() < MODEL.miss_probability:
                    missed_results += 1
                elif box is not None:
                    boxes.append(box)
            if case == "player_leak":
                boxes.append(Detection("person", (400, 280, 760, 719), 0.95))
            if rng.random() < MODEL.false_probability:
                false_results += 1
                cx = rng.uniform(120, 1160)
                boxes.append(Detection("person", (cx - 20, 260, cx + 20, 340), 0.55))
            ready = (
                now
                + MODEL.command_to_picture
                + rng.uniform(MODEL.detector_delay_min, MODEL.detector_delay_max)
            )
            pending.append((ready, now, tuple(boxes)))
        # Variable latency can reorder frames. The consumer receives capture time.
        ready = sorted((item for item in pending if item[0] <= now), key=lambda item: item[0])
        pending = deque(item for item in pending if item[0] > now)
        if ready:
            _, stamp, delivered = ready[-1]
        observation = Observation(
            Reading("flat", "none", None, None, None, False, 1.0),
            bool(applied.left[1]),
            now,
            objects=delivered,
            objects_time=stamp,
            hud=Hud(health=1.0),
        )
        result = skill.step(observation)
        pad = result.pad
        assert pad.r2 == 0 and set(pad.buttons) <= {"circle"}
        if pad.l2 or pad.buttons:
            assert pad.left == (0, 0)
        pressed = "circle" in pad.buttons
        if pressed and not previously_pressed:
            reachable = [index for index, target in enumerate(targets) if in_reach(player, target)]
            selected = min(
                reachable,
                key=lambda i: hypot(targets[i][0] - player[0], targets[i][1] - player[1]),
                default=None,
            )
            if selected is not None:
                hits[selected] += 1
            attempts.append(
                {
                    "seconds": round(now, 3),
                    "in_reach": selected is not None,
                    "person": selected,
                    "nearest_distance": round(
                        min((hypot(t[0] - player[0], t[1] - player[1]) for t in targets), default=0.0), 3
                    ),
                }
            )
        previously_pressed = pressed
        applied = pad
        if result.status != "running":
            assert pad == NEUTRAL_PAD and result.reason
            assert skill.step(observation).pad == NEUTRAL_PAD
            break
    assert result.status != "running", "skill exceeded its time bound"
    success = max(hits, default=0) >= skill.hits
    return {
        "case": case,
        "seed": seed,
        "fov_scale": fov_scale,
        "turn_scale": turn_scale,
        "status": result.status,
        "reason": result.reason,
        "seconds": round(now, 3),
        "requested_hits": skill.hits,
        "hits_per_person": hits,
        "hits_delivered_in_reach": success,
        "failure": None
        if success
        else ("skill completed with out-of-reach attempts" if result.status == "done" else result.reason),
        "attempts": attempts,
        "missed_detections": missed_results,
        "false_detections": false_results,
        "neutral_terminal": result.pad == Pad(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=10)
    parser.add_argument("--output", type=Path, default=Path("../lab/punch/results.json"))
    args = parser.parse_args()
    if args.seeds < 10:
        parser.error("at least 10 seeds are required for the acceptance experiment")
    runs = [
        run(case, seed, fov, turn)
        for case in CASES
        for fov in SCALES
        for turn in SCALES
        for seed in range(args.seeds)
    ]
    summaries = []
    for case in CASES:
        for fov in SCALES:
            for turn in SCALES:
                group = [r for r in runs if (r["case"], r["fov_scale"], r["turn_scale"]) == (case, fov, turn)]
                success_count = sum(r["hits_delivered_in_reach"] for r in group)
                summary = {
                    "case": case,
                    "fov_scale": fov,
                    "turn_scale": turn,
                    "successes": success_count,
                    "runs": len(group),
                    "mean_seconds": round(sum(r["seconds"] for r in group) / len(group), 3),
                    "max_seconds": max(r["seconds"] for r in group),
                    "failures": dict(Counter(r["failure"] for r in group if r["failure"])),
                    "all_bounded_neutral": all(
                        r["neutral_terminal"] and r["seconds"] <= 15 + MODEL.tick for r in group
                    ),
                }
                summaries.append(summary)
                print(json.dumps(summary, sort_keys=True))
    accepted = all(
        s["all_bounded_neutral"]
        and (s["case"] not in {"standing", "walking"} or s["successes"] >= 0.8 * s["runs"])
        for s in summaries
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "assumptions": asdict(MODEL),
                "acceptance_passed": accepted,
                "summaries": summaries,
                "runs": runs,
            },
            indent=2,
        )
        + "\n"
    )
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
