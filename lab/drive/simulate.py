"""Closed-loop P87 spatial measurements; no console connection."""

import argparse
import gzip
import json
import sys
from bisect import bisect_right
from dataclasses import asdict, replace
from math import hypot
from pathlib import Path
from random import Random

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pilot" / "src"))
from pilot.cli import drive_config
from pilot.drive import Driver
from pilot.sim import SimConfig, Simulator
from steady import measure


class RecordedNoise(Simulator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.raster_rng = Random(kwargs.get("seed", 0) + 8400)
        self.rows = []
        self.unknown_speed = False
        self.speed_availability = None

    def _path_reading(self):
        path = super()._path_reading()
        sampled = []
        for point in path:
            if (
                not sampled
                or hypot(point[0] - sampled[-1][0], point[1] - sampled[-1][1]) >= 6
            ):
                sampled.append(point)
        # Four samples minus a fitted intercept and slope leave two residual
        # degrees of freedom: 1.2 * sqrt(2/4) = .85 px upper measured residual SD.
        noisy = tuple(
            (x + self.raster_rng.gauss(0, 1.2), y + self.raster_rng.gauss(0, 1.2))
            for x, y in sampled
        )
        return tuple(point for point in noisy if hypot(*point) >= 11)

    def observe(self):
        reading, moving = super().observe()
        missing_speed = self.unknown_speed
        if self.speed_availability:
            times, available = self.speed_availability
            index = max(0, bisect_right(times, 150 + self.time % 30) - 1)
            missing_speed = not available[index]
        if missing_speed:
            reading = replace(reading, gps_speed=None, gps_time=None)
            self.observed_speed = None
        self.rows.append(
            {
                "t": self.time,
                "reading": asdict(reading),
                "pad": {"left": [self.applied.steer, 0]},
            }
        )
        return reading, moving


ROUTES = {
    "straight": ((0, 0), (0, 120)),
    "left": ((0, 0), (0, 100), (-100, 100)),
    "right": ((0, 0), (0, 100), (100, 100)),
    "s_bend": ((0, 0), (0, 60), (40, 100), (-40, 180), (0, 220), (0, 280)),
}


def configuration(**kwargs):
    return replace(
        SimConfig(
            path_noise=0,
            path_missing=0,
            noise_degrees=1.3,
            noise_tail_multiplier=1,
            noise_tail_probability=0,
            damage_probability=0,
            outlier_probability=0,
            dead_zone=0.0,
            max_time=180,
        ),
        **kwargs,
    )


def trial(
    name="straight",
    *,
    config=None,
    driver=None,
    seed=0,
    unknown_speed=False,
    recorded_speed=False,
):
    sim = RecordedNoise(ROUTES[name], config=config or configuration(), seed=seed)
    sim.unknown_speed = unknown_speed
    if recorded_speed:
        sources = json.loads(
            gzip.decompress(
                Path(__file__).with_name("p87-recordings.json.gz").read_bytes()
            )
        )
        rows = [r for r in sources[0]["rows"] if 150 <= r["t"] < 180]
        sim.speed_availability = (
            [r["t"] for r in rows],
            [r["reading"].get("gps_speed") is not None for r in rows],
        )
    result = sim.run(driver or Driver(drive_config(["style=bold"])))
    windows = [
        measure(sim.rows, t, t + 15) for t in range(5, int(result.elapsed) - 14, 15)
    ]
    return {
        "course": name,
        "seed": seed,
        "unknown_speed": unknown_speed,
        "recorded_speed_availability": recorded_speed,
        **asdict(result),
        "windows": windows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--variant",
        choices=("baseline", "continuous", "combined", "farther"),
        default="baseline",
    )
    parser.add_argument("--delay", type=float, default=0.14)
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--calibrate", action="store_true")
    parser.add_argument("--recorded-speed", action="store_true")
    args = parser.parse_args()
    from p87_candidates import candidate

    results = []
    if args.calibrate:
        for delay in (0.14, 0.21, 0.6, 0.65):
            for zone in (0.0, 0.25):
                for unknown in (False, True):
                    config = configuration(delay=delay, dead_zone=zone)
                    results.append(
                        {
                            "delay": delay,
                            "physical_dead_zone_assumption": zone,
                            **trial(config=config, unknown_speed=unknown),
                        }
                    )
    else:
        for seed in range(args.seeds):
            for name in ROUTES:
                results.append(
                    trial(
                        name,
                        config=configuration(delay=args.delay),
                        seed=seed,
                        driver=candidate(drive_config(["style=bold"]), args.variant),
                        recorded_speed=args.recorded_speed,
                    )
                )
    print(
        json.dumps(
            {
                "variant": args.variant,
                "config": asdict(configuration(delay=args.delay)),
                "raster_sample_spacing_px": 6,
                "raster_independent_noise_sd_px": 1.2,
                "results": results,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
