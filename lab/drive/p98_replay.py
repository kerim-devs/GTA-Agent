"""P98 open-loop pedal attribution, using recorded readings and the pre-task driver."""

import ast
import csv
import gzip
import json
import subprocess
import sys
import types
from collections import Counter
from itertools import pairwise
from math import hypot, sqrt
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot/src"))
from pilot.cli import drive_config
from pilot.contract import Reading
from pilot.drive import Driver

WINDOWS = [
    ("day", "20261113-225006", 13, 105),
    ("night", "20261113-230030", 565, 779),
    ("exit", "20261113-225006", 205, 236),
]


def baseline():
    module = types.ModuleType("p98_before")
    sys.modules[module.__name__] = module
    source = subprocess.check_output(
        ["git", "show", "HEAD:pilot/src/pilot/drive.py"], cwd=ROOT, text=True
    )
    exec(compile(source, "<pre-P98 drive>", "exec"), module.__dict__)  # noqa: S102 - trusted Git baseline
    source = subprocess.check_output(
        ["git", "show", "HEAD:pilot/src/pilot/cli.py"], cwd=ROOT, text=True
    )
    values = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(n, ast.Name) and n.id in {"CAREFUL", "BOLD", "MEASURED_DELAY_S"}
            for n in node.targets
        ):
            exec(  # noqa: S102 - only the three trusted style assignments
                compile(
                    ast.Module(body=[node], type_ignores=[]), "<pre-P98 styles>", "exec"
                ),
                values,
            )
    return module.Driver, module.DriveConfig(
        command_delay=values["MEASURED_DELAY_S"], **values["BOLD"]
    )


def limit_terms(path, bend, speed, cfg):
    heading = max(
        min(cfg.slow_speed, cfg.speed_limit), cfg.speed_limit / (1 + bend / 15)
    )
    curve = cfg.speed_limit
    path = path[: len(path) - cfg.curve_trim]
    travel = hypot(*path[0]) if path else 0
    peak = 0
    for i in range(len(path) - 2 * cfg.curve_step):
        a, b, c = path[i], path[i + cfg.curve_step], path[i + 2 * cfg.curve_step]
        ab, bc, ac = (
            hypot(b[0] - a[0], b[1] - a[1]),
            hypot(c[0] - b[0], c[1] - b[1]),
            hypot(c[0] - a[0], c[1] - a[1]),
        )
        if min(ab, bc) < 1:
            continue
        k = (
            2
            * abs((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]))
            / max(ab * bc * ac, 1e-6)
        )
        peak = max(peak, k)
        corner = max(
            min(cfg.slow_speed, cfg.speed_limit),
            sqrt(cfg.lateral_acceleration * cfg.map_scale_min / max(k, 1e-6)),
        )
        remaining = max(
            0,
            (travel - cfg.lookahead_px) * cfg.map_scale_min
            - (speed or 0) * (cfg.command_delay + cfg.gps_window / 2),
        )
        curve = min(curve, sqrt(corner**2 + 2 * cfg.planned_deceleration * remaining))
        travel += hypot(path[i + 1][0] - a[0], path[i + 1][1] - a[1])
    return heading, curve, peak


def replay(cls, cfg, rows, start, end):
    driver = cls(cfg)
    results = []
    previous = None
    for row in rows:
        if row["t"] >= end:
            break
        if (row.get("skill") or {}).get("name") != "drive_route":
            previous = None
            continue
        if previous is None or row["t"] - previous > 2:
            driver = cls(cfg)
        previous = row["t"]
        limits = []
        original = driver._speed_limit

        def observe_limit(path, bend, speed, original=original, limits=limits):
            value = original(path, bend, speed)
            limits.append(value)
            return value

        driver._speed_limit = observe_limit
        value = dict(row["reading"], blips=())
        value["path"] = tuple(tuple(p) for p in value["path"])
        reading = Reading(**value)
        command = driver.step(reading, row["t"], None, speed=reading.gps_speed)
        driver._speed_limit = original
        if row["t"] < start:
            continue
        bend = max(
            abs(driver._filtered_near or 0),
            cfg.far_bend * abs(driver._filtered_far or 0),
        )
        heading, curve, peak = limit_terms(reading.path, bend, driver._speed, cfg)
        limit = limits[-1] if limits else None
        cause = "heading" if heading <= curve else "curvature"
        if command.state != "follow":
            cause = command.state
        if reading.gps_speed is None:
            cause = "unknown-speed"
        if hasattr(driver, "speed_reason") and command.state == "follow":
            cause = driver.speed_reason
        actual = row["result"]["pad"]
        sent = row.get("sent_pad") or actual
        results.append(
            {
                "t": row["t"],
                "frame_id": row["frame_id"],
                "state": command.state,
                "throttle": command.throttle,
                "brake": command.brake,
                "steer": command.steer,
                "gps_speed": reading.gps_speed,
                "filtered_speed": driver._speed,
                "gps_distance": reading.gps_distance,
                "gps_time": reading.gps_time,
                "near": bend,
                "far": driver._filtered_far,
                "aim_px": driver.aim_px,
                "heading_limit": heading,
                "curve_limit": curve,
                "limit": limit,
                "cause": cause,
                "curvature": peak,
                "corrupt": reading.corrupt,
                "confidence": reading.confidence,
                "actual_throttle": actual.get("r2", 0),
                "actual_brake": actual.get("l2", 0),
                "sent_throttle": sent.get("r2", 0),
                "sent_brake": sent.get("l2", 0),
            }
        )
    return results


def summary(rows):
    if not rows:
        return {}
    durations = [min(0.5, b["t"] - a["t"]) for a, b in pairwise(rows)] + [1 / 30]
    total = sum(durations)
    return {
        "ticks": len(rows),
        "seconds": round(total, 3),
        "brake_pulses": sum(
            r["brake"] > 0 and (i == 0 or rows[i - 1]["brake"] == 0)
            for i, r in enumerate(rows)
        ),
        "no_pedal_ticks": sum(r["throttle"] == 0 for r in rows),
        "no_pedal_share": round(sum(r["throttle"] == 0 for r in rows) / len(rows), 4),
        "no_pedal_seconds": round(
            sum(dt for r, dt in zip(rows, durations) if r["throttle"] == 0), 3
        ),
        "mean_pedal": round(sum(r["throttle"] for r in rows) / len(rows), 4),
        "median_limit": round(
            median(r["limit"] for r in rows if r["limit"] is not None), 3
        ),
        "median_speed": round(
            median(r["gps_speed"] for r in rows if r["gps_speed"] is not None), 3
        ),
        "max_abs_steer": round(max(abs(r["steer"]) for r in rows), 3),
        "lift_causes": dict(Counter(r["cause"] for r in rows if r["throttle"] == 0)),
        "brake_causes": dict(Counter(r["cause"] for r in rows if r["brake"] > 0)),
    }


def main():
    old, old_cfg = baseline()
    output = {}
    audit = {}
    for name, recording, start, end in WINDOWS:
        source = Path("/Users/kerim/recordings/pilot") / recording / "play.jsonl"
        rows = [json.loads(line) for line in source.read_text().splitlines()]
        output[name] = {"recording": recording, "start": start, "end": end}
        audit[name] = {}
        for label, cls, cfg in [
            ("before", old, old_cfg),
            ("after", Driver, drive_config(["style=bold"])),
        ]:
            result = replay(cls, cfg, rows, start, end)
            output[name][label] = summary(result)
            seconds = {}
            pulses = []
            lifts = []
            for i, tick in enumerate(result):
                if tick["brake"] > 0 and (i == 0 or result[i - 1]["brake"] == 0):
                    pulses.append(tick)
                if tick["throttle"] == 0:
                    second = str(int(tick["t"]))
                    seconds.setdefault(second, []).append(
                        {
                            k: tick[k]
                            for k in (
                                "t",
                                "state",
                                "cause",
                                "gps_speed",
                                "filtered_speed",
                                "heading_limit",
                                "curve_limit",
                                "limit",
                                "gps_distance",
                                "gps_time",
                                "corrupt",
                            )
                        }
                    )
                if tick["throttle"] == 0 and (i == 0 or result[i - 1]["throttle"] != 0):
                    lifts.append(
                        {"start": tick["t"], "end": tick["t"], "cause": tick["cause"]}
                    )
                elif tick["throttle"] == 0:
                    lifts[-1]["end"] = tick["t"]
            audit[name][label] = {
                "brake_onsets": pulses,
                "lift_intervals": lifts,
                "lifted_seconds": seconds,
            }
            if label == "before":
                output[name]["recorded"] = {
                    "brake_pulses": sum(
                        r["actual_brake"] > 0
                        and (i == 0 or result[i - 1]["actual_brake"] == 0)
                        for i, r in enumerate(result)
                    ),
                    "no_pedal_share": sum(r["actual_throttle"] == 0 for r in result)
                    / len(result),
                    "mean_pedal": sum(r["actual_throttle"] for r in result)
                    / len(result),
                    "mean_sent_pedal": sum(r["sent_throttle"] for r in result)
                    / len(result),
                }
            with gzip.open(
                ROOT / "lab/drive" / f"p98-{name}-{label}.csv.gz", "wt"
            ) as stream:
                writer = csv.DictWriter(stream, fieldnames=list(result[0]))
                writer.writeheader()
                writer.writerows(result)
        # Every no-pedal second and brake onset keeps its underlying readings in the CSV.
        print(name, json.dumps(output[name]), flush=True)
    with gzip.open(ROOT / "lab/drive/p98-attribution.json.gz", "wt") as stream:
        json.dump(audit, stream, indent=2)
    (ROOT / "lab/drive/p98-replay.json").write_text(json.dumps(output, indent=2) + "\n")


if __name__ == "__main__":
    main()
