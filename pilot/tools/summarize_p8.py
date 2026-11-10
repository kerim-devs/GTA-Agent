"""Reduce a P8 matrix to small review tables and explicitly rebuild measured failure pins."""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from pilot.sim import CAR_PROFILES


def errors(row):
    result = []
    if not row["reached"]:
        result.append(f"not reached at {row['elapsed']:.3f}s")
    if row["max_no_progress"] > 10:
        result.append(f"progress gap {row['max_no_progress']:.3f}s > 10s")
    limit = 5 * row["scale"]
    if row["max_distance"] > limit:
        result.append(f"maximum {row['max_distance']:.3f}m > {limit}m")
    if row["steering_flips_per_second"] > 2:
        result.append(f"flips {row['steering_flips_per_second']:.3f}/s > 2/s")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("matrix", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--pins", type=Path)
    args = parser.parse_args()
    rows = json.loads(args.matrix.read_text())
    groups = defaultdict(list)
    failures = []
    for row in rows:
        groups[(row["profile"], row["name"], row["scale"])].append(row)
        failed = errors(row)
        if failed:
            case = [row[key] for key in ("name", "delay", "scale", "seed", "dead_zone", "profile")]
            explanation = "A remaining measured edge failure; see the report and the car-profile parameters."
            if row["name"] == "straight" and row["scale"] == 0.5:
                explanation = (
                    "The inherited initial offset is already 3m = 6px, "
                    "above the 5px bound before control starts."
                )
            elif row["name"] == "wall" and row["scale"] == 0.5:
                explanation = (
                    "The inherited start points across the route toward a wall 3m away. "
                    "The minimum forward turning radius is 3.86m, exceeding the 2.5m lane bound; "
                    "recovery also leaves it."
                )
            failures.append(dict(case=case, errors=failed, explanation=explanation))
    table = []
    for (profile, name, scale), cases in groups.items():
        table.append(
            dict(
                profile=profile,
                scenario=name,
                scale=scale,
                runs=len(cases),
                reached=sum(r["reached"] for r in cases),
                passed=sum(not errors(r) for r in cases),
                worst_mean_m=round(max(r["mean_distance"] for r in cases), 3),
                max_m=round(max(r["max_distance"] for r in cases), 3),
                max_px=round(max(r["max_distance"] / scale for r in cases), 3),
                max_flips_s=round(max(r["steering_flips_per_second"] for r in cases), 3),
                max_progress_gap_s=round(max(r["max_no_progress"] for r in cases), 3),
            )
        )
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "matrix-summary.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=table[0].keys())
        writer.writeheader()
        writer.writerows(table)
    summary = dict(
        runs=len(rows),
        reached=sum(r["reached"] for r in rows),
        passed=len(rows) - len(failures),
        failures=len(failures),
        max_px=max(r["max_distance"] / r["scale"] for r in rows),
        max_flips_s=max(r["steering_flips_per_second"] for r in rows),
        profiles=CAR_PROFILES,
        nominal=[r for r in table if r["profile"] == "nominal"],
    )
    (args.out / "matrix-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    # The gate exercises all nominal seeds and seed 0 for every pairwise range profile.
    pins = [row for row in failures if row["case"][-1] == "nominal" or row["case"][3] == 0]
    if args.pins:
        args.pins.write_text(json.dumps(pins, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print(f"Gate pins: {len(pins)}; full matrix failures: {len(failures)}")


if __name__ == "__main__":
    main()
