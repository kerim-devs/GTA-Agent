"""Run the on-foot guard over a recorded pilot session and say when it would have called the figure
stuck, and what it would have sent then next to what was sent.

    pilot/.venv/bin/python lab/foot/replay.py RECORDING OUT.json

The recorded pixels cannot answer new commands. So each recorded walking skill (`walk`, `walk_to`) gets
a fresh guard, as it would live, which is told the stick that skill sent and watches the real frames,
the readings as recorded, the pipeline's map motion recomputed from the video and the judge's answers
delivered at the times they arrived. The first decision of each guard is a fair one: up to it, what
was sent is what the guard would have sent. Everything after it rests on frames that never saw the
guard's command, and is listed only to show that it stays bounded.
"""

import json
import sys
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pilot" / "src"))

from pilot.conductor import minimap_crop
from pilot.contract import Answer, Blip, Judgment, Observation, Reading
from pilot.foot import FootGuard
from pilot.judge import ModeFilter
from pilot.loop import Pipeline


class NoGPS:
    def poll(self, crop, timestamp):
        return None


def reading(row):
    data = dict(row)
    data["blips"] = tuple(Blip(**b) for b in data.get("blips", ()))
    data["path"] = tuple(tuple(p) for p in data.get("path", ()))
    return Reading(**data)


def main(recording: Path, out: Path):
    rows = [json.loads(line) for line in (recording / "play.jsonl").open()]
    ticks = {}
    for row in rows:
        if row.get("fresh") and row.get("reading") is not None:
            ticks.setdefault(row["frame_id"], row)
    heads = [json.loads(line) for line in (recording / "head.jsonl").open()]
    origin = heads[0]["t"] - rows[0]["t"]
    judge_path = recording / "judge.jsonl"
    judgments = []
    if judge_path.exists():
        judgments = [json.loads(line) for line in judge_path.open()]
        judgments = [j for j in judgments if j.get("answers")]
    frames = [json.loads(line) for line in (recording / "frames.jsonl").open()]
    capture = cv2.VideoCapture(str(recording / "video.mp4"))
    pipeline = Pipeline(gps_reader=NoGPS())
    modes = ModeFilter()
    pending = iter(judgments)
    upcoming = next(pending, None)
    judgment = None
    guard, run, previous = None, 0, None
    decisions = []
    walking_ticks = 0
    for item in frames:
        ok, bgr = capture.read()
        if not ok:
            break
        row = ticks.get(item["frame_id"])
        if row is None:
            continue
        t = row["t"]
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        _r, moving, _ = pipeline.step(minimap_crop(rgb), t, feedback=False)
        fresh = None
        while upcoming is not None and upcoming["t"] - origin <= t:
            fresh = Judgment(
                upcoming["capture"] - origin,
                {key: Answer(**value) for key, value in upcoming["answers"].items()},
                upcoming["probabilities"],
                upcoming["duration"],
                upcoming["server"],
            )
            upcoming = next(pending, None)
        mode = modes.update(fresh, t)
        judgment = fresh or judgment
        skill = row.get("skill") or {}
        name = skill.get("name")
        key = (name, skill.get("status"))
        # A new instance of a skill begins where the name changes or the last one ended.
        if name in ("walk", "walk_to") and key[1] == "running" and previous != key:
            guard, run = FootGuard(), run + 1
        if name not in ("walk", "walk_to"):
            guard = None
        previous = key
        if guard is None or skill.get("status") != "running":
            continue
        pad = row.get("sent_pad") or (row.get("result") or {}).get("pad") or {}
        sent = tuple(pad.get("left") or (0.0, 0.0))
        observation = Observation(
            reading(row["reading"]), moving, t, frame=rgb, judgment=judgment, mode=mode
        )
        before = len(guard.events)
        steer = guard.step(observation, sent)
        walking_ticks += 1
        for when, state in guard.events[before:]:
            decisions.append(
                {
                    "t": round(when, 2),
                    "run": run,
                    "skill": name,
                    "first": not any(d["run"] == run for d in decisions),
                    "decision": state,
                    "would_send": {
                        "left": [round(v, 2) for v in steer.left],
                        "right": list(steer.right),
                    },
                    "sent": {"left": list(sent), "right": pad.get("right")},
                }
            )
    capture.release()
    first = [d for d in decisions if d["first"]]
    summary = {
        "recording": recording.name,
        "walking_ticks": walking_ticks,
        "walking_runs": run,
        "first_decisions": len(first),
        "first_decision_kinds": {
            k: sum(d["decision"] == k for d in first)
            for k in {d["decision"] for d in first}
        },
        "judgments": len(judgments),
        "blocked_judgments": sum(
            j["answers"]["path"]["value"] == "blocked" for j in judgments
        ),
        "decisions": decisions,
    }
    out.write_text(json.dumps(summary, indent=1) + "\n")
    for d in first:
        print(
            f"{d['t']:7.2f}s run {d['run']:2d} {d['skill']:8s} {d['decision']:7s} would send {d['would_send']}, sent {d['sent']['left']}"
        )
    print({k: v for k, v in summary.items() if k != "decisions"})


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
