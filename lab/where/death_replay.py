"""Replay the recorded no-map/accepted-vehicle contradiction against both versions."""

import bisect
import json
import subprocess
import sys
import types
from dataclasses import asdict, fields
from pathlib import Path

from measure import HERE, ROOT
from pilot.contract import Answer, Judgment, Observation, Reading
from pilot.vehicle_entry import EnterVehicle


def main():
    source = Path("/Users/kerim/recordings/pilot/20261112-143128")
    play = list(map(json.loads, (source / "play.jsonl").read_text().splitlines()))
    judges = [
        r
        for r in map(json.loads, (source / "judge.jsonl").read_text().splitlines())
        if r.get("answers")
    ]
    offset = 360103.727126
    arrivals = [r["t"] - offset for r in judges]
    module = types.ModuleType("pilot._p60_before_death")
    sys.modules[module.__name__] = module
    original = subprocess.check_output(
        ["git", "show", "HEAD:pilot/src/pilot/vehicle_entry.py"], cwd=ROOT, text=True
    )
    exec(compile(original, "HEAD:vehicle_entry.py", "exec"), module.__dict__)
    before, after = module.EnterVehicle({}), EnterVehicle({})
    # The original run already pressed. Replay just the continuous seat-proof window.
    before.attempts = after.attempts = 1
    allowed = {f.name for f in fields(Reading)}
    rows = []
    for tick in play:
        t = tick["t"]
        if not 20 <= t <= 24.5:
            continue
        j = judges[max(0, bisect.bisect_right(arrivals, t) - 1)]
        judgment = Judgment(
            j["capture"] - offset,
            {k: Answer(**v) for k, v in j["answers"].items()},
            j["probabilities"],
            j["duration"],
            j["server"],
        )
        obs = Observation(
            Reading(**{k: v for k, v in tick["reading"].items() if k in allowed}),
            None,
            t,
            judgment=judgment,
            mode=j.get("mode"),
        )
        old, new = before.step(obs), after.step(obs)
        rows.append(
            {
                "t": t,
                "minimap": obs.reading.minimap,
                "accepted_mode": obs.mode,
                "raw_mode": j["answers"]["mode"],
                "before": asdict(old),
                "after": asdict(new),
            }
        )
    (HERE / "death-replay.json").write_text(
        json.dumps(
            {
                "scope": "Seat-proof window only; uses recorded readings and original judge replies, no movement simulation",
                "clock_offset": offset,
                "ticks": rows,
            },
            separators=(",", ":"),
        )
        + "\n"
    )
    print(
        "ticks",
        len(rows),
        "old done",
        sum(r["before"]["status"] == "done" for r in rows),
        "new done",
        sum(r["after"]["status"] == "done" for r in rows),
    )
    print(
        "first old success",
        next((r["t"] for r in rows if r["before"]["status"] == "done"), None),
    )


if __name__ == "__main__":
    main()
