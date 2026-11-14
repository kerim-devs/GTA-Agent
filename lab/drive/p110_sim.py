"""P110 heading and retreat measurements on the existing planar car profiles."""

import json
from inspect import signature
from math import degrees, hypot
from pathlib import Path

from p101_sim import baseline, trial
from pilot.cli import drive_config
from pilot.drive import Driver
from pilot.sim import CAR_PROFILES, SimConfig, Simulator

HERE = Path(__file__).resolve().parent


def parked(profile, blocked=0, driver_type=Driver):
    row = trial(profile, blocked=blocked, driver_type=driver_type)
    trace = row.pop("trace")
    active = [r for r in trace if r[5].startswith("bypass-")]
    reverse, leg, maximum, commanded, maximum_commanded = 0.0, 0.0, 0.0, 0.0, 0.0
    for before, after in zip(trace, trace[1:]):
        distance = hypot(after[1] - before[1], after[2] - before[2])
        if before[4] < 0:
            reverse += distance
            leg += distance
            maximum = max(maximum, leg)
        else:
            leg = 0.0
        if before[5] == "bypass-reverse" and before[8] and before[4] < 0:
            commanded += distance
            maximum_commanded = max(maximum_commanded, commanded)
        else:
            commanded = 0.0
    row.update(
        max_heading=max((abs(degrees(r[3])) for r in active), default=0),
        end_heading=abs(degrees(active[-1][3])) if active else None,
        reversed_m=reverse,
        longest_retreat_m=maximum,
        longest_commanded_retreat_m=maximum_commanded,
    )
    return row


def slope(driver_type=Driver):
    cfg = SimConfig(
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
        reverse_speed=12,
    )
    sim = Simulator([(0, 0), (0, 150)], config=cfg)
    driver = driver_type(drive_config(["style=bold"]))
    # The planar model has no slope: give it observed downhill reverse momentum.
    options = {"blind": True} if "blind" in signature(driver._start_bypass).parameters else {}
    driver._start_bypass(0, -1, **options)
    sim.speed = -8
    commands = []
    while sim.time < 3:
        reading, moving = sim.observe()
        command = driver.step(reading, sim.time, True, speed=abs(sim.speed))
        commands.append(command)
        sim.advance(command)
        if command.state != "bypass-reverse":
            break
    return dict(
        reverse_command_seconds=sim.time,
        metres=-sim.y,
        last_brake=commands[-1].brake,
        last_state=commands[-1].state,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--before", action="store_true")
    args = parser.parse_args()
    cls = baseline() if args.before else Driver
    result = dict(parked=[parked(p, b, cls) for p in CAR_PROFILES for b in (0, -1, 1)], slope=slope(cls))
    label = "before" if args.before else "after"
    (HERE / f"p110-sim-{label}.json").write_text(json.dumps(result, indent=2) + "\n")
    for r in result["parked"]:
        print(
            r["profile"],
            r["blocked"],
            r["after_contact"],
            r["joined_at"],
            round(r["max_heading"], 2),
            round(r["end_heading"], 2),
            round(r["longest_retreat_m"], 2),
        )
    print(result["slope"])
