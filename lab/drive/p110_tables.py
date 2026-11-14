"""Render the complete episode inventory and summarize the saved measurements."""

import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
episodes = json.loads((HERE / "p110-episodes.json").read_text())["episodes"]
active = [e for e in episodes if "bypass-reverse" in e["phases"]]


def counts(rows):
    return dict(
        episodes=len(rows),
        near_over_45=sum(e["end"]["near"] is not None and abs(e["end"]["near"]) > 45 for e in rows),
        far_over_45=sum(e["end"]["far"] is not None and abs(e["end"]["far"]) > 45 for e in rows),
        following_proxy=sum(e["within_5s"] for e in rows),
        origins=Counter(e["source_inferred"] for e in rows),
    )


lines = [
    "| # | Recording | Seconds | Kind | Near degrees | Far degrees | Printed metres | Origin | Follow in 5 s |",
    "|---:|---|---|---|---|---|---|---|---|",
]
for i, e in enumerate(episodes, 1):

    def number(value):
        return "?" if value is None else f"{value:.1f}"

    def pair(key):
        return f"{number(e['start'][key])} → {number(e['end'][key])}"

    distance = (
        f"{number(e['first_distance'])} → {number(e['last_distance'])} ({number(e['distance_change'])})"
    )
    kind = "R" if "bypass-reverse" in e["phases"] else "W" if e["phases"] == ["bypass-wait"] else "F"
    origin = {"detected": "D", "blind": "B", "unknown": "?"}[e["source_inferred"]]
    lines.append(
        f"| {i} | {e['session'][-6:]} | {e['start']['t']:.2f}–{e['until']:.2f} | {kind} | "
        f"{pair('near')} | {pair('far')} | {distance} | {origin} | {'yes' if e['within_5s'] else 'no'} |"
    )
(HERE / "p110-episodes.md").write_text("\n".join(lines) + "\n")
print("Morning:", json.dumps(dict(all=counts(episodes), reversed=counts(active))))
for label in ("before", "after"):
    data = json.loads((HERE / f"p110-sim-{label}.json").read_text())
    for blocked in (0, -1, 1):
        rows = [r for r in data["parked"] if r["blocked"] == blocked]
        print(
            label,
            blocked,
            "passed",
            sum(r["passed_at"] is not None for r in rows),
            "joined",
            sum(r["joined_at"] is not None for r in rows),
            "max_heading",
            max(r["max_heading"] for r in rows),
            "end_heading",
            max(r["end_heading"] for r in rows),
            "reverse_leg",
            max(r["longest_retreat_m"] for r in rows),
            "total_reverse",
            max(r["reversed_m"] for r in rows),
            "command_reverse",
            max(r.get("longest_commanded_retreat_m", 0) for r in rows),
        )
