"""Tick replay with real minimap/motion/mode readers; never sends console input.

Two walks are fed the same recorded ticks side by side, each with its own guard: the walk as it was before
P57 (foot.py of BASE, loaded from git) and the walk as it is now. Recorded pictures do not respond to
either walk's commands, so this compares what the two decide on the same pictures, not where they arrive.
"""

import json
import subprocess
import sys
import types
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot/src"))
from pilot.contract import Answer, Judgment, Observation
from pilot.foot import WalkRoad, find_road, hud_crop
from pilot.judge import ModeFilter
from pilot.loop import Pipeline

SESSIONS = ("122242", "110418", "110736", "111053", "122558")
BASE = "f9922f1"  # the last commit before the P57 work
NEUTRAL = (0.0, 0.0)


def old_walk_class():
    source = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{BASE}:pilot/src/pilot/foot.py"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.replace("from .", "from pilot.")
    module = types.ModuleType("foot_before_p57")
    sys.modules["foot_before_p57"] = module  # dataclasses look the module up by name
    exec(compile(source, "foot_before_p57", "exec"), module.__dict__)
    return module.WalkRoad


def longest_run(rows, test):
    """Seconds of the longest run of consecutive ticks for which test(row) holds."""
    best = start = last = None
    for row in rows:
        if test(row):
            start = row["t"] if start is None else start
            last = row["t"]
            best = max(best or 0.0, last - start)
        else:
            start = None
    return round(best or 0.0, 3)


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


class NoGPS:
    def poll(self, crop, timestamp):
        return None


def replay(suffix):
    folder = Path("/Users/kerim/recordings/pilot") / ("20261112-" + suffix)
    play, frames, heads = [
        records(folder / name) for name in ("play.jsonl", "frames.jsonl", "head.jsonl")
    ]
    origin = heads[0]["t"] - play[0]["t"]
    judges = iter(r for r in records(folder / "judge.jsonl") if r.get("answers"))
    upcoming = next(judges, None)
    judgment = None
    mode = ModeFilter()
    pipeline = Pipeline(gps_reader=NoGPS())
    ticks = {}
    for row in play:
        if row.get("reading"):
            ticks.setdefault(row["frame_id"], []).append(row)
    walks = [r for r in play if (r.get("skill") or {}).get("name") == "walk_road"]
    # 122558 never ran the requested walk: it levelled then waited while
    # the reader said seated. Replay the requested skill from that wait tick.
    alternate = not walks
    if alternate:
        walks = [
            r
            for r in play
            if (r.get("skill") or {}).get("name") == "wait" and r["t"] >= 6
        ]
    if not walks:
        raise ValueError(f"{suffix}: no foot interval")
    start = walks[0]["t"]
    skill = WalkRoad({"duration": 20})
    before = old_walk_class()({"duration": 20})
    video = cv2.VideoCapture(str(folder / "video.mp4"))
    counts = Counter()
    rows = []
    ended = {}
    for meta in frames:
        ok, bgr = video.read()
        if not ok:
            break
        for row in ticks.get(meta["frame_id"], []):
            t = row["t"]
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            crop = hud_crop(rgb)
            reading, moving, _ = pipeline.step(crop, t, feedback=False)
            fresh = None
            while upcoming is not None and upcoming["t"] - origin <= t:
                fresh = Judgment(
                    upcoming["capture"] - origin,
                    {k: Answer(**v) for k, v in upcoming["answers"].items()},
                    upcoming["probabilities"],
                    upcoming["duration"],
                    upcoming["server"],
                )
                upcoming = next(judges, None)
            accepted = mode.update(fresh, t)
            judgment = fresh or judgment
            if t < start or len(ended) == 2:
                continue
            observation = Observation(
                reading, moving, t, frame=rgb, judgment=judgment, mode=accepted
            )
            result = skill.step(observation)
            old = before.step(observation)
            road = find_road(crop)
            position = (
                road.position if road is not None and not reading.corrupt else "unknown"
            )
            counts[position] += 1
            item = {
                "t": round(t, 3),
                "frame_id": meta["frame_id"],
                "position": position,
                "road": asdict(road) if road else None,
                "status": result.status,
                "reason": result.reason,
                "left": result.pad.left,
                "before_status": old.status,
                "before_reason": old.reason,
                "before_left": old.pad.left,
            }
            rows.append(item)
            if result.status != "running":
                ended.setdefault("new", item)
            if old.status != "running":
                ended.setdefault("before", item)
    video.release()
    out = ROOT / "lab/foot/p57"
    out.mkdir(exist_ok=True)
    (out / (folder.name + ".json")).write_text(
        json.dumps(rows, separators=(",", ":")) + "\n"
    )

    def moves(left):
        return tuple(left) != NEUTRAL

    old_moved = [r for r in rows if moves(r["before_left"])]
    kept = [r for r in old_moved if moves(r["left"])]
    lane = [r for r in old_moved if r["position"] == "lane"]
    moved_or_lane = [r for r in old_moved if moves(r["left"]) or r["position"] == "lane"]
    return {
        "session": folder.name,
        "counterfactual_replacement": alternate,
        "ticks": len(rows),
        "recording_ended_before_deadline": len(ended) < 2,
        "positions": dict(counts),
        "moving_ticks_before": len(old_moved),
        "moving_ticks_now": sum(moves(r["left"]) for r in rows),
        "old_moving_ticks_where_now_moves": len(kept),
        "old_moving_ticks_lane": len(lane),
        "share_of_old_moving_ticks_kept_outside_lane": round(
            (len(moved_or_lane) - len(lane)) / max(1, len(old_moved) - len(lane)), 3
        ),
        "ticks_where_the_pad_differs_from_before": sum(
            tuple(r["left"]) != tuple(r["before_left"]) for r in rows
        ),
        "of_which_on_a_lane_reading": sum(
            tuple(r["left"]) != tuple(r["before_left"]) and r["position"] == "lane" for r in rows
        ),
        "longest_neutral_hold_now_s": longest_run(rows, lambda r: not moves(r["left"])),
        "longest_hold_now_where_before_moved_s": longest_run(
            rows, lambda r: not moves(r["left"]) and moves(r["before_left"])
        ),
        "longest_neutral_hold_before_s": longest_run(
            rows, lambda r: not moves(r["before_left"])
        ),
        "ending_before": ended.get("before") and {
            k: ended["before"][k] for k in ("t", "status", "reason", "before_status", "before_reason")
        },
        "ending_now": ended.get("new") and {
            k: ended["new"][k] for k in ("t", "status", "reason")
        },
    }


if __name__ == "__main__":
    result = {
        "scope": (
            "Recorded pictures do not respond to either walk's commands. 'before' is foot.py at "
            + BASE
            + "; 'now' is the walk in this tree. Both run with their own real guard on the same ticks."
        ),
        "runs": [replay(name) for name in SESSIONS],
    }
    print(json.dumps(result, indent=2))
