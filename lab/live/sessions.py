"""What the pilot did over a set of its sessions, counted: how long each skill ran, how each run ended,
how often the head changed its mind, and how far the drives got.

    pilot/.venv/bin/python lab/live/sessions.py /Users/kerim/recordings/pilot/20261112-10*
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


def runs(rows):
    """Each stretch one skill was active: name, start, end, how it ended, why."""
    out, current = [], None
    for row in rows:
        skill = row.get("skill") or {}
        name, status = skill.get("name"), skill.get("status")
        if status == "running":
            if current is None or current["name"] != name:
                current = {"name": name, "start": row["t"], "end": row["t"], "status": None, "reason": None}
                current["first"] = row["reading"]
                out.append(current)
            current["end"] = row["t"]
            current["last"] = row["reading"]
        elif current is not None and name == current["name"]:
            current["status"], current["reason"] = status, str(skill.get("reason"))
            current = None
    return out


def main(folders):
    seconds = requests = replaced = 0.0
    time, ends, events, drives = defaultdict(float), defaultdict(Counter), Counter(), []
    for folder in map(Path, folders):
        play, head = folder / "play.jsonl", folder / "head.jsonl"
        if not play.exists() or not head.exists():
            continue
        rows = [json.loads(line) for line in play.open()]
        if not rows:
            continue
        seconds += rows[-1]["t"]
        for run in runs(rows):
            time[run["name"]] += run["end"] - run["start"]
            reason = (run["reason"] or "").split(";")[0]
            ends[run["name"]][f"{run['status'] or 'cut off'}: {reason}" if run["status"] else "cut off"] += 1
            if run["name"] == "drive_route":
                a, b = run["first"].get("gps_distance"), run["last"].get("gps_distance")
                drives.append((folder.name, run["end"] - run["start"], a, b, run["reason"]))
        for line in head.open():
            row = json.loads(line)
            if row["type"] == "request":
                requests += 1
                for event in row["request"]["events"]:
                    events[event.get("kind", "?")] += 1
            elif row.get("disposition") == "replaced":
                replaced += 1
    minutes = seconds / 60
    print(f"{minutes:.1f} minutes, {requests / minutes:.1f} requests a minute, {replaced / minutes:.1f} plans replaced a minute")
    print("events: " + ", ".join(f"{kind} {count}" for kind, count in events.most_common(12)))
    print(f"{'skill':<14}{'runs':>5}{'seconds':>9}  endings")
    for name, total in sorted(time.items(), key=lambda item: -item[1]):
        endings = ", ".join(f"{count}x {how}" for how, count in ends[name].most_common(6))
        print(f"{name:<14}{sum(ends[name].values()):>5}{total:>9.0f}  {endings}")
    print("drives: session, seconds, metres to go at start and end, ending")
    for name, length, a, b, reason in drives:
        if length >= 5:
            print(f"  {name} {length:5.0f} s  {a} -> {b}  {reason}")


if __name__ == "__main__":
    main(sys.argv[1:])
