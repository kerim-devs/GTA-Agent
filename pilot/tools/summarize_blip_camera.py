"""Summarize the predeclared quality filters for the offline camera check."""

import json
from pathlib import Path

import numpy as np


def main() -> None:
    output = Path(__file__).resolve().parents[2] / "lab/blips"
    raw = json.loads((output / "camera-motion-raw.json").read_text())
    pairs = [
        r
        for r in raw
        if r["map"] == "flat"
        and not r["corrupt"]
        and r["inliers"] >= 12
        and r["inliers"] / r["points"] > 0.7
        and 0.99 < r["scale"] < 1.01
        and abs(r["rotation"]) < 2
        and np.linalg.norm(r["motion"]) >= 0.5
    ]
    summary = {
        "quality_filter": (
            "flat, noncorrupt, >=12 inliers, >70% inliers, "
            "scale (0.99,1.01), abs rotation <2 degrees, motion >=0.5 px"
        ),
        "raw_pairs": len(raw),
        "unique_pairs": len(pairs),
        "delays": {},
    }
    for delay in ("0.6", "0.7", "0.8", "0.9", "1.0", "1.1"):
        angles = [p["samples"][delay]["angle"] for p in pairs if delay in p["samples"]]
        summary["delays"][delay] = {
            "n": len(angles),
            "median_degrees": float(np.median(angles)),
            "p90_degrees": float(np.percentile(angles, 90)),
            "within_45_degrees": sum(a <= 45 for a in angles),
        }
    (output / "camera-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (output / "camera-pairs.json").write_text(json.dumps(pairs, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
