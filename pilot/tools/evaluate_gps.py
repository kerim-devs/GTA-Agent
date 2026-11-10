"""Compare causal GPS estimates with explicit, reviewable OCR distance anchors."""

import argparse
import json
from pathlib import Path

import numpy as np

from pilot.drive import DriveConfig
from pilot.gps import Speedometer, parse

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / "pilot/tests/fixtures/gps-a-reference.json"


def evaluate(window=None, stale=None):
    cfg = DriveConfig()
    anchors = json.loads(REFERENCE.read_text())["anchors"]
    times = [a["t"] for a in anchors]
    distances = [a["distance"] for a in anchors]
    table = []
    endpoints = {}
    accepted = []
    for stretch in ("a", "b", "c"):
        rows = [
            json.loads(line) for line in (ROOT / f"lab/gps/093238-{stretch}.jsonl").read_text().splitlines()
        ]
        meter = Speedometer(
            window or cfg.gps_window,
            stale or cfg.gps_stale,
            cfg.gps_max_speed,
            cfg.gps_tolerance,
            cfg.gps_acceleration,
        )
        samples = []
        for i, row in enumerate(rows):
            t = row["t"]
            fix = parse(row["texts"])
            speed = meter.update(t, fix)
            if stretch == "a":
                if t in (238.603, 306.094):
                    endpoints[t] = None if fix is None else fix.distance
                if meter.time is not None and (not accepted or accepted[-1][0] != meter.time):
                    accepted.append((meter.time, meter.fix.distance))
            duration = rows[i + 1]["t"] - t if i + 1 < len(rows) else 0
            reference = None
            if stretch == "a" and times[0] <= t <= times[-1]:
                left, right = max(times[0], t - 2), min(times[-1], t + 2)
                reference = (np.interp(left, times, distances) - np.interp(right, times, distances)) / (
                    right - left
                )
            samples.append((row, duration, speed, reference))
        for group in ("all", "clean", "damaged"):
            subset = [s for s in samples if group == "all" or s[0]["corrupt"] == (group == "damaged")]
            available = [s for s in subset if s[2] is not None]
            scored = [s for s in available if s[3] is not None]
            table.append(
                dict(
                    stretch=stretch,
                    group=group,
                    frames=len(subset),
                    speed_frames=len(available),
                    coverage_time=sum(s[1] for s in available) / max(1e-9, sum(s[1] for s in subset)),
                    reference_samples=len(scored),
                    within_3=sum(abs(s[2] - s[3]) <= 3 for s in scored) / len(scored) if scored else None,
                )
            )
    return dict(
        reference=str(REFERENCE.relative_to(ROOT)),
        endpoint_decline_m=endpoints[238.603] - endpoints[306.094],
        accepted_decline_m=accepted[0][1] - accepted[-1][1],
        accepted_first=accepted[0],
        accepted_last=accepted[-1],
        endpoint_seconds=306.094 - 238.603,
        table=table,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = evaluate()
    text = json.dumps(result, indent=2) + "\n"
    print(text, end="")
    if args.out:
        args.out.write_text(text)


if __name__ == "__main__":
    main()
