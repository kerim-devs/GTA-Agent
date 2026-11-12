"""Offline, capture-clock comparisons of a human hand and the route driver."""

from __future__ import annotations

import json
from bisect import bisect_right
from dataclasses import asdict, replace
from math import hypot
from pathlib import Path

import numpy as np

from .contract import Reading
from .drive import Driver

HZ = 30
TICK = 1 / HZ
MAX_GAP = 0.1


def json_lines(path):
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def sample_frames(frames):
    """Select at most one frame per capture-clock bin, never fill missing bins."""
    previous = None
    for frame in frames:
        bucket = int(np.floor(float(frame["t"]) * HZ))
        if bucket != previous:
            yield frame
            previous = bucket


def controller_lines(lines, source="human"):
    return sorted((line for line in lines if line.get("src") == source), key=lambda row: row["t"])


def has_hand(lines):
    # The picture-only recorder writes one initial neutral row.
    return any(active(row) or row.get("buttons") for row in lines)


def active(pad):
    return abs(pad.get("left", [0, 0])[0]) >= 0.05 or max(pad.get("r2", 0), pad.get("l2", 0)) > 0.05


def hand_at(lines, times, t):
    index = bisect_right(times, t) - 1
    return lines[index] if index >= 0 else None


def durations(rows):
    return [
        (min(MAX_GAP, rows[i + 1]["t"] - row["t"]) if i + 1 < len(rows) else TICK)
        if i + 1 == len(rows) or rows[i + 1]["t"] - row["t"] <= MAX_GAP
        else TICK
        for i, row in enumerate(rows)
    ]


def route_error(reading):
    if reading.get("bearing") is None or reading.get("arrow") is None:
        return None
    return (reading["bearing"] - reading["arrow"] + 180) % 360 - 180


def estimate_lead(rows, pads, maximum=1.5):
    """Estimate visual response lag, never fit against the driver's commands.

    A decreasing route-relative heading is a clockwise vehicle response. Route
    geometry and camera motion contaminate it, so retain the full fit and report
    weak or boundary optima as unresolved rather than calling them latency.
    """
    if not has_hand(pads) or len(rows) < 4:
        return {"seconds": None, "reason": "no usable hand or visual response", "scores": []}
    times = [p["t"] for p in pads]
    signals = []
    for i in range(3, len(rows)):
        a, b = rows[i - 3], rows[i]
        dt = b["t"] - a["t"]
        ea, eb = route_error(a["reading"]), route_error(b["reading"])
        if not (0.06 <= dt <= 0.16) or ea is None or eb is None:
            continue
        if any(r["reading"].get("corrupt") or r["reading"].get("route") == "none" for r in (a, b)):
            continue
        response = -((eb - ea + 180) % 360 - 180) / dt
        if 2 <= abs(response) <= 150:
            signals.append(((a["t"] + b["t"]) / 2, response))
    scores = []
    for shift in np.arange(0, maximum + TICK / 2, TICK):
        pairs = [(hand_at(pads, times, t - shift), response) for t, response in signals]
        pairs = [(p["left"][0], response) for p, response in pairs if p is not None]
        if len(pairs) < 30:
            continue
        x, y = np.asarray(pairs).T
        score = float(np.corrcoef(x, y)[0, 1]) if np.std(x) > 0.02 and np.std(y) > 0 else 0.0
        scores.append({"seconds": round(float(shift), 6), "correlation": score, "samples": len(pairs)})
    if not scores:
        return {"seconds": None, "reason": "insufficient visual turning", "scores": []}
    best = max(scores, key=lambda item: item["correlation"])
    resolved = best["correlation"] >= 0.15 and 0 < best["seconds"] < maximum - TICK / 2
    return {
        **best,
        "resolved": resolved,
        "reason": "visual response correlation" if resolved else "weak or boundary visual-response fit",
        "physical_delay_validated": False,
        "scores": scores,
    }


def path_curvature(path, config):
    """Same three-point geometry and trim as Driver; units are inverse pixels."""
    path = path[: len(path) - config.curve_trim] if config.curve_trim else path
    step = config.curve_step
    values = []
    for index in range(len(path) - 2 * step):
        a, b, c = path[index], path[index + step], path[index + 2 * step]
        ab, bc, ac = (
            hypot(b[0] - a[0], b[1] - a[1]),
            hypot(c[0] - b[0], c[1] - b[1]),
            hypot(c[0] - a[0], c[1] - a[1]),
        )
        if min(ab, bc) < 1:
            continue
        cross = abs((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]))
        values.append(2 * cross / max(ab * bc * ac, 1e-6))
    return max(values) if values else None


def replay_readings(rows, config):
    driver = Driver(config)
    previous = None
    output = []
    for row in rows:
        if previous is not None and row["t"] - previous > 2.0:
            driver = Driver(config)
        previous = row["t"]
        rd = dict(row["reading"])
        rd["path"] = tuple(tuple(p) for p in rd.get("path", ()))
        rd["blips"] = ()
        reading = Reading(**rd)
        limit = []
        original = driver._speed_limit

        def observe(path, bend, speed, original=original, limit=limit):
            value = original(path, bend, speed)
            limit.append(value)
            return value

        driver._speed_limit = observe
        command = driver.step(reading, row["t"], None, speed=reading.gps_speed)
        driver._speed_limit = original
        output.append(
            {
                **row,
                "command": asdict(command),
                "limit": limit[-1] if limit else None,
                "curvature_px": path_curvature(reading.path, config),
            }
        )
    return output


def gps_reading(reading, speedometer, t, fix):
    """Keep causal GPS history over ordinary capture gaps, as in live playback."""
    if speedometer.last_clock is not None and t - speedometer.last_clock > 2.0:
        speedometer.reset()
    if reading.minimap != "tilted":
        speedometer.reset()
        fix = None
    speed = speedometer.update(t, fix, sampled_at=t)
    fresh = speedometer.time is not None and 0 <= t - speedometer.time <= speedometer.stale
    current = speedometer.fix if fresh else None
    return replace(
        reading,
        gps_speed=speed,
        gps_distance=None if current is None else current.distance,
        gps_arrow=None if current is None else current.arrow,
        gps_time=speedometer.time if fresh else None,
    )


def intervals(rows, key):
    result = []
    start = end = None
    for row, duration in zip(rows, durations(rows), strict=True):
        if row.get(key):
            if start is not None and row["t"] - end > MAX_GAP:
                result.append({"start": start, "end": end, "seconds": end - start})
                start = None
            if start is None:
                start = row["t"]
            end = row["t"] + duration
        elif start is not None:
            result.append({"start": start, "end": end, "seconds": end - start})
            start = None
    if start is not None:
        result.append({"start": start, "end": end, "seconds": end - start})
    return result


def weighted_quantile(values, weights, q):
    if not values:
        return None
    order = np.argsort(values)
    values, weights = np.asarray(values)[order], np.asarray(weights)[order]
    return float(values[min(int(np.searchsorted(np.cumsum(weights), q * weights.sum())), len(values) - 1)])


def analyze(rows, pads, config, sections=None, lead=None):
    if not has_hand(pads):
        return {
            "status": "skipped",
            "reason": "no active controller lines (absent or neutral initialization only)",
            "route_seconds": 0,
            "metrics": None,
            "rows": [],
        }
    alignment = (
        estimate_lead(rows, pads)
        if lead is None
        else {"seconds": lead, "resolved": True, "reason": "supplied reference lead"}
    )
    # Keep uncertain estimates visible; the report must not present them as measured latency.
    shift = alignment["seconds"]
    if shift is None:
        shift = 0.0
        alignment["resolved"] = False
        alignment["reason"] += "; zero-lag coverage only, command comparison uncalibrated"
    alignment["applied_seconds"] = shift
    rows = replay_readings(rows, config)
    times = [pad["t"] for pad in pads]
    for row in rows:
        rd = row["reading"]
        pad = hand_at(pads, times, row["t"] - shift)
        row["hand"] = pad
        drive = rd["minimap"] == "tilted" and pad is not None
        if sections is not None:
            drive = drive and any(
                s["kind"] == "drive" and s["start"] <= row["t"] < s["end"] for s in sections
            )
        else:
            drive = drive and active(pad)
        row["eligible"] = drive and rd["route"] != "none"
        row["no_route"] = drive and rd["route"] == "none"
        row["clear"] = False
    # A moment is a contiguous same-sign run, not a count of correlated ticks.
    moments = []
    run = []
    weights = durations(rows)

    def finish():
        if run and sum(weights[i] for i in run) >= 0.3 - 1e-6:
            for i in run:
                rows[i]["clear"] = True
            agreeing = sum(
                weights[i] for i in run if rows[i]["command"]["steer"] * rows[i]["hand"]["left"][0] > 0
            )
            seconds = sum(weights[i] for i in run)
            moments.append(
                {
                    "start": rows[run[0]]["t"],
                    "end": rows[run[-1]]["t"] + weights[run[-1]],
                    "seconds": seconds,
                    "same_direction_share": agreeing / seconds,
                }
            )
        run.clear()

    for i, row in enumerate(rows):
        stick = row["hand"]["left"][0] if row["hand"] else 0
        clear = row["eligible"] and abs(stick) >= 0.3
        if run and (
            not clear
            or stick * rows[run[-1]]["hand"]["left"][0] <= 0
            or row["t"] - rows[run[-1]]["t"] > MAX_GAP
        ):
            finish()
        if clear:
            run.append(i)
    finish()
    metrics = metrics_for(rows, weights, config)
    metrics["clear_moments"] = len(moments)
    metrics["majority_direction_moments"] = sum(m["same_direction_share"] > 0.5 for m in moments)
    metrics["moment_direction_share"] = (
        (metrics["majority_direction_moments"] / len(moments)) if moments else None
    )
    return {
        "status": "analyzed",
        "alignment": alignment,
        "route_seconds": metrics["route_seconds"],
        "metrics": metrics,
        "clear_moments": moments,
        "route_stretches": intervals(rows, "eligible"),
        "no_route_stretches": intervals(rows, "no_route"),
        "rows": rows,
    }


def metrics_for(rows, weights, config):
    eligible = [(r, w) for r, w in zip(rows, weights, strict=True) if r["eligible"]]
    clear = [(r, w) for r, w in eligible if r["clear"]]
    total = sum(w for _, w in eligible)
    clear_seconds = sum(w for _, w in clear)

    def share(predicate, pairs=eligible):
        denominator = sum(w for _, w in pairs)
        return sum(w for r, w in pairs if predicate(r)) / denominator if denominator else None

    def quantile(pairs, value, q):
        return weighted_quantile([value(r) for r, _ in pairs], [w for _, w in pairs], q)

    speed_rows = [
        (r, w)
        for r, w in eligible
        if r["reading"].get("gps_speed") is not None and r["curvature_px"] is not None
    ]
    bends = [(r, w) for r, w in speed_rows if r["curvature_px"] >= 0.01]
    straights = [(r, w) for r, w in speed_rows if r["curvature_px"] < 0.005]
    limits = [(r, w) for r, w in speed_rows if r["limit"] is not None]
    result = {
        "route_seconds": total,
        "clear_seconds": clear_seconds,
        "clear_share_of_route": clear_seconds / total if total else None,
        "direction_seconds_share": share(lambda r: r["command"]["steer"] * r["hand"]["left"][0] > 0, clear),
        "human_stick_median": quantile(clear, lambda r: abs(r["hand"]["left"][0]), 0.5),
        "driver_stick_median": quantile(clear, lambda r: abs(r["command"]["steer"]), 0.5),
        "full_r2_share": share(lambda r: r["hand"].get("r2", 0) >= 0.95),
        "lifted_share": share(lambda r: r["hand"].get("r2", 0) <= 0.05),
        "l2_share": share(lambda r: r["hand"].get("l2", 0) > 0.05),
        "brake_at_speed_seconds": sum(
            w for r, w in speed_rows if r["hand"].get("l2", 0) > 0.05 and r["reading"]["gps_speed"] > 7
        ),
        "speed_geometry_seconds": sum(w for _, w in speed_rows),
        "bend_seconds": sum(w for _, w in bends),
        "straight_seconds": sum(w for _, w in straights),
    }
    for label, pairs in (("bend", bends), ("straight", straights)):
        for q, suffix in ((0.5, "p50"), (0.9, "p90")):
            result[f"{label}_speed_{suffix}"] = quantile(pairs, lambda r: r["reading"]["gps_speed"], q)
            result[f"{label}_limit_{suffix}"] = quantile(
                [(r, w) for r, w in pairs if r["limit"] is not None], lambda r: r["limit"], q
            )
            result[f"{label}_lateral_proxy_{suffix}"] = quantile(
                pairs, lambda r: r["reading"]["gps_speed"] ** 2 * r["curvature_px"] / config.map_scale_min, q
            )
    result["over_limit_share"] = share(lambda r: r["reading"]["gps_speed"] > r["limit"], limits)
    lifts = []
    last_lift = None
    previous = None
    for row in rows:
        if not row["eligible"]:
            previous = last_lift = None
            continue
        if previous and not 0 < row["t"] - previous["t"] <= MAX_GAP:
            previous = last_lift = None
        if previous:
            if previous["hand"].get("r2", 0) > 0.05 and row["hand"].get("r2", 0) <= 0.05:
                last_lift = row["t"]
            if (previous["curvature_px"] or 0) < 0.01 <= (row["curvature_px"] or 0):
                if last_lift is not None and 0 <= row["t"] - last_lift <= 5:
                    lifts.append(row["t"] - last_lift)
                last_lift = None
        previous = row
    result["lift_before_bend_seconds"] = lifts
    result["lift_before_bend_p50"] = float(np.median(lifts)) if lifts else None
    return result
