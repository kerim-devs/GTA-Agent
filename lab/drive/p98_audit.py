"""Attribute every recorded pedal-off tick and L2 onset, including non-speed actions."""

import csv
import gzip
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def audit(name, session):
    with gzip.open(ROOT / "lab/drive" / f"p98-{name}-before.csv.gz", "rt") as stream:
        ticks = list(csv.DictReader(stream))
    source = {
        row["frame_id"]: row
        for row in map(
            json.loads,
            (Path("/Users/kerim/recordings/pilot") / session / "play.jsonl")
            .read_text()
            .splitlines(),
        )
    }
    seconds, pulses, reasons = {}, [], Counter()
    for i, tick in enumerate(ticks):
        brake, throttle = float(tick["actual_brake"]), float(tick["actual_throttle"])
        reading = source[int(tick["frame_id"])]["reading"]
        reason = tick["cause"]
        if brake == 1:
            reason = (
                "route-gone stop"
                if reading["route"] == "none"
                else "intentional reverse phase"
            )
        elif brake == 0.6 and float(tick["brake"]) < 0.6:
            reason = "urgent-obstacle signature; original boxes not logged"
        elif brake > 0:
            reason = (
                "heading speed limit"
                if float(tick["heading_limit"]) <= float(tick["curve_limit"])
                else "curvature speed limit"
            )
            if tick["state"] == "coast":
                reason += ", inherited through coast"
        elif throttle == 0:
            if tick["state"] != "follow":
                reason = tick["state"]
            elif float(tick["throttle"]) == 0:
                reason += " speed limit"
            else:
                reason = "not reproduced without original motion/obstacle state"
        item = {**tick, "attribution": reason}
        if brake > 0 and (i == 0 or float(ticks[i - 1]["actual_brake"]) == 0):
            pulses.append(item)
        if throttle == 0:
            seconds.setdefault(str(int(float(tick["t"]))), []).append(item)
            reasons[reason] += 1
    return {
        "recorded_L2_onsets": pulses,
        "every_pedal_off_second": seconds,
        "pedal_off_tick_causes": dict(reasons),
        "pulse_causes": dict(Counter(p["attribution"] for p in pulses)),
    }


if __name__ == "__main__":
    results = {}
    for name, session in [
        ("day", "20261113-225006"),
        ("night", "20261113-230030"),
        ("exit", "20261113-225006"),
    ]:
        results[name] = audit(name, session)
        print(
            name, results[name]["pulse_causes"], results[name]["pedal_off_tick_causes"]
        )
    with gzip.open(ROOT / "lab/drive/p98-recorded-attribution.json.gz", "wt") as stream:
        json.dump(results, stream, indent=2)
