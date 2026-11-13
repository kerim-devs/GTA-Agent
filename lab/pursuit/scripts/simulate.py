"""Full P78 profile matrix, separate from the repository's 90-second smoke gate."""

import hashlib
import json
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "pilot/src"), str(ROOT / "pilot/tests")]

from test_pursuit_worlds import assert_world, run_world  # noqa: E402

from pilot.sim import CAR_PROFILES  # noqa: E402


def main():
    cv2.setNumThreads(1)
    evidence = ROOT / "lab/pursuit/simulation.json"
    receipt = ROOT / "lab/pursuit/simulation-meta.json"
    sources = [
        ROOT / "pilot/src/pilot/pursuit.py",
        ROOT / "pilot/tests/test_pursuit_worlds.py",
        ROOT / "pilot/src/pilot/sim.py",
        Path(__file__),
    ]
    digest = hashlib.sha256(b"".join(path.read_bytes() for path in sources)).hexdigest()
    rows = (
        json.loads(evidence.read_text())
        if receipt.exists() and json.loads(receipt.read_text()).get("source_sha256") == digest
        else []
    )
    failures = []

    def measured(mode, profile, scenario=None):
        previous = next(
            (
                r
                for r in rows
                if r["mode"] == mode and r["profile"] == profile and r.get("scenario") == scenario
            ),
            None,
        )
        if previous is not None:
            return previous
        settings = {scenario: True, "seconds": 30} if scenario else {}
        result = run_world(mode, profile, **settings)
        result.pop("rows")
        if scenario:
            result["scenario"] = scenario
        rows.append(result)
        evidence.write_text(json.dumps(rows, indent=2) + "\n")
        receipt.write_text(
            json.dumps({"source_sha256": digest, "runs": len(rows), "complete": False}, indent=2) + "\n"
        )
        print(json.dumps(result), flush=True)
        return result

    for mode in ("follow", "catch", "reach"):
        for profile in CAR_PROFILES:
            result = measured(mode, profile)
            try:
                assert_world(result)
            except AssertionError:
                failures.append((mode, profile))
    for profile in CAR_PROFILES:
        for setting in ("water", "held", "traffic"):
            result = measured("catch", profile, setting)
            if result["water"] or result["held"] > 5 or not result["no_buttons"]:
                failures.append((setting, profile))
    receipt.write_text(
        json.dumps(
            {"source_sha256": digest, "runs": len(rows), "complete": True, "failures": failures}, indent=2
        )
        + "\n"
    )
    print(f"{len(rows)} runs; failures: {failures}", flush=True)
    raise SystemExit(bool(failures))


if __name__ == "__main__":
    main()
