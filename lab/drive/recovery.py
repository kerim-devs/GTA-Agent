"""Offline recovery trials using the production tests' delayed bicycle simulator."""

import json
from dataclasses import asdict
from pathlib import Path

from pilot.drive import Driver
from pilot.sim import SimConfig, Simulator


def trial(kind):
    class Obstacle(Simulator):
        def _hits_wall(self, x, y):
            # A scripted release isolates the second-attempt state transition.
            if kind == "second-try" and self._recoveries >= 2:
                return False
            return super()._hits_wall(x, y)

    config = SimConfig(
        acceleration=0 if kind == "held" else 4.5,
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
        max_time=35,
    )
    sim = Obstacle(
        [(0, 0), (0, 100)], config=config, walls=(((-20, 0.2), (20, 0.2)), ((-20, -1.6), (20, -1.6)))
    )
    driver = Driver()
    phases, previous = [], None
    terminal = None
    while sim.time < config.max_time:
        reading, moving = sim.observe()
        command = driver.step(reading, sim.time, moving, speed=sim.observed_speed)
        if command.state != previous:
            phases.append({"t": round(sim.time, 3), **asdict(command)})
            previous = command.state
        if command.state in ("dead-or-held", "failed-recovery"):
            terminal = command.state
            assert command.steer == command.throttle == command.brake == 0
            break
        if kind == "second-try" and sim.y >= 8:
            terminal = "freed"
            break
        sim.advance(command)
    return {
        "scenario": kind,
        "ending": terminal,
        "seconds": round(sim.time, 3),
        "position": [round(sim.x, 3), round(sim.y, 3)],
        "attempts": sim._recoveries,
        "phases": phases,
    }


def main():
    results = [trial(kind) for kind in ("held", "second-try", "never-free")]
    Path(__file__).with_name("recovery.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
