"""Offline camera-relative plane simulation; never connects to a controller."""

from __future__ import annotations

import json
import math
from collections import deque
from dataclasses import asdict
from itertools import pairwise
from pathlib import Path

import numpy as np

from pilot.contract import NEUTRAL_PAD, Blip, Reading
from pilot.head import SkillCall
from pilot.skills import Observation, Skill


def simulate(name: str, seed: int, *, wall: str = "none", angle: float = 75, missing: bool = False) -> dict:
    rng = np.random.default_rng(seed)
    skill = Skill(SkillCall(name, {"color": "blue", "duration": 10 if name == "walk_to" else 5}))
    position = np.zeros(2)
    target = (
        np.array([60.0, 0.0])
        if name == "walk_to"
        else np.array([math.sin(math.radians(angle)), math.cos(math.radians(angle))]) * 50
    )
    heading = 0.0
    history = deque()
    turns = []
    trace = []
    dt, delay = 1 / 30, 0.14
    moving = True
    collisions = 0
    for tick in range(302):
        now = tick * dt
        c, s = math.cos(heading), math.sin(heading)
        delta = target - position
        local = np.array([c * delta[0] - s * delta[1], s * delta[0] + c * delta[1]])
        local += rng.normal(0, 0.35, 2)
        dots = () if missing or rng.random() < 0.1 or 1.0 < now < 1.3 else (Blip("blue", *local),)
        reading = Reading("flat", "none", None, None, 0, False, 1, blips=dots)
        history.append((now, reading, moving))
        while len(history) > 1 and history[1][0] <= now - delay:
            history.popleft()
        observed = history[0]
        result = skill.step(Observation(observed[1], observed[2], now))
        trace.append(
            {
                "t": round(now, 4),
                "position": position.tolist(),
                "heading": math.degrees(heading),
                "pad": asdict(result.pad),
                "status": result.status,
            }
        )
        if result.status != "running":
            assert result.pad == NEUTRAL_PAD
            break
        if result.pad.right[0]:
            turns.append(math.copysign(1, result.pad.right[0]))
        heading += math.radians(result.pad.right[0] * 120) * dt
        x, y = result.pad.left
        change = np.array([c * x - s * y, -s * x - c * y]) * 25 * dt
        proposed = position + change
        extent = 2 if wall == "corner" else 100
        blocked = wall != "none" and 20 <= proposed[0] <= 23 and abs(proposed[1]) <= extent
        if blocked:
            collisions += 1
        else:
            position = proposed
        moving = not blocked and np.linalg.norm(change) > 0.01
    angular_error = abs(
        (math.degrees(math.atan2(target[0] - position[0], target[1] - position[1]) - heading) + 180) % 360
        - 180
    )
    return {
        "name": name,
        "seed": seed,
        "wall": wall,
        "initial_angle": angle,
        "missing": missing,
        "status": result.status,
        "reason": result.reason,
        "seconds": now,
        "distance": float(np.linalg.norm(target - position)),
        "angle_error": angular_error,
        "turn_reversals": sum(a != b for a, b in pairwise(turns)),
        "recoveries": skill.recoveries,
        "collisions": collisions,
        "trace": trace,
    }


def main() -> None:
    results = []
    for seed in range(20):
        for wall in ("none", "corner", "sealed"):
            result = simulate("walk_to", seed, wall=wall)
            assert result["seconds"] <= 10
            assert result["status"] in ("done", "failed")
            if result["status"] == "done":
                assert result["distance"] <= 6
            if wall == "none":
                assert result["status"] == "done"
            if wall == "sealed":
                assert result["status"] == "failed"
            results.append(result)
        for angle in (-179, -90, -20, 20, 90, 179):
            result = simulate("face", seed, angle=angle)
            brief = {k: v for k, v in result.items() if k != "trace"}
            assert result["status"] == "done", brief
            assert result["angle_error"] <= 11, brief
            assert result["turn_reversals"] == 0, brief
            assert result["seconds"] <= 5
            results.append(result)
    for name in ("walk_to", "face"):
        result = simulate(name, 0, missing=True)
        assert result["status"] == "failed" and result["reason"] == "blip-gone"
        results.append(result)
    output = Path(__file__).resolve().parents[2] / "lab/blips"
    output.mkdir(exist_ok=True, parents=True)
    (output / "skill-simulation.json").write_text(json.dumps(results, indent=2) + "\n")
    summary = []
    for name, wall in (("walk_to", "none"), ("walk_to", "corner"), ("walk_to", "sealed"), ("face", "none")):
        group = [r for r in results if r["name"] == name and r["wall"] == wall and not r["missing"]]
        summary.append(
            {
                "skill": name,
                "wall": wall,
                "runs": len(group),
                "done": sum(r["status"] == "done" for r in group),
                "failed": sum(r["status"] == "failed" for r in group),
                "max_seconds": max(r["seconds"] for r in group),
                "max_turn_reversals": max(r["turn_reversals"] for r in group),
            }
        )
    (output / "skill-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
