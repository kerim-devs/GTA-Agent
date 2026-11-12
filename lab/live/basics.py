"""Counts the tries of lab/live/basics.sh: per basic skill how many worked, and how each of the others ended.

    pilot/.venv/bin/python lab/live/basics.py [/Users/kerim/recordings/pilot/basics.tsv]
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

SKILL = {
    "leave": "press",
    "walk": "walk_road",
    "enter": "enter_vehicle",
    "waypoint": "set_waypoint",
    "drive": "drive_route",
}


def judge(step, folder):
    """(worked, what happened) for one try, from the session's own log."""
    rows = [json.loads(line) for line in (folder / "play.jsonl").open()]
    if not rows:
        return False, "no ticks"
    mine = [row for row in rows if (row.get("skill") or {}).get("name") == SKILL[step]]
    if not mine:
        return False, "the skill never ran"
    last = mine[-1]["skill"]
    status, reason = last.get("status"), str(last.get("reason") or "").split(";")[0]
    seconds = mine[-1]["t"] - mine[0]["t"]
    tail = [row["reading"].get("minimap") for row in rows[-30:]]
    seated = tail.count("tilted") > tail.count("flat")
    if step == "leave":
        return (not seated), "on foot afterwards" if not seated else "still seated"
    if step == "walk":
        motion = Counter(
            str(row["skill"].get("reason")).rsplit("motion=", 1)[-1]
            for row in mine
            if "motion=" in str(row["skill"].get("reason"))
        )
        moved = motion["going"] / max(1, sum(motion.values()))
        ok = status in ("done", "running") and motion["going"] > motion["still"]
        return ok, f"{status} ({reason}), going on {moved:.0%} of ticks, still on {motion['still']}"
    if step == "enter":
        ok = status == "done" and seated
        return ok, f"{status} ({reason}) after {seconds:.0f} s, {'seated' if seated else 'on foot'} at the end"
    if step == "waypoint":
        return status == "done", f"{status} ({reason}) after {seconds:.0f} s"
    distances = [row["reading"].get("gps_distance") for row in mine]
    distances = [value for value in distances if value is not None]
    gained = distances[0] - distances[-1] if len(distances) > 1 else None
    ok = status in ("done", "running") and seconds >= 45
    way = "distance not read" if gained is None else f"{gained:.0f} m nearer"
    return ok, f"{status} ({reason}) after {seconds:.0f} s, {way}"


def main(path):
    tries = defaultdict(list)
    for line in Path(path).read_text().splitlines():
        cycle, step, folder = line.split("\t")
        try:
            tries[step].append((cycle, Path(folder).name, *judge(step, Path(folder))))
        except (OSError, ValueError, KeyError) as error:
            tries[step].append((cycle, Path(folder).name, False, f"unreadable: {error}"))
    for step in SKILL:
        rows = tries.get(step, [])
        print(f"{step}: {sum(row[2] for row in rows)} of {len(rows)} worked")
        for cycle, name, ok, what in rows:
            print(f"  {cycle} {name} {'ok ' if ok else 'NO '} {what}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/Users/kerim/recordings/pilot/basics.tsv")
