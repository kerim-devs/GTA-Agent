"""Record every tick and the measured reverse bounds of the noisy turn matrix."""

import csv
import json
from math import degrees, hypot
from pathlib import Path

from pilot.cli import drive_config
from pilot.drive import Driver
from pilot.gps import Speedometer
from pilot.sim import CAR_PROFILES, SimConfig, Simulator

HERE = Path(__file__).resolve().parent


def main():
    rows = []
    with (HERE / "p80-turn-after.csv").open("w") as stream:
        writer = csv.writer(stream)
        writer.writerow(["profile", "t", "x", "y", "heading_degrees", "speed", "phase",
            "command_state", "steer", "r2", "l2"])
        for name, physics in CAR_PROFILES.items():
            config = drive_config(["style=bold"])
            driver = Driver(config)
            sim = Simulator([(0, 0), (0, 100)], heading=180, config=SimConfig(**physics), seed=0)
            sim._speedometer = Speedometer(config.gps_window, config.gps_stale,
                config.gps_max_speed, config.gps_tolerance, config.gps_acceleration)
            since = None
            distance = longest = furthest = 0.0
            while sim.time < 8:
                reading, moving = sim.observe()
                command = driver.step(reading, sim.time, moving, speed=sim.observed_speed)
                if driver._phase == "turn-reverse":
                    if since is None:
                        since, distance = sim.time, 0.0
                elif since is not None:
                    longest = max(longest, sim.time - since)
                    furthest = max(furthest, distance)
                    since = None
                writer.writerow([name, *[round(v, 5) for v in (sim.time, sim.x, sim.y,
                    degrees(sim.heading), sim.speed)], driver._phase, command.state,
                    round(command.steer, 5), round(command.throttle, 5), round(command.brake, 5)])
                before = sim.x, sim.y
                sim.advance(command)
                if since is not None:
                    distance += hypot(sim.x - before[0], sim.y - before[1])
            rows.append({"profile": name, "longest_reverse_phase": longest,
                "furthest_reverse_phase": furthest})
    (HERE / "p80-turn-bounds.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
