"""P98 closed-loop comparison on the existing car profiles; no console access."""

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


def run(cls, cfg, road, profile, seed=0):
    sim_cfg = SimConfig(
        **CAR_PROFILES[profile],
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
    sim = Simulator(drive_through_roads()[road], config=sim_cfg, seed=seed)
    driver = cls(cfg)
    speeds = []
    throttles = []
    brakes = 0
    last_brake = False
    errors = []
    reached = False
    min_speed = 0
    approach_brake = None
    corner_speed = []
    states = {}
    while sim.time < sim.config.max_time:
        reading, moving = sim.observe()
        c = driver.step(reading, sim.time, moving, speed=sim.observed_speed)
        states[c.state] = states.get(c.state, 0) + 1
        distance, progress = sim._route_position()
        if progress > 50 and sim.length - progress > 25:
            speeds.append(sim.speed)
            throttles.append(c.throttle)
            brakes += bool(c.brake > 0 and not last_brake)
        last_brake = c.brake > 0
        if road == "exit" and c.brake and approach_brake is None:
            approach_brake = progress
        if road != "kilometre" and 200 < progress < 400:
            corner_speed.append(sim.speed)
        errors.append(distance)
        min_speed = min(min_speed, sim.speed)
        sim.advance(c)
        if progress >= sim.length - 3:
            reached = True
            break
    ceiling = min(sim_cfg.top_speed, sim_cfg.acceleration / sim_cfg.drag)
    return {
        "reached": reached,
        "elapsed": round(sim.time, 3),
        "median_speed": round(median(speeds), 3) if speeds else None,
        "physical_cruise_ceiling": round(ceiling, 3),
        "max_error": round(max(errors), 3),
        "brake_pulses": brakes,
        "mean_pedal": round(sum(throttles) / len(throttles), 3) if throttles else None,
        "minimum_speed": round(min_speed, 3),
        "first_brake_progress": approach_brake,
        "corner_median": round(median(corner_speed), 3) if corner_speed else None,
        "states": states,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profiles", nargs="*", default=list(CAR_PROFILES))
    parser.add_argument("--roads", nargs="*", default=list(drive_through_roads()))
    parser.add_argument("--after-only", action="store_true")
    args = parser.parse_args()
    before, old_cfg = baseline()
    rows = []
    for name in args.roads:
        for profile in args.profiles:
            row = {"road": name, "profile": profile}
            if not args.after_only:
                row["before"] = run(before, old_cfg, name, profile)
            row["after"] = run(Driver, drive_config(["style=bold"]), name, profile)
            rows.append(row)
            print(json.dumps(row), flush=True)
    (ROOT / "lab/drive/p98-sim.json").write_text(json.dumps(rows, indent=2) + "\n")


if __name__ == "__main__":
    main()
