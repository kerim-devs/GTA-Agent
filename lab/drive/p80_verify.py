"""Check P80 acceptance against the captured P73 baseline and final matrix."""

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    before = json.loads((HERE / "p80-before.json").read_text())["rows"]
    after = json.loads((HERE / "p80-after.json").read_text())
    reference = {(r["profile"], r["scenario"], r["style"]): r for r in before}
    assert len(before) == len(after["rows"]) == 66
    for row in after["rows"]:
        old = reference[row["profile"], row["scenario"], row["style"]]
        assert row["reached"], row
        if row["style"] == "careful":
            assert row == old, (old, row)
        else:
            assert row["elapsed"] <= old["elapsed"], (old, row)
    behind = [r for r in after["rows"] if r["style"] == "bold" and r["scenario"] == "behind"]
    assert len(behind) == 11
    assert sum(r["aligned_at"] < 6 for r in behind) >= 9, behind
    assert all(r["aligned_at"] < 8 and r["max_standing_outside_recovery"] <= 1 for r in behind)
    assert len(after["parked"]) == 110
    for row in after["parked"]:
        assert row["passed_at"] is not None and row["collisions"] == 0, row
        if row["gap"] == 12:
            assert row["phases"] == [[0.0, "follow"]] and not row["stopped_after_rolling"], row
        else:
            assert row["after_wait"] <= 6, row
            assert row["reverse_started"] - row["queue_started"] >= 2 - 1 / 30 - 1e-8, row
            assert row["longest_reverse"] <= 0.9 + 1 / 30 + 1e-8, row
            side = 1 if row["blocked"] == -1 else -1
            assert row["first_side"] == side and row["position"][0] * side > 0, row
    print("PASS: 33 careful rows identical; 33 bold arrivals no later; "
        f"{sum(r['aligned_at'] < 6 for r in behind)}/11 turns under 6 s, 11/11 under 8 s; "
        "99 close-car trials within 6 s after the wait without contact; "
        "11 distant trials without stopping; free sides and reverse bounds checked.")


if __name__ == "__main__":
    main()
