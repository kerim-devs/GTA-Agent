"""Compare P73 styles in the existing simulator; no console or recording writes."""

import argparse
import json
from dataclasses import asdict
from math import cos, degrees, hypot, sin
from pathlib import Path

from pilot.cli import drive_config
from pilot.contract import Command, Observation
from pilot.drive import Driver
from pilot.objects import Detection
from pilot.sim import CAR_PROFILES, SimConfig, Simulator
from pilot.skills import DriveRoute

SCENARIOS = {
    "town": (((0, 0), (0, 80), (80, 80), (80, 160), (0, 160)), 0),
    "country": (((0, 0), (0, 100), (40, 200), (0, 300)), 0),
    "behind": (((0, 0), (0, 100)), 180),
}


class MeasuredSimulator(Simulator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.travelled = 0.0
        self.standing = self.max_standing = 0.0
        self.aligned_at = None

    def advance(self, command):
        before = self.x, self.y
        super().advance(command)
        self.travelled += hypot(self.x - before[0], self.y - before[1])
        if abs(self.speed) <= 0.5 and not command.state.startswith(("recovery", "turn-", "bypass-")):
            self.standing += self.config.dt
            self.max_standing = max(self.max_standing, self.standing)
        else:
            self.standing = 0.0
        if self.aligned_at is None and abs((degrees(self.heading) + 180) % 360 - 180) <= 30:
            self.aligned_at = self.time


def matrix():
    rows = []
    for profile, physics in CAR_PROFILES.items():
        for name, (route, heading) in SCENARIOS.items():
            for style in ("careful", "bold"):
                config = drive_config([f"style={style}"])
                sim = MeasuredSimulator(
                    route,
                    heading=heading,
                    config=SimConfig(max_time=120, **physics),
                    seed=0,
                )
                result = sim.run(Driver(config))
                row = {
                    "profile": profile,
                    "scenario": name,
                    "style": style,
                    **asdict(result),
                    "travelled_metres": sim.travelled,
                    "recoveries_per_km": result.recoveries * 1000 / max(sim.travelled, 1e-9),
                    "max_standing_outside_recovery": sim.max_standing,
                    "aligned_at": sim.aligned_at if name == "behind" else None,
                    "final_distance_to_destination": hypot(sim.x - route[-1][0], sim.y - route[-1][1]),
                }
                rows.append(row)
                print(json.dumps(row), flush=True)
    return rows


def box(sim, rear, x=0.0):
    """Project the same 1.8 m car used by the P73 queue world."""
    dx, dy = x - sim.x, rear - sim.y
    ahead = dx * sin(sim.heading) + dy * cos(sim.heading)
    side = dx * cos(sim.heading) - dy * sin(sim.heading)
    if ahead < 0.5:
        return ()
    pixels = 0.24 * 1280 * 5 / (ahead + 5)
    centre = 640 + side / 1.8 * pixels
    return (Detection("car", (centre - pixels / 2, 430 - pixels / 1.25, centre + pixels / 2, 430), 0.9),)


def parked(profile, gap, blocked=0, seconds=12):
    cfg = SimConfig(
        **CAR_PROFILES[profile],
        noise_degrees=0,
        noise_tail_probability=0,
        outlier_probability=0,
        damage_probability=0,
        path_noise=0,
        path_missing=0,
        speed_noise=0,
        speed_missing=0,
        gps_wrong=0,
        gps_dropout=0,
        max_time=seconds,
    )
    rear = gap
    walls = [((-0.9, rear), (0.9, rear))]
    if blocked:
        walls.append(((blocked * 3 - 0.9, rear), (blocked * 3 + 0.9, rear)))
    sim = Simulator([(0, 0), (0, 500)], config=cfg, walls=walls)
    skill = DriveRoute({"duration": 120, "style": "bold"})
    stopped = passed = None
    phases = []
    queue_started = reverse_started = reverse_start_y = reverse_distance = None
    first_side = None
    rolled = stopped_after_rolling = False
    longest_reverse = 0.0
    reverse_at = None
    while sim.time < seconds:
        reading, moving = sim.observe()
        objects = box(sim, rear)
        if blocked:
            objects += box(sim, rear, blocked * 3)
        result = skill.step(Observation(reading, moving, sim.time, objects=objects, objects_time=sim.time))
        state = skill.driver._last.state
        if state == "bypass-wait" and queue_started is None:
            queue_started = sim.time
        if state == "bypass-reverse":
            if reverse_started is None:
                reverse_started, reverse_start_y = sim.time, sim.y
            if reverse_at is None:
                reverse_at = sim.time
            longest_reverse = max(longest_reverse, sim.time - reverse_at)
        elif reverse_at is not None:
            longest_reverse = max(longest_reverse, sim.time - reverse_at)
            reverse_at = None
        if state == "bypass-forward" and first_side is None:
            first_side = result.pad.left[0]
            reverse_distance = reverse_start_y - sim.y
        if abs(sim.speed) > 0.5:
            rolled = True
        elif rolled and not state.startswith(("bypass-", "turn-", "recovery")):
            stopped_after_rolling = True
        if not phases or phases[-1][1] != state:
            phases.append((round(sim.time, 3), state))
        if stopped is None and moving is False:
            stopped = sim.time
        if sim.y > rear + 2:
            passed = sim.time
            break
        if result.status != "running":
            break
        sim.advance(Command(result.pad.left[0], result.pad.r2, result.pad.l2, state))
    return dict(
        profile=profile,
        gap=gap,
        blocked=blocked,
        passed_at=passed,
        first_stationary=stopped,
        after_wait=None if passed is None or reverse_started is None else passed - reverse_started,
        queue_started=queue_started,
        reverse_started=reverse_started,
        reverse_distance=reverse_distance,
        longest_reverse=longest_reverse,
        first_side=first_side,
        stopped_after_rolling=stopped_after_rolling,
        collisions=sim.collisions,
        position=[sim.x, sim.y],
        phases=phases,
        status=result.status,
        reason=result.reason,
    )


def parked_matrix():
    rows = []
    for profile in CAR_PROFILES:
        for gap in (2, 4, 7, 12):
            for blocked in (0, -1, 1) if gap < 12 else (0,):
                row = parked(profile, gap, blocked)
                rows.append(row)
                print(json.dumps(row), flush=True)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--only", choices=("routes", "parked"))
    args = parser.parse_args()
    rows = matrix() if args.only != "parked" else []
    parked_rows = parked_matrix() if args.only != "routes" else []
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps({"evidence": "simulator", "rows": rows, "parked": parked_rows}, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
