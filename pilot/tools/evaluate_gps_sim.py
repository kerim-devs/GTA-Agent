"""Rebuild the explicit P9 simulation evidence and measured failure baseline."""

import argparse
import json
from pathlib import Path

from evaluate_driver import SCENARIOS, matrix

from pilot.drive import DriveConfig
from pilot.sim import CAR_PROFILES


def violations(row):
    errors = []
    if not row["reached"]:
        errors.append(f"not reached at {row['elapsed']:.3f}s")
    if row["max_no_progress"] > 10:
        errors.append(f"progress gap {row['max_no_progress']:.3f}s > 10s")
    if row["max_distance"] > 5:
        errors.append(f"maximum {row['max_distance']:.3f}m > 5.0m")
    if row["steering_flips_per_second"] > 2:
        errors.append(f"flips {row['steering_flips_per_second']:.3f}/s > 2/s")
    if row["max_overspeed_time"] > 1:
        errors.append(f"overspeed {row['max_overspeed_time']:.3f}s > 1s")
    if row["max_bend_speed"] > 4:
        errors.append(f"bend speed {row['max_bend_speed']:.3f}m/s > 4m/s")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--pin", type=Path)
    args = parser.parse_args()
    rows = matrix(DriveConfig(), tuple(CAR_PROFILES), args.workers)
    failures = []
    for row in rows:
        errors = violations(row)
        if errors:
            failures.append(
                dict(
                    case=[row[k] for k in ("name", "delay", "scale", "seed", "dead_zone", "profile")],
                    errors=errors,
                )
            )
    args.out.write_text(json.dumps(rows, separators=(",", ":")) + "\n")
    if args.pin:
        args.pin.write_text(json.dumps(failures, indent=2) + "\n")
    print(f"cases={len(rows)} reached={sum(r['reached'] for r in rows)} pinned_failures={len(failures)}")
    for name in SCENARIOS:
        cases = [r for r in rows if r["name"] == name]
        print(
            name,
            len(cases),
            sum(r["reached"] for r in cases),
            f"route_max={max(r['max_distance'] for r in cases):.3f}m",
            f"bend_max={max(r['max_bend_speed'] for r in cases):.3f}m/s",
            f"overspeed_max={max(r['max_overspeed_time'] for r in cases):.3f}s",
            f"progress_gap={max(r['max_no_progress'] for r in cases):.3f}s",
        )


if __name__ == "__main__":
    main()
