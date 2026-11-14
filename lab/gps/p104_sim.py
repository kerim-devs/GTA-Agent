"""Matched no-speed pedal trials; one simulator and one process at a time."""

import json
import sys
import types
from dataclasses import asdict

from pilot.cli import drive_config
from pilot.drive import Driver
from pilot.sim import CAR_PROFILES, SimConfig, Simulator, drive_through_roads

import p104


def run():
    baseline = types.ModuleType("pilot.p104_drive_original")
    baseline.__package__ = "pilot"
    sys.modules[baseline.__name__] = baseline
    source = p104.subprocess.check_output(["git", "show", "HEAD:pilot/src/pilot/drive.py"], text=True)
    exec(compile(source, "baseline-drive.py", "exec"), baseline.__dict__)
    roads = drive_through_roads()
    roads["kilometre"] = ((0, 0), (0, 250))
    roads["town"] = ((0, 0), (0, 50), (50, 50), (50, 100))
    rows = []
    for profile, car in CAR_PROFILES.items():
        for name, route in roads.items():
            for dropout in ((6, 12) if profile in {"nominal", "fast-low-grip"} else (12,)):
                config = SimConfig(
                    **car, dead_zone=.25, delay=.14, max_time=900,
                    gps_wrong=0, gps_dropout=dropout, path_spacing=6,
                    path_missing=0, damage_probability=0, outlier_probability=0,
                    noise_degrees=.5, path_noise=.15,
                )
                row = dict(profile=profile, road=name, dropout=dropout)
                for version, driver in (("before", baseline.Driver), ("after", Driver)):
                    result = Simulator(route, config=config).run(driver(drive_config(["style=bold"])))
                    row[version] = asdict(result)
                rows.append(row)
        print(profile, "finished", flush=True)
    p104.dump(p104.OUT / "p104-sim.jsonl", rows)
    baseline_pass = [r for r in rows if r['before']['reached'] and r['before']['max_distance'] <= 5 and not r['before']['collisions']]
    lost = [r for r in baseline_pass if not r['after']['reached'] or r['after']['max_distance'] > 5 or r['after']['collisions']]
    result = dict(trials=len(rows), baseline_pass=len(baseline_pass), regressions=len(lost),
                  max_after_distance=max(r['after']['max_distance'] for r in baseline_pass),
                  elapsed_ratio_median=float(p104.np.median([r['after']['elapsed']/r['before']['elapsed'] for r in baseline_pass])))
    print(json.dumps(result), flush=True)
    for row in lost:
        print("REGRESSION", json.dumps(row), flush=True)
    (p104.OUT / 'p104-sim-summary.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    run()
