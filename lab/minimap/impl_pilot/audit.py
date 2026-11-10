"""Reproduce attack selection and save the inspected sheets and measurements."""

import dataclasses
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

def main():
    # File-loaded lab readers import the lab contract from their working directory.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    reader_path = sys.argv[2] if len(sys.argv) > 2 else "impl_pilot/minimap.py"
    spec = importlib.util.spec_from_file_location("audit_reader", reader_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    crops = np.load("data/crops.npy", mmap_mode="r")
    meta = json.loads(Path("data/meta.json").read_text())
    readings = [module.read(crop) for crop in crops]
    groups = {key: [] for key in (
        "route_without_colour", "colour_without_route", "near_jump",
        "opposite_steering", "flicker", "confident_damage",
    )}
    for k, (m, r) in enumerate(zip(meta, readings)):
        if r.route != "none" and m["yellow"] == 0 and m["purple"] == 0:
            groups["route_without_colour"].append(k)
        if r.route == "none" and max(m["yellow"], m["purple"]) > 100:
            groups["colour_without_route"].append(k)
        if r.bearing is not None and abs(m["steer"]) > .4 and m["r2"] > .2:
            if r.bearing * m["steer"] < 0:
                groups["opposite_steering"].append(k)
        if r.corrupt and r.confidence >= .5:
            groups["confident_damage"].append(k)
        if k and meta[k-1]["rec"] == m["rec"] and 0 < m["t"] - meta[k-1]["t"] < .3:
            p = readings[k-1]
            if r.bearing is not None and p.bearing is not None:
                if abs((r.bearing-p.bearing+180)%360-180) > 60:
                    groups["near_jump"].append(k)
        if 0 < k < len(meta)-1 and meta[k-1]["rec"] == m["rec"] == meta[k+1]["rec"]:
            a, b = readings[k-1], readings[k+1]
            if (a.route == b.route != r.route) or (a.minimap == b.minimap != r.minimap):
                groups["flicker"].append(k)
    rng = np.random.default_rng(20261110)
    selected = []
    sheets = {}
    for key, ids in groups.items():
        sample = sorted(rng.choice(ids, min(24, len(ids)), replace=False).tolist())
        sheets[key] = sample
        selected.extend(sample)
    for i in range(2):
        sample = sorted(rng.choice(len(crops), 24, replace=False).tolist())
        sheets[f"random_{i+1}"] = sample
        selected.extend(sample)
    # Context around every abrupt near-bearing jump distinguishes turns from misreads.
    sheets["jump_context"] = sorted({j for k in groups["near_jump"] for j in (k-1,k,k+1)})
    selected.extend(sheets["jump_context"])
    for name, ids in sheets.items():
        for start in range(0, len(ids), 12):
            subprocess.run([sys.executable, "tools.py", "overlay", reader_path,
                            str(out / f"{name}_{start//12+1}.jpg"),
                            *map(str, ids[start:start+12])], check=True)
    payload = {
        "counts": {key: len(ids) for key, ids in groups.items()},
        "groups": groups, "sheets": sheets, "unique_inspected": len(set(selected)),
        "readings": [dataclasses.asdict(r) for r in readings],
    }
    (out / "audit.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({k: payload[k] for k in ("counts", "sheets", "unique_inspected")}, indent=2))


if __name__ == "__main__":
    main()
