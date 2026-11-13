"""Offline P84 measurements; never connects to a controller or recording daemon."""

import argparse
import json
import sys
from bisect import bisect_right
from dataclasses import asdict, fields, replace
from math import atan2, degrees, hypot, sqrt
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pilot" / "src"))
import itertools

from pilot.cli import drive_config
from pilot.contract import Reading
from pilot.drive import Driver
from proposed_target import fitted_target

from pilot import drive


def angle(value):
    return (value + 180) % 360 - 180


def old_target(path, radius):
    previous = path[0]
    if len(path) >= 2 and hypot(*previous) > radius:
        x, y = previous
        dx, dy = path[1][0] - x, path[1][1] - y
        length = hypot(dx, dy)
        if length > 0:
            dx, dy = dx / length, dy / length
            projection = x * dx + y * dy
            discriminant = projection * projection - x * x - y * y + radius * radius
            if discriminant < 0 and projection > 0:
                return x - projection * dx, y - projection * dy
            if discriminant >= 0:
                along = -projection + sqrt(discriminant)
                if along < 0:
                    return x + along * dx, y + along * dy
    for point in path[1:]:
        before, after = hypot(*previous), hypot(*point)
        if before <= radius <= after and after > before:
            fraction = (radius - before) / (after - before)
            return tuple(a + fraction * (b - a) for a, b in zip(previous, point))
        if before >= radius:
            return previous
        previous = point
    return previous


def jsonl(path):
    with path.open() as source:
        return [json.loads(line) for line in source if line.strip()]


def human_rows(recording, frames, start, end, stride):
    from pilot.replay import hud_crop

    from pilot import minimap

    pads = jsonl(recording / "pad.jsonl")
    pad_times = [p["t"] for p in pads]
    capture = cv2.VideoCapture(str(recording / "video.mp4"))
    rows = []
    first = next((n for n, f in enumerate(frames) if f["t"] >= start), len(frames))
    if first < len(frames):
        capture.set(cv2.CAP_PROP_POS_FRAMES, frames[first]["i"])
    for n, frame in enumerate(frames[first:]):
        if frame["t"] >= end:
            break
        ok, bgr = capture.read()
        if not ok:
            raise ValueError(f"Cannot decode frame {frame['i']}")
        if n % stride:
            continue
        index = bisect_right(pad_times, frame["t"]) - 1
        pad = pads[index] if index >= 0 else {"left": [0, 0]}
        rows.append(
            {
                "t": frame["t"],
                "frame_id": frame["frame_id"],
                "reading": asdict(minimap.read(hud_crop(bgr))),
                "pad": pad,
            }
        )
    capture.release()
    return rows


def reading(value):
    return Reading(
        **{f.name: value[f.name] for f in fields(Reading) if f.name in value}
    )


def course(path, support=20):
    start = path[0]
    end = start
    distance = 0
    for before, end in itertools.pairwise(path):
        distance += hypot(end[0] - before[0], end[1] - before[1])
        if distance >= support:
            break
    return degrees(atan2(end[0] - start[0], end[1] - start[1]))


def raster_residuals(path):
    samples = [(0.0, *path[0])]
    spacing = []
    distance = 0.0
    for before, point in itertools.pairwise(path):
        spacing.append(hypot(point[0] - before[0], point[1] - before[1]))
        distance += spacing[-1]
        samples.append((distance, *point))
        if distance >= 20:
            break
    sample = np.asarray(samples)
    design = np.column_stack((np.ones(len(sample)), sample[:, 0]))
    fit = np.linalg.lstsq(design, sample[:, 1:], rcond=None)[0]
    tangent = fit[1]
    normal = np.array([-tangent[1], tangent[0]]) / max(np.linalg.norm(tangent), 1e-9)
    residual = (sample[:, 1:] - design @ fit) @ normal
    return residual.tolist(), spacing


def flips(times, values, threshold=0.1):
    previous = 0
    events = []
    for t, value in zip(times, values):
        side = 1 if value > threshold else -1 if value < -threshold else 0
        if side:
            if previous and side != previous:
                events.append((t, side))
            previous = side
    return events


def stats(values):
    if not len(values):
        return None
    return {
        name: round(float(np.percentile(values, q)), 4)
        for name, q in [("median", 50), ("p90", 90), ("p99", 99)]
    }


def replay(rows, target):
    driver = Driver(drive_config(["style=bold"]))
    result = []
    saved = drive._target
    drive._target = target
    try:
        for row in rows:
            # The archived GPS clock is absolute; its recording origin is absent.
            r = replace(reading(row["reading"]), gps_time=None)
            result.append(driver.step(r, row["t"], None, speed=r.gps_speed).steer)
    finally:
        drive._target = saved
    return result


def measure(rows, start, end):
    valid = [r for r in rows if r["t"] < end]
    before, after = replay(valid, old_target), replay(valid, fitted_target)
    selected = [
        (r, b, a)
        for r, b, a in zip(valid, before, after)
        if r["t"] >= start
        and len(r["reading"].get("path", [])) >= 2
        and r["reading"].get("arrow") is not None
        and r["reading"].get("bearing") is not None
        and not r["reading"].get("corrupt")
    ]
    times = [r["t"] for r, _, _ in selected]
    if not times:
        return {"start": start, "end": end, "samples": 0}
    actual = [
        (r.get("sent_pad") or r.get("result", {}).get("pad") or r.get("pad", {})).get(
            "left", [0, 0]
        )[0]
        for r, _, _ in selected
    ]
    errors, near_old, near_new, courses, map_courses = [], [], [], [], []
    residuals, spacings = [], []
    seen = set()
    fresh_times = []
    bearings = []
    ages = []
    for row, _, _ in selected:
        r = row["reading"]
        path = r["path"]
        c = course(path)
        courses.append(angle(c - r["arrow"]))
        map_courses.append(c)
        errors.append(abs(angle(r["bearing"] - c)))
        if row.get("frame_id", row["t"]) in seen:
            continue
        seen.add(row.get("frame_id", row["t"]))
        fresh_times.append(row["t"])
        residual, spacing = raster_residuals(path)
        residuals.extend(residual)
        spacings.extend(spacing)
        bearings.append(angle(r["bearing"] - r["arrow"]))
        near_old.append(angle(degrees(atan2(*old_target(path, 8))) - r["arrow"]))
        near_new.append(angle(degrees(atan2(*fitted_target(path, 8))) - r["arrow"]))
        if row.get("result", {}).get("distance_age") is not None:
            ages.append(row["result"]["distance_age"])

    def jumps(values):
        return stats(
            [
                abs(angle(b - a))
                for a, b, ta, tb in zip(
                    values, values[1:], fresh_times, fresh_times[1:]
                )
                if tb - ta < 0.2
            ]
        )

    events = flips(times, actual)
    error_events = flips(fresh_times, near_old, 8)
    response = []
    for t, side in events:
        preceding = [(et, es) for et, es in error_events if et <= t]
        if preceding and preceding[-1][1] == side and t - preceding[-1][0] <= 1:
            response.append(t - preceding[-1][0])
    unsupported = []
    for t, side in events:
        nearby = [c for tt, c in zip(times, courses) if t - 0.35 <= tt <= t]
        if nearby and not any(side * c > 8 for c in nearby):
            unsupported.append(t)
    # A lag estimate, not an identified plant delay: course changes also rotate this signal.
    grid = np.arange(times[0], times[-1], 0.05)
    signal = np.unwrap(np.radians(map_courses))
    yaw = -np.gradient(np.interp(grid, times, signal), 0.05)
    steer = np.interp(grid, times, actual)
    correlations = []
    for lag in np.arange(0, 1.51, 0.05):
        n = round(lag / 0.05)
        x, y = (steer[:-n], yaw[n:]) if n else (steer, yaw)
        if len(x) > 10 and np.std(x) > 1e-6 and np.std(y) > 1e-6:
            correlations.append((float(np.corrcoef(x, y)[0, 1]), float(lag)))
    peak = max(correlations, default=(0, None))
    return {
        "start": start,
        "end": end,
        "samples": len(times),
        "unique_frames": len(fresh_times),
        "bearing_vs_path_course_degrees": stats(errors),
        "bearing_jump_degrees": jumps(bearings),
        "old_aim_jump_degrees": jumps(near_old),
        "new_aim_jump_degrees": jumps(near_new),
        "actual_flips": len(events),
        "replay_before_flips": len(flips(times, [b for _, b, _ in selected])),
        "replay_after_flips": len(flips(times, [a for _, _, a in selected])),
        "unsupported_by_local_tangent_flips": len(unsupported),
        "aim_to_stick_seconds": stats(response),
        "aim_to_stick_matched": len(response),
        "steer_to_map_course_rate_proxy_lag_seconds": peak[1],
        "steer_to_map_course_rate_proxy_correlation": round(peak[0], 4),
        "gps_distance_age_seconds": stats(ages),
        "gps_speed_missing": sum(
            r["reading"].get("gps_speed") is None for r, _, _ in selected
        ),
        "path_perpendicular_residual_sd_px": round(float(np.std(residuals)), 4),
        "path_perpendicular_abs_residual_px": stats(np.abs(residuals)),
        "path_sample_spacing_px": stats(spacings),
        "flips_by_threshold": {
            str(threshold): {
                "actual": len(flips(times, actual, threshold)),
                "before": len(flips(times, [b for _, b, _ in selected], threshold)),
                "proposal": len(flips(times, [a for _, _, a in selected], threshold)),
            }
            for threshold in (0.05, 0.1, 0.2, 0.25)
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path)
    parser.add_argument("--start", type=float, default=120)
    parser.add_argument("--end", type=float, default=315)
    parser.add_argument(
        "--readings",
        type=Path,
        help="Decoded human rows, with original frame/pad times",
    )
    parser.add_argument(
        "--human",
        action="store_true",
        help="Decode route readings and align human pad timestamps",
    )
    parser.add_argument("--stride", type=int, default=2)
    parser.add_argument("--export", type=Path)
    args = parser.parse_args()
    frames = jsonl(args.recording / "frames.jsonl")
    rows = (
        human_rows(args.recording, frames, args.start, args.end, args.stride)
        if args.human
        else jsonl(args.readings or args.recording / "play.jsonl")
    )
    if not args.readings and not args.human:
        rows = [
            r
            for r in rows
            if (r.get("skill") or {}).get("name") == "drive_route" and r.get("reading")
        ]
    rows = [r for r in rows if args.start <= r["t"] < args.end]
    capture = cv2.VideoCapture(str(args.recording / "video.mp4"))
    decoded = []
    for t in (args.start, (args.start + args.end) / 2, args.end - 1):
        index = max(0, bisect_right([f["t"] for f in frames], t) - 1)
        capture.set(cv2.CAP_PROP_POS_FRAMES, frames[index]["i"])
        ok, frame = capture.read()
        decoded.append(
            {
                "t": frames[index]["t"],
                "decoded": ok,
                "mean_luma": round(
                    float(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).mean()), 2
                )
                if ok
                else None,
            }
        )
    capture.release()
    print(
        json.dumps(
            {
                "recording": str(args.recording),
                "video_samples": decoded,
                "frame_gap_seconds": max(
                    (
                        b["t"] - a["t"]
                        for a, b in itertools.pairwise(frames)
                        if args.start <= a["t"] < args.end
                    ),
                    default=0,
                ),
                "windows": [
                    measure(rows, t, min(t + 15, args.end))
                    for t in np.arange(args.start, args.end, 15)
                ],
            },
            indent=2,
        )
    )
    if args.export:
        args.export.write_text(
            json.dumps(
                {
                    "source": str(args.recording),
                    "start": args.start,
                    "end": args.end,
                    "rows": rows,
                },
                separators=(",", ":"),
            )
            + "\n"
        )


if __name__ == "__main__":
    main()
