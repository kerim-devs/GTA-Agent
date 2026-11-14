"""P102 before/after replay of recorded reader ticks; commands cannot move the recorded car."""

import argparse
import csv
import gzip
import json
import sys
from collections import Counter, defaultdict
from math import hypot
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot/src"))
from p98_replay import baseline, replay, summary
from pilot.cli import drive_config
from pilot.drive import Driver

WINDOWS = [
    ("town", "20261114-010438", 200, 251),
    ("incident", "20261114-011017", 96, 106),
    ("freeway", "20261114-005357", 400, 520),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticks", action="store_true")
    args = parser.parse_args()
    old, old_cfg = baseline()
    totals = {}
    for name, recording, start, end in WINDOWS:
        source = Path("/Users/kerim/recordings/pilot") / recording / "play.jsonl"
        rows = [json.loads(line) for line in source.open()]
        rows = [row for row in rows if row.get("reading")]
        actual = {r["t"]: r for r in rows}
        totals[name] = {}
        for label, cls, cfg in [
            ("before", old, old_cfg),
            ("after", Driver, drive_config(["style=bold"])),
        ]:
            results = replay(cls, cfg, rows, start, end)
            pulses, seconds = [], defaultdict(Counter)
            for i, r in enumerate(results):
                original = actual[r["t"]]
                reading = original["reading"]
                path = reading["path"]
                r["around_pedal"] = original["result"].get("around_pedal")
                r["logged_reason"] = original["result"].get("speed_reason")
                r["path_points"] = len(path)
                r["path_length_px"] = (
                    hypot(*path[0])
                    + sum(
                        hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(path, path[1:])
                    )
                    if path
                    else 0
                )
                r["map_scale"] = Driver(cfg)._map_scale(r["filtered_speed"])
                dt = (
                    min(0.5, results[i + 1]["t"] - r["t"])
                    if i + 1 < len(results)
                    else 1 / 30
                )
                if r["throttle"] == 0:
                    seconds[int(r["t"])][r["cause"]] += dt
                if r["brake"] and (i == 0 or not results[i - 1]["brake"]):
                    pulses.append(
                        {
                            k: r[k]
                            for k in (
                                "t",
                                "cause",
                                "limit",
                                "filtered_speed",
                                "around_pedal",
                                "logged_reason",
                            )
                        }
                    )
                if args.ticks and name == "incident":
                    print(
                        label,
                        f"{r['t']:.3f}",
                        r["limit"],
                        r["cause"],
                        r["throttle"],
                        r["brake"],
                    )
            with gzip.open(
                ROOT / "lab/drive" / f"p102-{name}-{label}.csv.gz", "wt"
            ) as stream:
                writer = csv.DictWriter(stream, fieldnames=list(results[0]))
                writer.writeheader()
                writer.writerows(results)
            totals[name][label] = {
                **summary(results),
                "pulses": pulses,
                "lifted_seconds": seconds,
            }
            print(name, label, json.dumps(summary(results)), flush=True)
        with gzip.open(
            ROOT / "lab/drive" / f"p102-{name}-readings.json.gz", "wt"
        ) as stream:
            json.dump([r for r in rows if start <= r["t"] < end], stream)
    (ROOT / "lab/drive/p102-replay.json").write_text(
        json.dumps(totals, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
