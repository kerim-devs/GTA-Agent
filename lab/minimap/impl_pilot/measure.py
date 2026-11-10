"""Reproduce split scores and the frozen, visually inspected motion calibration.

Run from lab/minimap with its interpreter. The optional output path defaults to
/tmp/p2-measurements.json. Calibration is small and is not a general accuracy claim.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from minimap import read
from pilot.motion import MOVING_PX, map_motion


def main():
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/p2-measurements.json")
    results = {"readers": {}, "motion": {}, "moving_px": MOVING_PX}
    for impl in ("trace", "rings", "model", "pilot"):
        for split in ("dev", "held"):
            run = subprocess.run(
                [sys.executable, "harness.py", f"impl_{impl}/minimap.py", "--split", split],
                check=True, capture_output=True, text=True,
            )
            score, _ = json.JSONDecoder().raw_decode(run.stdout)
            results["readers"][f"{impl}_{split}"] = score
            print(impl, split, json.dumps(score["labelled"]), score["speed_ms"], flush=True)
    crops = np.load("data/crops.npy", mmap_mode="r")
    meta = json.loads(Path("data/meta.json").read_text())
    groups = {
        "driving": [658, 659, 668, 672, 829, 840, 858, 859, 860, 962, 969, 973],
        "foot_standing": [2083, 2084, 2085, 2330],
        "vehicle_stuck": [2343, 2344, 2345, 2346, 2347, 2348, 2349, 2350, 2352, 2353],
        "neutral_vehicle_ambiguous": list(range(1101, 1109)),
    }
    for name, ids in groups.items():
        pairs = [{
            "k": k, "rec": meta[k]["rec"], "t": meta[k]["t"],
            "dt": meta[k+1]["t"] - meta[k]["t"],
            "r2": meta[k]["r2"], "l2": meta[k]["l2"], "steer": meta[k]["steer"],
            "pixels": map_motion(crops[k], crops[k+1]),
        } for k in ids]
        accepted = [p["pixels"] for p in pairs if p["pixels"] is not None]
        results["motion"][name] = {
            "pairs": pairs, "accepted": len(accepted), "total": len(pairs),
            "min_median_max": np.quantile(accepted, [0, .5, 1]).tolist() if accepted else [],
        }
    durations = []
    accepted_durations = []
    # Measure all consecutive same-recording pairs, including rejection cost.
    for _ in range(3):
        for k in range(len(crops)-1):
            if meta[k]["rec"] != meta[k+1]["rec"]:
                continue
            start = time.perf_counter_ns()
            value = map_motion(crops[k], crops[k+1])
            ms = (time.perf_counter_ns() - start) / 1e6
            durations.append(ms)
            if value is not None:
                accepted_durations.append(ms)
    for name, values in (("all_pairs", durations), ("accepted_pairs", accepted_durations)):
        results["motion"][name] = {
            "calls": len(values), "mean_ms": float(np.mean(values)),
            "p95_ms": float(np.percentile(values, 95)), "max_ms": float(max(values)),
        }
    # Readings for the random sheets are retained independently of the selector.
    review = json.loads(Path("impl_pilot/review.json").read_text())
    random_ids = sorted(set(review["sheets"]["random_1"] + review["sheets"]["random_2"]))
    results["random_sheets"] = {k: read(crops[k]).__dict__ for k in random_ids}
    output.write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results["motion"], indent=2), flush=True)
    print(f"Saved {output}")


if __name__ == "__main__":
    main()
