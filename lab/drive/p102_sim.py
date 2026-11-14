"""P102 serial closed-loop road/profile evidence, with the P98 sensor settings."""

import argparse
import json
import sys
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot/src"))
from p98_replay import baseline
from pilot.cli import drive_config
from pilot.drive import Driver
from pilot.sim import CAR_PROFILES, SimConfig, Simulator, drive_through_roads

ROADS = {
    "junction": ((0.0, 0.0), (0.0, 150.0), (150.0, 150.0)),
    "two-blocks": ((0.0, 0.0), (0.0, 150.0), (150.0, 150.0), (150.0, 300.0)),
    **{k: v for k, v in drive_through_roads().items() if k in {"kilometre", "exit"}},
}


def run(cls, config, road, profile):
    geometry = (
        dict(path_spacing=6.0, path_horizon=90.0)
        if road in {"junction", "two-blocks"}
        else {}
    )
    cfg = SimConfig(
        **CAR_PROFILES[profile],
        **geometry,
        dead_zone=0.25,
        delay=0.14,
        max_time=300,
        gps_wrong=0,
        gps_dropout=0,
        path_missing=0,
        damage_probability=0,
        outlier_probability=0,
        noise_degrees=0.5,
        path_noise=0.15,
    )
    sim = Simulator(ROADS[road], config=cfg)
    driver = cls(config)
    entries = []
    speeds = []
    pulses = []
    lifts = 0.0
    error = 0.0
    last = False
    minimum = 0.0
    corners = (
        [150, 300] if road == "two-blocks" else [150] if road == "junction" else []
    )
    while sim.time < cfg.max_time:
        reading, moving = sim.observe()
        command = driver.step(reading, sim.time, moving, speed=sim.observed_speed)
        distance, progress = sim._route_position()
        error = max(error, distance)
        if len(entries) < len(corners) and progress >= corners[len(entries)] - 5:
            entries.append(round(sim.speed, 3))
        if progress > 50 and sim.length - progress > 25:
            speeds.append(sim.speed)
            if command.brake > 0 and not last:
                pulses.append(
                    [round(sim.time, 3), round(progress, 3), driver.speed_reason]
                )
            if command.throttle == 0:
                lifts += cfg.dt
        last = command.brake > 0
        minimum = min(minimum, sim.speed)
        sim.advance(command)
        if progress >= sim.length - 3:
            break
    return dict(
        reached=progress >= sim.length - 3,
        elapsed=round(sim.time, 3),
        max_error=round(error, 3),
        median_speed=round(median(speeds), 3),
        entry_speeds=entries,
        brake_pulses=len(pulses),
        pulses=pulses,
        lifted_seconds=round(lifts, 3),
        minimum_speed=round(minimum, 3),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", nargs="*", default=list(CAR_PROFILES))
    parser.add_argument("--roads", nargs="*", default=list(ROADS))
    parser.add_argument("--baseline", action="store_true")
    args = parser.parse_args()
    cls, cfg = baseline() if args.baseline else (Driver, drive_config(["style=bold"]))
    rows = []
    for road in args.roads:
        for profile in args.profiles:
            row = dict(road=road, profile=profile, **run(cls, cfg, road, profile))
            rows.append(row)
            print(json.dumps(row), flush=True)
    label = "before" if args.baseline else "after"
    (ROOT / "lab/drive" / f"p102-sim-{label}.json").write_text(
        json.dumps(rows, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
