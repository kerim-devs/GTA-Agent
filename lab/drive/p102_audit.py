"""Every recorded brake onset and lifted second, with explicit limits on attribution."""

import csv
import gzip
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot/src"))


def scene(name, t):
    if name == "town":
        if t < 216:
            return "right junction ahead; visible in the route, still on the approach"
        if t < 224:
            return "right junction entered and exited"
        if t < 235.5:
            return "left junction ahead"
        if t < 240:
            return "left junction and crossing red car ahead"
        return "shallow S bend on the current road and a right route turn farther ahead"
    if t < 102.8:
        return "straight current block; distant right bend at the map rim; lorry left and van right"
    if t < 103.5:
        return "police vehicle enters the own track; contact begins before hidden-turn"
    return "post-contact car turned across the route; hidden-turn is a response to changed heading"


def main():
    audit = {}
    for name in ("town", "incident"):
        with gzip.open(
            ROOT / "lab/drive" / f"p102-{name}-before.csv.gz", "rt"
        ) as stream:
            before = list(csv.DictReader(stream))
        by_time = {float(r["t"]): r for r in before}
        with gzip.open(
            ROOT / "lab/drive" / f"p102-{name}-readings.json.gz", "rt"
        ) as stream:
            recorded = [
                r
                for r in json.load(stream)
                if (r.get("skill") or {}).get("name") == "drive_route"
            ]
        pulses = []
        seconds = defaultdict(Counter)
        last = False
        for i, row in enumerate(recorded):
            t = row["t"]
            result = row["result"]
            pad = result["pad"]
            dt = min(0.5, recorded[i + 1]["t"] - t) if i + 1 < len(recorded) else 1 / 30
            isolated = by_time.get(t, {})
            around = result.get("around_pedal")
            urgent = around == -1 or (around is None and pad.get("l2") == 0.6)
            cause = (
                "vehicle urgent"
                if urgent
                else result.get("speed_reason") or isolated.get("cause", "unreproduced")
            )
            if pad.get("l2", 0) > 0 and not last:
                pulses.append(
                    dict(
                        t=round(t, 3),
                        cause=cause,
                        around_pedal=around,
                        scene=scene(name, t),
                        brake=pad["l2"],
                        original_boxes="not logged",
                    )
                )
            last = pad.get("l2", 0) > 0
            if pad.get("r2", 0) == 0:
                seconds[int(t)][cause] += dt
        audit[name] = dict(
            recorded_pulses=pulses,
            recorded_lifted_seconds=[
                dict(second=k, causes=v, scene=scene(name, k + 0.5))
                for k, v in seconds.items()
            ],
        )
        for label in ("before", "after"):
            with gzip.open(
                ROOT / "lab/drive" / f"p102-{name}-{label}.csv.gz", "rt"
            ) as stream:
                rows = list(csv.DictReader(stream))
            pulses = []
            seconds = defaultdict(Counter)
            last = False
            for i, r in enumerate(rows):
                t = float(r["t"])
                brake = float(r["brake"])
                dt = (
                    min(0.5, float(rows[i + 1]["t"]) - t)
                    if i + 1 < len(rows)
                    else 1 / 30
                )
                if brake and not last:
                    pulses.append(
                        dict(t=round(t, 3), cause=r["cause"], scene=scene(name, t))
                    )
                last = bool(brake)
                if float(r["throttle"]) == 0:
                    seconds[int(t)][r["cause"]] += dt
            audit[name][label] = dict(
                pulses=pulses,
                lifted_seconds=[
                    dict(second=k, causes=v, scene=scene(name, k + 0.5))
                    for k, v in seconds.items()
                ],
            )
        print(
            name,
            "recorded pulses",
            len(audit[name]["recorded_pulses"]),
            Counter(p["cause"] for p in audit[name]["recorded_pulses"]),
        )
    human = []
    for name, start, end, sections in [
        (
            "20261113-141634",
            198,
            218,
            [
                ("approach-left", 202, 205),
                ("left-turn", 205, 207),
                ("between", 208, 211),
                ("approach-right", 211, 214),
                ("right-turn", 214, 216),
            ],
        ),
        (
            "20261113-180503",
            73,
            81,
            [("approach-right", 76, 79), ("right-turn", 79, 81)],
        ),
    ]:
        with gzip.open(
            ROOT / "lab/drive" / f"p102-human-{name}.json.gz", "rt"
        ) as stream:
            rows = json.load(stream)
        pads = [
            json.loads(l)
            for l in (Path("/Users/kerim/recordings/kerim") / name / "pad.jsonl").open()
        ]
        pads = [p for p in pads if p.get("src") == "human"]
        intervals = []
        lift = brake = 0.0
        for i, p in enumerate(pads[:-1]):
            a = max(start, p["t"])
            b = min(end, pads[i + 1]["t"])
            if b <= a:
                continue
            if p.get("r2", 0) == 0:
                lift += b - a
            if p.get("l2", 0) > 0:
                brake += b - a
            kind = (
                "brake"
                if p.get("l2", 0) > 0
                else "lift"
                if p.get("r2", 0) == 0
                else "pedal"
            )
            if (
                intervals
                and intervals[-1]["kind"] == kind
                and abs(intervals[-1]["end"] - a) < 0.001
            ):
                intervals[-1]["end"] = b
            else:
                intervals.append(dict(kind=kind, start=a, end=b))
        measurements = []
        for label, a, b in sections:
            subset = [r for r in rows if a <= r["t"] < b and r["speed"] is not None]
            speeds = [r["speed"] for r in subset]
            measurements.append(
                dict(
                    section=label,
                    start=a,
                    end=b,
                    speed_samples=len(speeds),
                    median_gps_speed=round(median(speeds), 3) if speeds else None,
                    min_gps_speed=round(min(speeds), 3) if speeds else None,
                    max_gps_speed=round(max(speeds), 3) if speeds else None,
                )
            )
        human.append(
            dict(
                recording=name,
                start=start,
                end=end,
                lift_seconds=lift,
                brake_seconds=brake,
                l2_share=brake / (end - start),
                intervals=intervals,
                sections=measurements,
            )
        )
        print(name, json.dumps(human[-1]))
    (ROOT / "lab/drive/p102-audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    (ROOT / "lab/drive/p102-human.json").write_text(json.dumps(human, indent=2) + "\n")


if __name__ == "__main__":
    main()
