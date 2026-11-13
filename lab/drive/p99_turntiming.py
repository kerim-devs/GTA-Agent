"""Measure the turn handover against P80's per-car alignment times."""

import inspect
import json
import textwrap
from pathlib import Path

from p99_evaluate import trial
from pilot.drive import Driver
from pilot.sim import CAR_PROFILES

HERE = Path(__file__).resolve().parent


def main():
    rows = []
    original = textwrap.dedent(inspect.getsource(Driver._manoeuvre))
    for threshold in (40, 50, 60, 70, 80):
        scope = dict(Driver._manoeuvre.__globals__)
        source = original.replace(
            "if abs(error) > 60 and elapsed", f"if abs(error) > {threshold} and elapsed"
        )
        exec(compile(source, __file__, "exec"), scope)  # noqa: S102 - local driver source only
        candidate = type("Candidate", (Driver,), {"_manoeuvre": scope["_manoeuvre"]})
        times = {p: trial(candidate, p, "behind")["aligned_at"] for p in CAR_PROFILES}
        rows.append({"threshold": threshold, "times": times})
        print(json.dumps(rows[-1]), flush=True)
    (HERE / "p99-turn-timing.json").write_text(json.dumps(rows, indent=2) + "\n")


if __name__ == "__main__":
    main()
