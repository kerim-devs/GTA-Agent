"""Condense final receipts and check careful against HEAD on every recorded driving tick."""

import json
import math
from collections import Counter

from p101_replay import HERE, inputs
from p101_sim import baseline

from pilot.avoid import STALE, passing_side, waits_behind
from pilot.cli import drive_config
from pilot.drive import Driver


def main():
    before = json.loads((HERE / "p101-sim-before.json").read_text())
    after = json.loads((HERE / "p101-sim-after.json").read_text())
    historical = json.loads((HERE / "p80-after.json").read_text())
    result = {"profiles": [], "recordings": {}}
    for profile in dict.fromkeys(r["profile"] for r in after["unreported"]):
        unseen = [r for r in after["unreported"] if r["profile"] == profile]
        known = [r for r in after["p80"] if r["profile"] == profile and r["after_wait"] is not None]
        result["profiles"].append(
            {
                "profile": profile,
                "p80_worst_after_wait": max(r["after_wait"] for r in known),
                "unseen_after_contact_by_wall_0_left_right": [r["after_contact"] for r in unseen],
                "latest_rejoin": max(r["joined_at"] for r in unseen),
            }
        )
    result["p80"] = {
        "passed": sum(r["passed_at"] is not None for r in after["p80"]),
        "contacts": sum(r["collisions"] for r in after["p80"]),
        "worst_reverse": max(r["longest_reverse"] for r in after["p80"]),
        "worst_delta_historical": max(
            r["after_wait"] - old["after_wait"]
            for r, old in zip(after["p80"], historical["parked"], strict=True)
            if r["after_wait"] is not None
        ),
    }
    result["unreported"] = {
        "before_passed": sum(r["passed_at"] is not None for r in before["unreported"]),
        "before_joined": sum(r["joined_at"] is not None for r in before["unreported"]),
        "after_passed": sum(r["passed_at"] is not None for r in after["unreported"]),
        "after_joined": sum(r["joined_at"] is not None for r in after["unreported"]),
        "worst_reverse": max(r["longest_reverse"] for r in after["unreported"]),
    }
    driver_before = baseline()
    for session in ("000623", "002126"):
        old, new = driver_before(drive_config(["style=careful"])), Driver(drive_config(["style=careful"]))
        states, motion, compared, differences, fresh = Counter(), Counter(), 0, 0, 0
        standing = Counter()
        for row, reading, objects, at in inputs(session):
            name = (row.get("skill") or {}).get("name")
            states[(row.get("result") or {}).get("driver_state") or name or "none"] += 1
            motion[str(row["moving"])] += 1
            fresh += at is not None and 0 <= row["t"] - at <= STALE
            if session == "000623" and 711 <= row["t"] <= 789:
                standing[str(row["moving"])] += 1
            if name != "drive_route":
                continue
            kwargs = dict(
                speed=reading.gps_speed,
                ahead=waits_behind(objects, at, row["t"]),
                bypass_side=passing_side(objects, at, row["t"]),
            )
            a = old.step(reading, row["t"], row["moving"], **kwargs)
            b = new.step(reading, row["t"], row["moving"], **kwargs)
            differences += a != b
            compared += 1
        result["recordings"][session] = {
            "states": states,
            "motion": motion,
            "stationary_window_motion": standing,
            "careful_compared": compared,
            "careful_differences": differences,
            "fresh_sparse_box_ticks": fresh,
        }
    human = []
    for event in json.loads((HERE / "p101-human-detail.json").read_text()):
        rows = [r for r in event["samples"] if r["pad"].get("l2", 0) > 0.2]
        good = [r for r in rows if r["shift_px"] is not None and r["arrow"] is not None]
        reverse = sum(
            r["shift_px"][0] * math.sin(math.radians(r["arrow"]))
            - r["shift_px"][1] * math.cos(math.radians(r["arrow"]))
            for r in good
        )
        human.append(
            {
                "session": event["session"],
                "start": event["start"],
                "l2_samples": len(rows),
                "valid_samples": len(good),
                "signed_reverse_map_pixels": reverse,
            }
        )
    result["human"] = human
    (HERE / "p101-summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
