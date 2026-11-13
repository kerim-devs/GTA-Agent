"""Frozen P97 readings and closed-loop turns; no transport or recording writes."""

import argparse
import csv
import gzip
import hashlib
import json
import sys
from collections import Counter
from math import degrees, hypot
from pathlib import Path
from subprocess import check_output
from types import ModuleType

from pilot.cli import drive_config
from pilot.contract import Reading
from pilot.drive import Driver
from pilot.gps import Speedometer
from pilot.sim import CAR_PROFILES, SimConfig, Simulator

HERE = Path(__file__).resolve().parent


def baseline():
    name = "pilot._p99_before"
    module = ModuleType(name)
    sys.modules[name] = module
    source = check_output(
        ["git", "show", "HEAD:pilot/src/pilot/drive.py"], text=True, cwd=HERE
    )
    exec(compile(source, name, "exec"), module.__dict__)  # noqa: S102 - local committed code only
    return module.Driver


def fixture():
    from replay import lines, motion_for_rows

    folder = Path("/Users/kerim/recordings/pilot/20261113-224327")
    rows = lines(folder / "play.jsonl")
    motion = motion_for_rows(folder, rows, HERE / "p99-motion.json.gz")
    selected = [
        {
            "t": r["t"],
            "frame_id": r["frame_id"],
            "reading": r["reading"],
            "moving": motion.get(r["frame_id"]),
            "attempt": (r.get("skill") or {}).get("attempt_id"),
        }
        for r in rows
        if 9.7 <= r["t"] <= 31.7 and r.get("fresh") and r.get("reading")
    ]
    (HERE / "p99-readings.json").write_text(
        json.dumps(selected, separators=(",", ":")) + "\n"
    )
    receipt = {
        "recording": str(folder),
        "source_sha256": {
            name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
            for name in ("play.jsonl", "frames.jsonl")
        },
        "ticks": len(selected),
        "start": selected[0]["t"],
        "end": selected[-1]["t"],
        "motion": "cv2 decoded frames; replay.motion_for_rows at matched frame_id; no detections replayed",
    }
    (HERE / "p99-fixture.json").write_text(json.dumps(receipt, indent=2) + "\n")


def replay(driver_type, label):
    rows = json.loads((HERE / "p99-readings.json").read_text())
    driver = driver_type(drive_config(["style=bold"]))
    states, phases, first_failure = Counter(), [], None
    with (HERE / f"p99-replay-{label}.csv").open("w") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "t",
                "frame_id",
                "moving",
                "near",
                "far",
                "arrow",
                "state",
                "steer",
                "r2",
                "l2",
            ]
        )
        for row in rows:
            reading = Reading(**{**row["reading"], "blips": ()})
            command = driver.step(
                reading, row["t"], row["moving"], speed=reading.gps_speed
            )
            writer.writerow(
                [
                    row["t"],
                    row["frame_id"],
                    row["moving"],
                    reading.bearing,
                    reading.far_bearing,
                    reading.arrow,
                    command.state,
                    command.steer,
                    command.throttle,
                    command.brake,
                ]
            )
            states[command.state] += 1
            if not phases or phases[-1][1] != command.state:
                phases.append([round(row["t"], 3), command.state])
            if (
                command.state in ("failed-recovery", "dead-or-held")
                and first_failure is None
            ):
                first_failure = row["t"]
    return {
        "ticks": len(rows),
        "states": states,
        "transitions": phases,
        "first_failure": first_failure,
    }


def world(profile, scenario):
    if scenario == "behind":
        return Simulator(
            [(0, 0), (0, 100)],
            heading=180,
            config=SimConfig(**CAR_PROFILES[profile]),
            seed=0,
        )
    config = SimConfig(
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
        scale_with_speed=0,
    )
    return Simulator(
        [(0, -12), (-18, -15), (-24, -10), (-24, 300)],
        position=(0, 0),
        walls=((((-12, -100), (-12, 250)),) if scenario == "rail" else ()),
        config=config,
    )


def trial(driver_type, profile, scenario, writer=None):
    driver = driver_type(drive_config(["style=bold"]))
    sim = world(profile, scenario)
    cfg = driver.config
    sim._speedometer = Speedometer(
        cfg.gps_window,
        cfg.gps_stale,
        cfg.gps_max_speed,
        cfg.gps_tolerance,
        cfg.gps_acceleration,
    )
    aligned = joined = None
    reverse = travel = 0.0
    states = Counter()
    for _ in range(30 * (12 if scenario == "behind" else 30)):
        reading, moving = sim.observe()
        command = driver.step(reading, sim.time, moving, speed=sim.observed_speed)
        if writer:
            writer.writerow(
                [
                    profile,
                    scenario,
                    sim.time,
                    sim.x,
                    sim.y,
                    degrees(sim.heading),
                    sim.speed,
                    command.state,
                    command.steer,
                    command.throttle,
                    command.brake,
                ]
            )
        states[command.state] += 1
        reverse += sim.config.dt if command.brake else 0
        before = sim.x, sim.y
        sim.advance(command)
        travel += hypot(sim.x - before[0], sim.y - before[1])
        if aligned is None and abs((degrees(sim.heading) + 180) % 360 - 180) <= 30:
            aligned = sim.time
        if (
            joined is None
            and abs(sim.x + 24) < 2
            and sim.y > 0
            and abs(degrees(sim.heading)) < 30
        ):
            joined = sim.time
    return {
        "profile": profile,
        "scenario": scenario,
        "aligned_at": aligned,
        "joined_at": joined,
        "x": sim.x,
        "y": sim.y,
        "speed": sim.speed,
        "heading": degrees(sim.heading),
        "travel": travel,
        "reverse_seconds": reverse,
        "collisions": sim.collisions,
        "state": command.state,
        "states": states,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", action="store_true")
    parser.add_argument("--before", action="store_true")
    args = parser.parse_args()
    if args.fixture:
        fixture()
    driver_type, label = (baseline(), "before") if args.before else (Driver, "after")
    with gzip.open(HERE / f"p99-sim-{label}.csv.gz", "wt") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "profile",
                "scenario",
                "t",
                "x",
                "y",
                "heading",
                "speed",
                "state",
                "steer",
                "r2",
                "l2",
            ]
        )
        rows = [
            trial(driver_type, p, s, writer)
            for p in CAR_PROFILES
            for s in ("behind", "join", "rail")
        ]
    result = {"simulator": rows, "replay": replay(driver_type, label)}
    (HERE / f"p99-{label}.json").write_text(json.dumps(result, indent=2) + "\n")
    for row in rows:
        print(json.dumps({k: v for k, v in row.items() if k != "states"}))
    print(json.dumps(result["replay"]))


if __name__ == "__main__":
    main()
