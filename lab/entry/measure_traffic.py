"""Measure reviewed traffic entries from human pads and manifest-clock action labels.

Reads recordings without changing them. Stop windows and position are visual annotations,
not inferred from an enter_vehicle label. A tilted action start is a mode-change proxy,
not the exact seated frame. Decode videos using frames.jsonl.i, never MP4 media time.
"""

from __future__ import annotations

import argparse
import json
from bisect import bisect_left
from pathlib import Path
from statistics import median

# Four driver removals in road traffic, reviewed in P57 and rechecked for P90.
# The driveway removal in 20261111-180814 is deliberately not a traffic take.
REVIEWED = {
    "20261111-175312": (
        623.0553,
        None,
        "lane",
        "Already stopped at 618.0; stop-to-press >=5.1s.",
    ),
    "20261111-182316": (529.2306, (528.9, 529.1), "lane", "Visible driver removed."),
    "20261111-183820": (
        676.1844,
        (675.9, 676.0),
        "lane",
        "Approaching car stops; visible driver removed.",
    ),
    "20261111-214652": (
        114.6581,
        (113.2, 113.4),
        "edge to lane",
        "Starts beside curb; visible driver removed.",
    ),
}


def rows(path):
    with path.open() as stream:
        return [json.loads(line) for line in stream if line.strip()]


def triangle_presses(pads):
    down = None
    for row in pads:
        held = "triangle" in row.get("buttons", [])
        if held and down is None:
            down = row["t"]
        elif not held and down is not None:
            yield down, row["t"]
            down = None


def measure(raw_root, derived_root, ledger):
    takes = []
    events = json.loads(ledger.read_text())["events"]
    for session, (expected_down, stop, position, notes) in REVIEWED.items():
        entries = [
            e
            for e in events
            if e["session"] == session
            and e.get("entry_interaction") == "forced_driver_removal"
        ]
        event = min(entries, key=lambda e: abs(e["start"] - expected_down))
        actions = rows(derived_root / session / "actions.jsonl")
        candidates = [
            (i, a) for i, a in enumerate(actions) if a["action"] == "enter_vehicle"
        ]
        index, entry = min(
            candidates, key=lambda item: abs(item[1]["start"] - event["start"])
        )
        if abs(entry["start"] - event["start"]) > 0.5:
            raise ValueError(
                f"{session}: derived entry no longer matches reviewed ledger"
            )
        down, up = min(
            triangle_presses(rows(raw_root / session / "pad.jsonl")),
            key=lambda pair: abs(pair[0] - expected_down),
        )
        if abs(down - expected_down) > 0.01:
            raise ValueError(f"{session}: reviewed Triangle press missing")
        tilted = next(
            (
                a
                for a in actions[index + 1 :]
                if a["start"] - down <= 10
                and a.get("evidence", {})
                .get("readers", {})
                .get("minimap", {})
                .get("tilted", 0)
            ),
            None,
        )
        if tilted is None:
            raise ValueError(f"{session}: no subsequent tilted state within 10s")
        frames = rows(raw_root / session / "frames.jsonl")
        frame_index = bisect_left([f["t"] for f in frames], down)
        frame = frames[frame_index]
        takes.append(
            {
                "session": session,
                "ledger_index": event["index"],
                "derived_line": index + 1,
                "entry_start": entry["start"],
                "triangle_down": down,
                "triangle_up": up,
                "press_seconds": round(up - down, 4),
                "press_frame": {key: frame[key] for key in ("i", "frame_id", "t")},
                "first_tilted_action": {
                    "t": tilted["start"],
                    "delta_seconds": round(tilted["start"] - down, 4),
                },
                "wanted": {
                    "entry": entry["evidence"]["readers"].get("wanted"),
                    "first_tilted": tilted["evidence"]["readers"].get("wanted"),
                },
                "ledger": {
                    key: event.get(key)
                    for key in (
                        "motion_context",
                        "occupancy",
                        "press_location",
                        "entry_interaction",
                    )
                },
                "manual": {
                    "stop_window": stop,
                    "stop_to_press_window": [
                        round(down - stop[1], 4),
                        round(down - stop[0], 4),
                    ]
                    if stop
                    else None,
                    "position": position,
                    "seat_frame": None,
                    "notes": notes,
                },
            }
        )

    def stats(values):
        return {"min": min(values), "median": median(values), "max": max(values)}

    return {
        "schema": 1,
        "sources": {
            "raw": str(raw_root),
            "derived": str(derived_root),
            "ledger": str(ledger),
        },
        "summary": {
            "strict_traffic_takes": len(takes),
            "below_five": len(takes) < 5,
            "press_seconds": stats([t["press_seconds"] for t in takes]),
            "press_to_tilted_seconds": stats(
                [t["first_tilted_action"]["delta_seconds"] for t in takes]
            ),
            "wanted_after_count": sum(bool(t["wanted"]["first_tilted"]) for t in takes),
        },
        "takes": takes,
        "limits": (
            "Four manually reviewed traffic takes, not all successful entries. "
            "Action start is not exact seated time. Driver response and road position "
            "are visual interpretation; no success rate is inferred."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw-root", type=Path, default=Path("/Users/kerim/recordings/kerim")
    )
    parser.add_argument(
        "--derived-root",
        type=Path,
        default=Path("/Users/kerim/recordings/derived/kerim"),
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "enter/p57-entries.json",
    )
    args = parser.parse_args()
    print(json.dumps(measure(args.raw_root, args.derived_root, args.ledger), indent=2))


if __name__ == "__main__":
    main()
