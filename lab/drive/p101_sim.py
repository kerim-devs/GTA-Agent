"""Closed-loop parked-car comparison with optional missing detections and side walls."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from subprocess import check_output
from types import ModuleType

from pilot.cli import drive_config
from pilot.contract import Command, Observation
from pilot.drive import Driver
from pilot.sim import CAR_PROFILES, SimConfig, Simulator
from pilot.skills import DriveRoute

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "pilot" / "tools"))
from evaluate_player_driver import box, parked  # noqa: E402


def baseline():
    module = ModuleType("pilot._p101_before")
    sys.modules[module.__name__] = module
    source = check_output(["git", "show", "HEAD:pilot/src/pilot/drive.py"], cwd=HERE, text=True)
    exec(compile(source, module.__name__, "exec"), module.__dict__)
    return module.Driver


def baseline_avoid():
    module = ModuleType("pilot._p101_avoid_before")
    sys.modules[module.__name__] = module
    source = check_output(["git", "show", "HEAD:pilot/src/pilot/avoid.py"], cwd=HERE, text=True)
    exec(compile(source, module.__name__, "exec"), module.__dict__)
    return module


def trial(profile, blocked=0, detected=False, driver_type=Driver, seconds=30):
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
    )
    # A closed rectangle, not just the rear bumper. The existing physics sweeps
    # the car's centre against its edges; real body clearance remains unmodelled.
    walls = [
        ((-0.9, 2), (0.9, 2)),
        ((-0.9, 2), (-0.9, 6)),
        ((0.9, 2), (0.9, 6)),
        ((-0.9, 6), (0.9, 6)),
    ]
    if blocked:
        walls.append(((blocked * 1.25, -20), (blocked * 1.25, 30)))
    sim = Simulator([(0, 0), (0, 150)], walls=walls, config=cfg)
    skill = DriveRoute({"duration": 90, "style": "bold"})
    skill.driver = driver_type(drive_config(["style=bold"]))
    first_contact = passed = joined = None
    reverse_at = None
    longest_reverse = 0.0
    phases, trace, states = [], [], Counter()
    while sim.time < seconds:
        reading, moving = sim.observe()
        objects = box(sim, 2) if detected else ()
        result = skill.step(Observation(reading, moving, sim.time, objects=objects, objects_time=sim.time))
        command = Command(result.pad.left[0], result.pad.r2, result.pad.l2, skill.driver._last.state)
        states[command.state] += 1
        if not phases or phases[-1][1] != command.state:
            phases.append([round(sim.time, 4), command.state, command.steer])
        if command.brake and command.state.startswith("bypass"):
            if reverse_at is None:
                reverse_at = sim.time
            longest_reverse = max(longest_reverse, sim.time - reverse_at + cfg.dt)
        else:
            reverse_at = None
        trace.append(
            [
                sim.time,
                sim.x,
                sim.y,
                sim.heading,
                sim.speed,
                command.state,
                command.steer,
                command.throttle,
                command.brake,
                moving,
            ]
        )
        before = sim.collisions
        sim.advance(command)
        if sim.collisions > before and first_contact is None:
            first_contact = sim.time
        if passed is None and sim.y > 8:
            passed = sim.time
        if passed and abs(sim.x) < 0.75 and sim.y > 12:
            joined = sim.time
            break
        if result.status != "running":
            break
    return {
        "profile": profile,
        "blocked": blocked,
        "detected": detected,
        "first_contact": first_contact,
        "passed_at": passed,
        "joined_at": joined,
        "after_contact": None if passed is None or first_contact is None else passed - first_contact,
        "longest_reverse": longest_reverse,
        "phases": phases,
        "states": states,
        "collisions": sim.collisions,
        "final_position": [sim.x, sim.y],
        "status": result.status,
        "reason": result.reason,
        "trace": trace,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", action="store_true")
    args = parser.parse_args()
    driver_type = baseline() if args.before else Driver
    if args.before:
        old_avoid = baseline_avoid()
        sys.modules["pilot.avoid"] = old_avoid
        sys.modules["pilot.skills"].Avoider = old_avoid.Avoider
    rows = []
    for profile in CAR_PROFILES:
        for blocked in (0, -1, 1):
            row = trial(profile, blocked=blocked, driver_type=driver_type)
            row.pop("trace")
            rows.append(row)
            print(json.dumps(row), flush=True)
    # Keep the original P80 runner unchanged for a like-for-like comparison.
    old_driver = sys.modules["pilot.skills"].Driver
    sys.modules["pilot.skills"].Driver = driver_type
    try:
        known = [
            parked(profile, gap, blocked)
            for profile in CAR_PROFILES
            for gap in (2, 4, 7, 12)
            for blocked in ((0, -1, 1) if gap < 12 else (0,))
        ]
    finally:
        sys.modules["pilot.skills"].Driver = old_driver
    label = "before" if args.before else "after"
    (HERE / f"p101-sim-{label}.json").write_text(
        json.dumps({"unreported": rows, "p80": known}, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
