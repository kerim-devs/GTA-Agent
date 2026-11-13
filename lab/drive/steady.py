"""Spatial straight-road measurements shared by recordings and the closed loop."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
from analyze import angle, human_rows, jsonl, raster_residuals


def geometry(reading):
    path = np.asarray(reading.get("path", ()), dtype=float)
    if reading.get("corrupt") or reading.get("arrow") is None or len(path) < 3:
        return None
    distance = np.r_[0, np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]
    if distance[-1] < 40:
        return None
    # Two adjacent 20px chords classify the road independently of the car heading.
    points = np.array(
        [[np.interp(s, distance, path[:, i]) for i in (0, 1)] for s in (0, 20, 40)]
    )
    vectors = np.diff(points, axis=0)
    courses = np.degrees(np.arctan2(vectors[:, 0], vectors[:, 1]))
    bend = abs(angle(courses[1] - courses[0]))
    return angle(courses[0] - reading["arrow"]), bend


def measure(rows, start, end):
    samples = []
    seen = set()
    residuals = []
    for row in rows:
        if not start <= row["t"] < end or row.get("frame_id", row["t"]) in seen:
            continue
        seen.add(row.get("frame_id", row["t"]))
        result = geometry(row["reading"])
        if result is None or result[1] >= 15:
            continue
        pad = (
            row.get("sent_pad")
            or row.get("result", {}).get("pad")
            or row.get("pad", {})
        )
        samples.append((row["t"], result[0], pad.get("left", [0, 0])[0]))
        residuals.extend(raster_residuals(row["reading"]["path"])[0])
    if not samples:
        return {"start": start, "end": end, "samples": 0}
    runs = np.split(
        np.array(samples), np.where(np.diff(np.array(samples)[:, 0]) > 0.2)[0] + 1
    )
    runs = [run for run in runs if run[-1, 0] - run[0, 0] >= 1]
    if not runs:
        return {"start": start, "end": end, "samples": 0}
    for run in runs:
        run[:, 1] = np.degrees(np.unwrap(np.radians(run[:, 1])))
    values = np.concatenate(runs)
    headings, sticks = values[:, 1], values[:, 2]
    return {
        "start": start,
        "end": end,
        "samples": len(values),
        "straight_seconds": float(sum(run[-1, 0] - run[0, 0] for run in runs)),
        "runs": len(runs),
        "heading_sd_deg": float(
            np.sqrt(sum(len(run) * np.var(run[:, 1]) for run in runs) / len(values))
        ),
        "heading_rms_deg": float(np.sqrt(np.mean(headings**2))),
        "heading_p90_span_deg": float(
            np.sqrt(
                sum(
                    len(run)
                    * (np.percentile(run[:, 1], 95) - np.percentile(run[:, 1], 5)) ** 2
                    for run in runs
                )
                / len(values)
            )
        ),
        "stick_mean_abs": float(np.mean(np.abs(sticks))),
        "stick_rms": float(np.sqrt(np.mean(sticks**2))),
        "path_residual_sd_px": float(np.std(residuals)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extract", action="store_true")
    args = parser.parse_args()
    fixture = Path(__file__).with_name("p87-recordings.json.gz")
    if args.extract:
        base = Path("/Users/kerim/recordings")
        sources = []
        for name, start, end, human in [
            ("pilot/20261113-163218", 120, 315, False),
            ("kerim/20261113-141634", 120, 135, True),
            ("kerim/20261113-031159", 15, 30, True),
        ]:
            directory = base / name
            rows = (
                human_rows(directory, jsonl(directory / "frames.jsonl"), start, end, 2)
                if human
                else [
                    r
                    for r in jsonl(directory / "play.jsonl")
                    if start <= r["t"] < end
                    and (r.get("skill") or {}).get("name") == "drive_route"
                    and r.get("reading")
                ]
            )
            sources.append(
                {
                    "recording": name,
                    "start": start,
                    "end": end,
                    "source_sha256": hashlib.sha256(
                        (
                            directory / ("pad.jsonl" if human else "play.jsonl")
                        ).read_bytes()
                    ).hexdigest(),
                    "rows": [
                        {
                            k: r[k]
                            for k in (
                                "t",
                                "frame_id",
                                "reading",
                                "sent_pad",
                                "pad",
                                "result",
                            )
                            if k in r
                        }
                        for r in rows
                    ],
                }
            )
        fixture.write_bytes(
            gzip.compress(json.dumps(sources, separators=(",", ":")).encode(), mtime=0)
        )
    sources = json.loads(gzip.decompress(fixture.read_bytes()))
    print(
        json.dumps(
            {
                "straight_bend_limit_deg": 15,
                "chord_px": 20,
                "minimum_run_seconds": 1,
                "maximum_gap_seconds": 0.2,
                "provisional_heading_sd_limit_deg": 10,
                "sources": [
                    {
                        "recording": s["recording"],
                        "source_sha256": s["source_sha256"],
                        "windows": [
                            measure(s["rows"], t, min(t + 15, s["end"]))
                            for t in range(s["start"], s["end"], 15)
                        ],
                    }
                    for s in sources
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
