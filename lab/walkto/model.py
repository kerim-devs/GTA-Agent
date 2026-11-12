"""Deterministic geometry model; real FootGuard with modelled perception outputs."""

import json
import math
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pilot.contract import Blip, Observation, Reading
from pilot.foot import FootGuard
from pilot.walkto import WalkTo


class ModelGuard(FootGuard):
    def _evidence(self, observation):
        return "going" if observation.moving else "still"


def road_at(position, points):
    best = None
    for a, b in zip(points, points[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = dx * dx + dy * dy
        t = max(0, min(1, ((position[0] - a[0]) * dx + (position[1] - a[1]) * dy) / length))
        x, y = a[0] + t * dx - position[0], a[1] + t * dy - position[1]
        distance = math.hypot(x, y)
        road = SimpleNamespace(
            distance=distance, bearing=math.degrees(math.atan2(x, y)), along=math.degrees(math.atan2(dx, dy))
        )
        if best is None or distance < best.distance:
            best = road
    return best


CASES = {
    "open ground": {"goal": (60, 70)},
    "block": {"goal": (70, 80), "blocks": [(15, 25, 65, 65)], "road": [(0, 0), (0, 72), (70, 72), (70, 90)]},
    "blocks with gap": {
        "goal": (65, 95),
        "blocks": [(-100, 30, 45, 55), (60, 30, 180, 55)],
        "road": [(0, 0), (52, 20), (52, 90), (65, 95)],
    },
    "river and bridge": {
        "goal": (65, 90),
        "blocks": [(-200, 35, 45, 50), (58, 35, 200, 50)],
        "road": [(0, 0), (52, 25), (52, 85), (65, 90)],
    },
    "rim comes inside": {"goal": (60, 180)},
    "vanishing blip": {"goal": (60, 100), "vanish": 3.0},
    "enters car": {"goal": (60, 100), "car": 3.0},
}


def run_case(case, fallback):
    skill = WalkTo({"duration": 90})
    skill.ROAD_FALLBACK = fallback
    skill.guard = ModelGuard()
    position = [0.0, 0.0]
    moving = True
    goal = case["goal"]
    roads = case.get("road", [(0, 0), goal])
    dt = 0.1
    result = None
    for tick in range(902):
        now = tick * dt
        x, y = goal[0] - position[0], goal[1] - position[1]
        distance = math.hypot(x, y)
        border = distance > 70
        scale = min(1, 70 / max(distance, 0.001))
        blips = () if now >= case.get("vanish", math.inf) else (Blip("purple", x * scale, y * scale, border),)
        mode = "vehicle" if now >= case.get("car", math.inf) else "foot"
        reading = Reading("flat", "none", None, None, 0, False, 1.0, blips=blips)
        observation = Observation(reading, moving, now, mode=mode)
        with patch("pilot.walkto.road_position", return_value=road_at(position, roads)):
            result = skill.step(observation)
        if result.status != "running":
            break
        new = [position[0] + result.pad.left[0] * 6 * dt, position[1] - result.pad.left[1] * 6 * dt]
        blocked = any(a <= new[0] <= c and b <= new[1] <= d for a, b, c, d in case.get("blocks", []))
        moving = not blocked and math.dist(new, position) > 0.01
        if not blocked:
            position = new
    return {
        "status": result.status,
        "seconds": round(now, 1),
        "distance": round(math.dist(position, goal), 2),
        "road_entries": skill.road_entries,
        "reason": result.reason,
    }


def main():
    results = {
        name: {"direct": run_case(case, False), "road": run_case(case, True)} for name, case in CASES.items()
    }
    output = {
        "perception": "Synthetic blips and nearest-road geometry; real FootGuard state machine with model motion evidence. No game physics or image perception claim.",
        "cases": results,
    }
    print(json.dumps(output, indent=2))
    Path(__file__).with_name("model-results.json").write_text(json.dumps(output, indent=2) + "\n")


if __name__ == "__main__":
    main()
