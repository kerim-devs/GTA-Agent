"""Offline replay tables and the P8 deterministic car-range matrix."""

import argparse
import json
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from itertools import product
from pathlib import Path

from pilot.contract import Reading
from pilot.drive import DriveConfig, Driver
from pilot.replay import diagnostics, json_lines
from pilot.sim import CAR_PROFILES, SimConfig, Simulator

SCENARIOS = {
    "straight": (((0, 0), (0, 120)), (3, 0), 20, ()),
    "left": (((0, 0), (0, 100), (-100, 100)), (0, 0), 0, ()),
    "right": (((0, 0), (0, 100), (100, 100)), (0, 0), 0, ()),
    "s_bend": (((0, 0), (0, 60), (40, 100), (-40, 180), (0, 220), (0, 280)), (0, 0), 0, ()),
    "block": (((0, 0), (0, 100), (100, 100), (100, -30), (-30, -30), (-30, 20)), (0, 0), 0, ()),
    "wall": (((0, 0), (60, 0), (60, 100)), (0, 0), 0, (((-6, 3), (6, 3)),)),
}


def matrix_case(job):
    config, name, delay, scale, seed, dead_zone, profile = job
    route, position, heading, walls = SCENARIOS[name]
    result = Simulator(
        route,
        position=position,
        heading=heading,
        walls=walls,
        config=SimConfig(delay=delay, map_scale=scale, dead_zone=dead_zone, **CAR_PROFILES[profile]),
        seed=seed,
    ).run(Driver(config))
    return dict(
        name=name, delay=delay, scale=scale, seed=seed, dead_zone=dead_zone, profile=profile, **asdict(result)
    )


def matrix(config: DriveConfig, profiles=("nominal",), workers=1) -> list[dict]:
    jobs = [
        (config, *case)
        for case in product(SCENARIOS, (0.14, 0.21, 0.3), (0.5, 1.0, 2.0), (0, 1, 2), (0.0, 0.25), profiles)
        if case[-1] == "nominal" or case[3] == 0
    ]
    if workers == 1:
        return [matrix_case(job) for job in jobs]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(matrix_case, jobs, chunksize=3))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ranges", action="store_true")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--rows", type=Path)
    parser.add_argument("--pad", type=Path)
    parser.add_argument("--rerun", action="store_true", help="Run current driver over cached readings")
    parser.add_argument("--config", default="{}", help="DriveConfig overrides as JSON")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    config = DriveConfig(**json.loads(args.config))
    if args.rows:
        if not args.pad:
            parser.error("--rows requires --pad")
        rows = json_lines(args.rows)
        if args.rerun:
            driver = Driver(config)
            rows = [
                dict(row, command=asdict(driver.step(Reading(**row["reading"]), row["time"], row["moving"])))
                for row in rows
            ]
        result = diagnostics(rows, json_lines(args.pad))
    else:
        result = matrix(config, tuple(CAR_PROFILES) if args.ranges else ("nominal",), args.workers)
    args.out.write_text(json.dumps(result, separators=(",", ":")) + "\n")
    if isinstance(result, list):
        for name in SCENARIOS:
            for scale in (0.5, 1.0, 2.0):
                cases = [r for r in result if r["name"] == name and r["scale"] == scale]
                print(
                    name,
                    scale,
                    sum(r["reached"] for r in cases),
                    len(cases),
                    round(max(r["max_distance"] for r in cases), 3),
                    round(max(r["steering_flips_per_second"] for r in cases), 3),
                )
    else:
        print(json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
