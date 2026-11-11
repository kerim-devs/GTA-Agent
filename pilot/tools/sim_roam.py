"""Exercise the real road reader and skill on rendered road networks with delayed car physics."""

import argparse
import json
import math
import random
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np

from pilot.contract import HUD_RECT, NEUTRAL_PAD, Command, Reading
from pilot.minimap import ARROW_XY, MX0, MX1, MY0, MY1
from pilot.roam import DriveFree
from pilot.sim import SimConfig, Simulator
from pilot.skills import Observation


@dataclass
class Result:
    seed: int
    scenario: str
    pace: str
    elapsed: float
    road_fraction: float
    driven_seconds: float
    distance: float
    collisions: int
    reverse_seconds: float
    escaped: bool
    bounded: bool
    neutral: bool
    status: str
    reason: str
    zoom_min: float
    zoom_max: float
    final_position: tuple[float, float]


def network():
    loop = []
    for cx, cy, start in ((20, 60, 180), (80, 60, 90), (80, 0, 0), (20, 0, -90)):
        for angle in np.linspace(start, start - 90, 19):
            loop.append((cx + 20 * math.cos(math.radians(angle)), cy + 20 * math.sin(math.radians(angle))))
    loop.append(loop[0])
    return [loop, [(0, 35), (55, 35), (55, 80)], [(80, 80), (80, 105)]]


def road_distance(x, y, roads):
    best = math.inf
    for road in roads:
        a, b = np.array(road[:-1]), np.array(road[1:])
        delta = b - a
        fraction = np.clip(((np.array([x, y]) - a) * delta).sum(axis=1) / (delta * delta).sum(axis=1), 0, 1)
        best = min(
            best, float(np.linalg.norm(np.array([x, y]) - (a + delta * fraction[:, None]), axis=1).min())
        )
    return best


def picture(sim, roads, rng, blind):
    scale = sim.map_scale
    crop = np.full((170, 260, 3), 65, np.uint8)
    cosine, sine = math.cos(sim.camera_heading), math.sin(sim.camera_heading)
    offset = rng.gauss(0, 0.35), rng.gauss(0, 0.35)
    for road in roads:
        points = []
        for x, y in road:
            rx, ry = (x - sim.x) / scale, (y - sim.y) / scale
            px, py = rx * cosine - ry * sine, rx * sine + ry * cosine
            points.append((round(ARROW_XY[0] + px + offset[0]), round(ARROW_XY[1] - py + offset[1])))
        shade = rng.randint(205, 240)
        cv2.polylines(
            crop, [np.array(points, np.int32)], False, (shade, shade, shade), max(2, round(7 / scale))
        )
    crop[:MY0] = 65
    crop[MY1:] = 65
    crop[:, :MX0] = 65
    crop[:, MX1:] = 65
    arrow = math.degrees(sim.heading - sim.camera_heading)
    reading = Reading("tilted", "none", None, None, arrow + rng.gauss(0, 0.8), blind, 0.9)
    x, y, w, h = HUD_RECT
    frame = np.zeros((720, 1280, 3), np.uint8)
    frame[y : y + h, x : x + w] = crop
    return reading, frame


def run(seed, scenario="network", pace="normal", seconds=45.0):
    rng = random.Random(seed)
    roads = network()
    if scenario == "dead-end":
        roads = [[(0, -25), (0, 26)], [(-30, 14), (30, 14)]]
    elif scenario == "blocked":
        roads = [[(0, -25), (0, 120)]]
    walls = (((-3.5, 25), (3.5, 25)),) if scenario in ("dead-end", "blocked") else ()
    config = SimConfig(
        delay=0.14,
        sensor_delay=0.06,
        max_time=seconds,
        grip=rng.uniform(3.5, 5),
        acceleration=rng.uniform(4, 5),
        drag=rng.uniform(0.4, 0.5),
        dead_zone=rng.uniform(0, 0.05),
    )
    start_y = 19 if scenario == "dead-end" else 0
    sim = Simulator(
        roads[0], position=(rng.uniform(-0.5, 0.5), start_y), config=config, walls=walls, seed=seed
    )
    if scenario == "zoom":
        sim.speed = 9.0
    skill = DriveFree({"seconds": seconds, "pace": pace, "turn": "any"})
    queue = deque()
    driven = on_road = travel = reversing = 0.0
    escaped = False
    peak_y = sim.y
    minimum_scale = maximum_scale = sim.map_scale
    last_position = sim.x, sim.y
    result = None
    for _ in range(math.ceil(seconds / config.dt) + 2):
        blind = rng.random() < 0.04 or (scenario == "blind" and sim.time >= 6)
        reading, frame = picture(sim, roads, rng, blind)
        moving = None if blind or rng.random() < 0.02 else abs(sim.speed) > 0.25
        queue.append((sim.time, reading, frame, moving))
        sensor_age = 0.06 + (0.10 if rng.random() < 0.08 else 0)
        while len(queue) > 1 and queue[1][0] <= sim.time - 0.20:
            queue.popleft()
        observed = min(queue, key=lambda item: abs(item[0] - (sim.time - sensor_age)))
        # Tick time is current; the image and motion were captured earlier.
        result = skill.step(Observation(observed[1], observed[3], sim.time, observed[2]))
        if result.status != "running":
            break
        pad = result.pad
        sim.advance(Command(pad.left[0], pad.r2, pad.l2, "recovery-reverse" if pad.l2 else "follow"))
        step_distance = math.dist(last_position, (sim.x, sim.y))
        travel += step_distance
        last_position = sim.x, sim.y
        if abs(sim.speed) > 0.25:
            driven += config.dt
            on_road += config.dt * (road_distance(sim.x, sim.y, roads) <= 3.5)
        reversing += config.dt * (pad.l2 > 0)
        peak_y = max(peak_y, sim.y)
        if scenario == "dead-end" and sim.y < 14 and sim.y < peak_y - 5 and abs(sim.x) > 5:
            escaped = True
        minimum_scale = min(minimum_scale, sim.map_scale)
        maximum_scale = max(maximum_scale, sim.map_scale)
    return Result(
        seed,
        scenario,
        pace,
        round(sim.time, 3),
        on_road / max(driven, 1e-9),
        round(driven, 3),
        round(travel, 3),
        sim.collisions,
        round(reversing, 3),
        escaped,
        result.status != "running" and sim.time <= seconds + config.dt + 1e-9,
        result.pad == NEUTRAL_PAD,
        result.status,
        result.reason or "",
        minimum_scale,
        maximum_scale,
        (round(sim.x, 3), round(sim.y, 3)),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--seconds", type=float, default=45)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 120 or args.seeds < 1:
        parser.error("seconds must be in [1,120] and seeds positive")
    results = [
        run(seed, scenario, seconds=args.seconds)
        for scenario in ("network", "dead-end", "blind", "zoom", "blocked")
        for seed in range(args.seeds)
    ]
    normal = [r for r in results if r.scenario == "network"]
    summary = {
        "runs": len(results),
        "normal_road_fraction": sum(r.road_fraction * r.driven_seconds for r in normal)
        / max(1e-9, sum(r.driven_seconds for r in normal)),
        "normal_min_road_fraction": min(r.road_fraction for r in normal),
        "normal_min_distance": min(r.distance for r in normal),
        "normal_min_elapsed": min(r.elapsed for r in normal),
        "dead_end_escapes": sum(r.escaped for r in results if r.scenario == "dead-end"),
        "all_bounded": all(r.bounded for r in results),
        "all_terminal_neutral": all(r.neutral for r in results),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps({"summary": summary, "results": [asdict(r) for r in results]}, indent=2) + "\n"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
