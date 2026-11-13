"""Compare P73 styles in the existing simulator; no console or recording writes."""

import argparse
import json
from dataclasses import asdict
from math import degrees, hypot
from pathlib import Path

from pilot.cli import drive_config
from pilot.drive import Driver
from pilot.sim import CAR_PROFILES, SimConfig, Simulator

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
        if abs(self.speed) <= 0.5 and not command.state.startswith("recovery"):
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    rows = matrix()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"evidence": "simulator", "rows": rows}, indent=2) + "\n")


if __name__ == "__main__":
    main()
