"""Tick replay with real minimap/motion/mode readers; never sends console input."""

import json
import sys
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
    video = cv2.VideoCapture(str(folder / "video.mp4"))
    counts = Counter()
    rows = []
    first_change = endpoint = None
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
            if t < start or endpoint is not None:
                continue
            observation = Observation(
                reading, moving, t, frame=rgb, judgment=judgment, mode=accepted
            )
            result = skill.step(observation)
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
            }
            rows.append(item)
            old = tuple((row.get("sent_pad") or {}).get("left") or (0, 0))
            if (
                first_change is None
                and sum(abs(a - b) for a, b in zip(old, result.pad.left)) > 0.1
            ):
                first_change = item
            if result.status != "running":
                endpoint = item
    video.release()
    incomplete = endpoint is None
    if incomplete:
        endpoint = rows[-1] if rows else None
    out = ROOT / "lab/foot/p57"
    out.mkdir(exist_ok=True)
    (out / (folder.name + ".json")).write_text(
        json.dumps(rows, separators=(",", ":")) + "\n"
    )
    return {
        "session": folder.name,
        "counterfactual_replacement": alternate,
        "ticks": len(rows),
        "recording_ended_before_deadline": incomplete,
        "positions": dict(counts),
        "first_changed_command": first_change,
        "endpoint": endpoint,
    }


if __name__ == "__main__":
    result = {
        "scope": "Recorded pictures do not respond to changed commands; endpoints describe observed replay frames, not simulated arrival.",
        "runs": [replay(name) for name in SESSIONS],
    }
    print(json.dumps(result, indent=2))
