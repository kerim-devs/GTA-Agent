"""Walks on foot to places from the map's legend, one try after another, and what each try was like.

    pilot/.venv/bin/python lab/live/walks.py <list.jsonl> [--walk JSON] [--seconds N] [--flag FILE] PLACE ...

Each try is two sessions with a fixed plan and no head that could change its mind: the waypoint
is set on the place by its name in the legend, and where that is no further than `--furthest`
metres, `walk_to_point` goes there. A place given as `-` walks to the waypoint that is already
set. The try waits while a person plays or a recording runs, ends at once when a controller
reports input, and ends two seconds after the walk has. One line per try is appended to the list
and printed: how long the walk took, every stretch with the stick let go between its first push
and its end, the foot guard's states, how often the stick swung, and what it ended on. `--flag`
names a file that exists while a try runs, for jobs on this machine that should wait.
"""

import argparse
import itertools
import json
import math
import os
import re
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
API = "http://127.0.0.1:9395"
JUDGE = "http://192.168.0.248:1234=qwen/qwen3-vl-8b"
OUT = Path("/Users/kerim/recordings/pilot")
NEAR = 40  # metres within which the game takes a waypoint off the map as soon as it is set
# What the head answers to whatever the game shows on the way, a help text for one: go on. Without
# it the next plan replaced the walk, as it did 30 map pixels from the hangar on 13 November.
GO_ON = [word for _ in range(40) for word in ("--plan", "go_on")]


def status():
    try:
        with urllib.request.urlopen(f"{API}/status", timeout=2) as answer:
            return json.load(answer)
    except Exception:  # whatever the bridge does, the loop goes on watching its session
        return {}


def rows_of(folder):
    rows = []
    try:
        for line in (folder / "play.jsonl").open():
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass  # the line being written
    except OSError:
        pass
    return rows


def last_of(rows, name):
    """(time, status, reason) of the skill's end, or None while it has none."""
    for row in rows:
        skill = row.get("skill") or {}
        if skill.get("name") == name and skill.get("status") in ("done", "failed"):
            return row["t"], skill["status"], str(skill.get("reason") or "")
    return None


def left_of(row):
    """The left stick the console was sent on this tick, or what the skill asked for where none was."""
    return (row.get("sent_pad") or row["result"]["pad"])["left"]


def judge(folder, place):
    """One try as a row of numbers, from its play log."""
    rows = rows_of(folder)
    row = {"session": folder.name, "place": place}
    waypoint = last_of(rows, "set_waypoint")
    if waypoint:
        row["waypoint"] = {
            "status": waypoint[1],
            "seconds": round(waypoint[0], 1),
            "reason": waypoint[2][:160],
        }
        metres = re.search(r"\((\d+) ?m\)", waypoint[2])
        if metres:
            row["metres"] = int(metres[1])
    walk = [
        r
        for r in rows
        if (r.get("skill") or {}).get("name") == "walk_to_point"
        and r.get("result")
        and r.get("t") is not None
    ]
    if not walk:
        return row
    end = last_of(rows, "walk_to_point")
    pushes = [r for r in walk if abs(left_of(r)[0]) + abs(left_of(r)[1]) > 0.05]
    row["walk"] = {
        "status": end[1] if end else "cut",
        "reason": (end[2] if end else "")[:200],
        "seconds": round(walk[-1]["t"] - walk[0]["t"], 1),
        "to_first_push": round(pushes[0]["t"] - walk[0]["t"], 2) if pushes else None,
    }
    if not pushes:
        return row
    # Every stretch with the left stick let go between the first push and the last.
    stops, since = [], None
    for r in walk:
        if not pushes[0]["t"] <= r["t"] <= pushes[-1]["t"]:
            continue
        left = left_of(r)
        if abs(left[0]) + abs(left[1]) <= 0.05:
            since = r["t"] if since is None else since
        elif since is not None:
            if r["t"] - since >= 0.1:
                stops.append((round(since - walk[0]["t"], 1), round(r["t"] - since, 2)))
            since = None
    # A swing is a change of the stick's direction by more than 60 degrees within a third of a second.
    swings, before = [], None
    for r in pushes:
        left = left_of(r)
        bearing = math.degrees(math.atan2(left[0], -left[1]))
        if (
            before is not None
            and r["t"] - before[0] <= 0.34
            and abs((bearing - before[1] + 180) % 360 - 180) > 60
        ):
            swings.append(round(r["t"] - walk[0]["t"], 1))
        before = (r["t"], bearing)
    # The guard's states in seconds, and how long it saw the figure stand while the stick was out.
    states, standing = {}, 0.0
    for r, following in itertools.pairwise(walk):
        reason = (r.get("skill") or {}).get("reason") or ""
        state = re.search(r"state=(\w+)", reason)
        if state:
            states[state[1]] = states.get(state[1], 0.0) + following["t"] - r["t"]
        if "motion=still" in reason and r in pushes:
            standing += following["t"] - r["t"]
    # The sprint: every press of X, and the time from one press to the next.
    presses, down = [], False
    for r in walk:
        now = "cross" in (r.get("sent_pad") or r["result"]["pad"])["buttons"]
        if now and not down:
            presses.append(r["t"])
        down = now
    periods = sorted(b - a for a, b in itertools.pairwise(presses) if b - a < 1.0)
    # Every stretch the walk jogged because the figure had run itself out.
    rests, since = [], None
    for r in walk:
        winded = "out of breath" in (r["result"].get("reason") or "")
        if winded and since is None:
            since = r["t"]
        elif not winded and since is not None and r["result"].get("reason"):
            rests.append((round(since - walk[0]["t"], 1), round(r["t"] - since, 1)))
            since = None
    if since is not None:
        rests.append((round(since - walk[0]["t"], 1), round(walk[-1]["t"] - since, 1)))
    reasons = [r["result"].get("reason") or "" for r in walk]
    road = [re.search(r"on a road (\d+) of (\d+) s", reason) for reason in reasons]
    road = [found for found in road if found]
    row["walk"].update(
        stops=stops,
        stopped_seconds=round(sum(length for _, length in stops), 2),
        swings=swings,
        guard={state: round(seconds, 1) for state, seconds in states.items() if state != "go"},
        standing=round(standing, 1),
        presses=len(presses),
        press_period=round(periods[len(periods) // 2], 3) if periods else None,
        rests=rests,
        on_road=[int(road[-1][1]), int(road[-1][2])] if road else None,
        woke=round(sum(1 for reason in reasons if reason.startswith("touching the camera")) / 30, 2),
    )
    return row


def line_of(row):
    walk = row.get("walk")
    waypoint = row.get("waypoint", {})
    head = f"{row['session']} {row['place']}"
    if "metres" in row:
        head += f" {row['metres']} m"
    if not walk:
        why = row.get("skipped") or f"waypoint {waypoint.get('status')} {waypoint.get('reason', '')[:90]}"
        return f"{head}: no walk; {why}"
    text = f"{head}: {walk['status']} after {walk['seconds']} s"
    if "metres" in row and walk["seconds"]:
        text += f" ({row['metres'] / walk['seconds']:.1f} m/s)"
    if walk.get("to_first_push") is not None:
        text += f", first push after {walk['to_first_push']} s"
    if "stops" in walk:
        text += f", {len(walk['stops'])} stops ({walk['stopped_seconds']} s) {walk['stops'][:6]}"
        text += f", standing {walk['standing']} s, swings {walk['swings'][:8]}, guard {walk['guard']}"
        text += f", road {walk['on_road']}, X {walk['presses']} times every {walk['press_period']} s"
        text += f", out of breath {walk['rests']}"
    return text + f" | {walk['reason'][:110]}"


def session(plan, seconds, flag, over):
    """One session with a fixed plan; ends two seconds after `over` says so of its log, or at once
    when a hand is on the controller. Returns its folder and whether it was cut short."""
    while True:
        state = status()
        if state.get("session_up") and not state.get("human_input") and not state.get("recording"):
            break
        time.sleep(5)
    before = sorted(OUT.glob("2026*"))
    command = [
        ".venv/bin/python", "-m", "pilot.cli", "play", "--no-level", "--no-view", "--head", "scripted",
        "--plan", json.dumps(plan), *GO_ON,
        "--quiet-seconds", "400", "--seconds", str(seconds), "--judge", JUDGE, "--record-dir", str(OUT),
    ]  # fmt: skip
    env = {key: value for key, value in os.environ.items() if key != "PS5_HOST"}
    if flag:
        flag.touch()
    cut, process = False, None
    try:
        process = subprocess.Popen(
            command, cwd=REPO / "pilot", env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        ended = None
        while process.poll() is None:
            time.sleep(1)
            if status().get("human_input"):
                cut = True
                break
            new = [folder for folder in sorted(OUT.glob("2026*")) if folder not in before]
            if new and ended is None and over(rows_of(new[-1])):
                ended = time.monotonic()
            if ended is not None and time.monotonic() - ended >= 2:
                break
    finally:
        # However this loop is left, by its own end, an error or a signal to the loop itself, the
        # session is asked to stop, asked again if it does not, and never left behind.
        if process is not None:
            for ask in (signal.SIGINT, signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
                if process.poll() is not None:
                    break
                process.send_signal(ask)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    pass
        if flag:
            flag.unlink(missing_ok=True)
    new = [folder for folder in sorted(OUT.glob("2026*")) if folder not in before]
    return (new[-1] if new else None), cut


def one(place, walk_args, seconds, flag, furthest):
    """The waypoint in a session of its own, so that a place too far away is not walked to."""
    row = {"place": place}
    if place != "-":
        plan = [{"name": "set_waypoint", "args": {"place": place}}]
        folder, cut = session(plan, 60, flag, lambda rows: last_of(rows, "set_waypoint"))
        if folder is None:
            return {"place": place, "error": "no session was written"}
        row = judge(folder, place)
        if cut:
            row["cut"] = "a hand on the controller"
        if cut or row.get("waypoint", {}).get("status") != "done":
            return row
        if "metres" not in row:
            row["skipped"] = "the distance was not read"
            return row
        if row.get("metres", 0) > furthest:
            row["skipped"] = f"further than {furthest} m"
            return row
        if row.get("metres", furthest) < NEAR:
            row["skipped"] = "the figure is there already"
            return row
    plan = [{"name": "walk_to_point", "args": walk_args}]
    folder, cut = session(plan, seconds, flag, lambda rows: last_of(rows, "walk_to_point"))
    if folder is None:
        return {**row, "error": "no session was written"}
    row = {**row, **{key: value for key, value in judge(folder, place).items() if key != "waypoint"}}
    if cut:
        row["cut"] = "a hand on the controller"
    return row


def main():
    # A loop that is told to end ends its session first.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("list", type=Path)
    parser.add_argument("places", nargs="+")
    parser.add_argument("--walk", default="{}", help="arguments of walk_to_point as JSON")
    parser.add_argument("--seconds", type=int, default=200)
    parser.add_argument("--flag", type=Path)
    parser.add_argument(
        "--furthest", type=int, default=700, help="metres beyond which a place is not walked to"
    )
    parser.add_argument(
        "--judge-only", action="store_true", help="the places are session folders to judge again"
    )
    args = parser.parse_args()
    if args.judge_only:
        for folder in args.places:
            print(line_of(judge(Path(folder), "-")))
        return 0
    walk_args = json.loads(args.walk)
    for place in args.places:
        row = one(place, walk_args, args.seconds, args.flag, args.furthest)
        row["walk_args"] = walk_args
        row["at"] = time.strftime("%H:%M:%S")
        with args.list.open("a") as out:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(time.strftime("%H:%M:%S"), row.get("error") or line_of(row), flush=True)
        if row.get("cut"):
            print("cut short by a hand on the controller; the list of places ends here", flush=True)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
