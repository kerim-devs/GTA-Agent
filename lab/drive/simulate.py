"""Compare the unaccepted fit in a closed loop with recorded raster noise."""

import json
import sys
from dataclasses import asdict
from math import hypot
from pathlib import Path
from random import Random

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pilot" / "src"))
from pilot.drive import Driver
from pilot.sim import SimConfig, Simulator
from proposed_target import fitted_target

from pilot import drive


class RecordedNoise(Simulator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.raster_rng = Random(kwargs.get("seed", 0) + 8400)

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
        return tuple(
            (x + self.raster_rng.gauss(0, 1.2), y + self.raster_rng.gauss(0, 1.2))
            for x, y in sampled
        )


ROUTES = {
    "straight": ((0, 0), (0, 120)),
    "left": ((0, 0), (0, 100), (-100, 100)),
    "right": ((0, 0), (0, 100), (100, 100)),
    "s_bend": ((0, 0), (0, 60), (40, 100), (-40, 180), (0, 220), (0, 280)),
}


def main():
    config = SimConfig(
        path_noise=0,
        path_missing=0,
        noise_degrees=1.3,
        noise_tail_multiplier=1,
        noise_tail_probability=0,
        damage_probability=0,
        outlier_probability=0,
        dead_zone=0.25,
    )
    original = drive._target
    results = []
    try:
        for name, route in ROUTES.items():
            for variant, target in [
                ("baseline", original),
                ("proposal", fitted_target),
            ]:
                drive._target = target
                result = RecordedNoise(route, config=config, seed=0).run(Driver())
                results.append({"course": name, "variant": variant, **asdict(result)})
    finally:
        drive._target = original
    print(
        json.dumps(
            {
                "config": asdict(config),
                "raster_sample_spacing_px": 6,
                "raster_independent_noise_sd_px": 1.2,
                "results": results,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
