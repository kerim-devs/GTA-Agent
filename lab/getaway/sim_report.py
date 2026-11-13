"""The simulation of P68 in numbers: get_away in the three worlds of pilot/tests/test_getaway.py.

From pilot/: env -u PS5_HOST .venv/bin/python ../lab/getaway/sim_report.py
Each run is sixty seconds at a tick of 0.1 s; "held" is the longest stretch with the car under 0.5 m/s.
"""

import importlib.util
import sys
from pathlib import Path

from pilot.sim import CAR_PROFILES, SimConfig

TESTS = Path(__file__).resolve().parents[2] / "pilot" / "tests" / "test_getaway.py"
spec = importlib.util.spec_from_file_location("test_getaway", TESTS)
world = importlib.util.module_from_spec(spec)
sys.modules["test_getaway"] = world
spec.loader.exec_module(world)

WORLDS = {
    "open ground": world.open_ground,
    "road with traffic": world.road_with_traffic,
    "towards water": world.towards_water,
}


def line(label, runs):
    ended = sorted(
        {r.results[-1].status + (f" {r.results[-1].reason}" if r.results[-1].reason else "") for r in runs}
    )
    wet = sum(r.in_water for r in runs)
    shore = min(r.min_water for r in runs)
    seconds = min(len(r.speeds) for r in runs) / 10
    print(
        f"{label}: {len(runs)} runs, end {ended}, seconds {seconds:.1f} or more, "
        f"held at most {max(r.held for r in runs):.1f} s, travelled {min(r.travelled for r in runs):.0f} to "
        f"{max(r.travelled for r in runs):.0f} m, in water {wet}"
        + (f", nearest the water {shore:.0f} m" if shore < 1e9 else "")
        + f", on the road {min(r.on_road / len(r.speeds) for r in runs):.2f} or more"
        + f", recoveries {sum(r.sim._recoveries for r in runs)}"
    )


for name, make in WORLDS.items():
    line(f"{name}, minimap on, seeds 0-4", [world.Run(make(seed)).go() for seed in range(5)])
for name in ("open ground", "road with traffic"):
    line(
        f"{name}, minimap off, seeds 0-4",
        [world.Run(WORLDS[name](seed), minimap="off").go() for seed in range(5)],
    )
for name, make in WORLDS.items():
    runs = []
    for profile in CAR_PROFILES.values():
        car = SimConfig(damage_probability=0.0, outlier_probability=0.0, **profile)
        runs.append(world.Run(make(1), car=car).go())
    line(f"{name}, the simulator's {len(runs)} car profiles", runs)
