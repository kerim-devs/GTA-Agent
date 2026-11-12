"""What the session on the pier shows, from the table `measure.py` wrote and the session's judge log.

    pilot/.venv/bin/python lab/foot/session.py /Users/kerim/recordings/pilot/20261111-204712 lab/foot/stuck-session.jsonl

A tick counts as pushed when the left stick sent is at least 0.5 away from the centre. It counts as
still when the ground under the arrow moved less than 0.3 crop pixels in half a second (`shift`), or,
where that cannot be told, when the pipeline's map motion lies in its stationary band (`moving` False).
Walking freely moves the ground 0.7 to 1.0 pixels in half a second on this map, sprinting 2 to 3.5.
"""

import json
import sys
from pathlib import Path


def pushed(row):
    left = row["left"] or (0, 0)
    return abs(left[0]) + abs(left[1]) >= 0.5


def still(row):
    if row["shift"] is not None:
        return row["shift"] < 0.3
    return row["moving"] is False


def going(row):
    if row["shift"] is not None:
        return row["shift"] >= 0.5
    return row["moving"] is True


def main(recording: Path, table: Path):
    rows = [json.loads(line) for line in table.open()]
    heads = [json.loads(line) for line in (recording / "head.jsonl").open()]
    play_first = json.loads((recording / "play.jsonl").open().readline())["t"]
    origin = heads[0]["t"] - play_first
    judgments = [json.loads(line) for line in (recording / "judge.jsonl").open()]
    judgments = [j for j in judgments if j.get("answers")]
    total = rows[-1]["t"] - rows[0]["t"]
    dt = total / len(rows)
    push = [r for r in rows if pushed(r)]
    stuck = [r for r in push if still(r)]
    moved = [r for r in push if going(r)]
    unknown = len(push) - len(stuck) - len(moved)
    print(f"session {total:.0f} s, {len(rows)} ticks, {dt * 1000:.0f} ms a tick")
    print(
        f"stick pushed: {len(push) * dt:.0f} s; of it still {len(stuck) * dt:.0f} s, "
    )
    print(f"  moving {len(moved) * dt:.0f} s, between or unknown {unknown * dt:.0f} s")
    print("seconds with at least half of their pushed ticks still: ", end="")
    by = {}
    for r in push:
        by.setdefault(int(r["t"]), []).append(still(r))
    seconds = [s for s, v in by.items() if sum(v) >= len(v) / 2]
    print(len(seconds))
    # Judge answers on the path, sorted by what the figure did at the frame it was asked about.
    still_set = set(seconds)
    path = {"still": {}, "other": {}}
    blocked_p = {"still": [], "other": []}
    for j in judgments:
        capture = j["capture"] - origin
        key = "still" if int(capture) in still_set else "other"
        value = j["answers"]["path"]["value"]
        path[key][value] = path[key].get(value, 0) + 1
        blocked_p[key].append(j["probabilities"]["path"].get("B", 0.0))
    for key, answers in path.items():
        p = sorted(blocked_p[key])
        print(
            f"judge on {key} seconds: {answers}, P(blocked) median {p[len(p) // 2]:.4f} max {p[-1]:.4f}"
        )
    # The blue blips the reader saw.
    blue = [r for r in rows if any(b[0] == "blue" for b in r["blips"])]
    print(f"ticks with a blue blip: {len(blue)} of {len(rows)}")
    places = {}
    for r in blue:
        for b in r["blips"]:
            if b[0] == "blue":
                places.setdefault((b[1] // 10 * 10, b[2] // 10 * 10, b[3]), 0)
                places[(b[1] // 10 * 10, b[2] // 10 * 10, b[3])] += 1
    for place, count in sorted(places.items(), key=lambda kv: -kv[1])[:8]:
        print("  blue at x,y (10 px bins), border:", place, count)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
