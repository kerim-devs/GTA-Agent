"""Offline P50 evidence. Run from the root; no console, models or network.

Recorded pictures cannot respond to changed commands. Request decisions and the
first guard intervention are counterfactual checks, never a completed live trip.
"""

import bisect
import json
import subprocess
import sys
import time
import types
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot/src"))
from pilot.contract import Answer, Judgment, Observation
from pilot.foot import (
    FootGuard,
    WalkRoad,
    find_road,
    hud_crop,
    north_bearing,
    world_shift,
    world_view,
)
from pilot.head import HeadRequest
from pilot.judge import ModeFilter
from pilot.loop import Pipeline
from pilot.minimap import read
from pilot.mission import MissionHead

OUT = ROOT / "lab/foot/p50"
BASE = "9fe3076373d18a4927517b91d359bb043e71d40c"
SESSIONS = ("20261112-100318", "20261112-100713", "20261112-082524", "20261111-204712")


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def baseline(name):
    module = types.ModuleType("pilot.p50_before_" + name)
    module.__package__ = "pilot"
    sys.modules[module.__name__] = module
    source = subprocess.check_output(
        ["git", "show", f"{BASE}:pilot/src/pilot/{name}.py"], cwd=ROOT, text=True
    )
    exec(compile(source, f"baseline/{name}.py", "exec"), module.__dict__)  # noqa: S102
    return module


class NoGPS:
    def poll(self, crop, timestamp):
        return None


def decide(head, request):
    answer = head.decide(HeadRequest(**deepcopy(request)))
    return {"rule": head.last_rule, "plan": asdict(answer)["plan"]}


def comparisons(old):
    cases = []
    for name in ("saved_cases", "frame_cases", "extra_cases"):
        for row in json.loads((ROOT / f"lab/mission/{name}.json").read_text()):
            cases.append(("mission", row["id"], row["request"]))
    for row in json.loads((ROOT / "lab/take-out/cases.json").read_text()):
        cases.append(
            ("take-out", f"{row['recording']}-{row['sample_t']:.3f}", row["request"])
        )
    changes = []
    for suite, key, request in cases:
        before, after = decide(old(), request), decide(MissionHead(), request)
        if before != after:
            changes.append(
                {"suite": suite, "id": key, "before": before, "after": after}
            )
    sessions = []
    for row in json.loads((ROOT / "lab/foot/p45-decisions.json").read_text())[
        "sessions"
    ]:
        old_head, new_head = old(), MissionHead()
        requests = []
        for item in row["requests"]:
            before, after = (
                decide(old_head, item["request"]),
                decide(new_head, item["request"]),
            )
            requests.append(
                {
                    "id": item["id"],
                    "t": item["t"],
                    "request": item["request"],
                    "before": before,
                    "after": after,
                }
            )
        sessions.append({"recording": row["recording"], "requests": requests})
    return {
        "counts": dict(Counter(case[0] for case in cases)),
        "changes": changes,
        "p45": sessions,
    }


def replay(name, old_foot, old_mission):
    recording = Path("/Users/kerim/recordings/pilot") / name
    play = records(recording / "play.jsonl")
    frames = records(recording / "frames.jsonl")
    heads = records(recording / "head.jsonl")
    origin = heads[0]["t"] - play[0]["t"]
    requests = [row for row in heads if row.get("type") == "request"]
    ticks = {
        row["frame_id"]: row for row in play if row.get("fresh") and row.get("reading")
    }
    # Requests carry a snapshot. Select its nearest preceding captured frame.
    times = [row["t"] for row in play]
    frame_ids = {row["frame_id"] for row in frames}
    request_frames = {}
    for row in requests:
        t = row["t"] - origin
        index = min(
            range(
                max(0, bisect.bisect_left(times, t) - 1),
                min(len(play), bisect.bisect_left(times, t) + 2),
            ),
            key=lambda i: abs(times[i] - t),
        )
        frame_id = play[index]["frame_id"]
        assert frame_id in frame_ids and abs(times[index] - t) < 0.01
        request_frames.setdefault(frame_id, []).append(row)
    judgments = iter(
        row for row in records(recording / "judge.jsonl") if row.get("answers")
    )
    upcoming = next(judgments, None)
    judgment = None
    modes = ModeFilter()
    pipeline = Pipeline(gps_reader=NoGPS())
    old_head, new_head = old_mission(), MissionHead()
    capture = cv2.VideoCapture(str(recording / "video.mp4"))
    previous = None
    guard = old_guard = skill = None
    skill_start = 0.0
    skill_request = None
    counts = Counter()
    intervals = {}
    decisions, head_results, roads, headings, pair_metrics = [], [], [], [], []
    timings = []
    cpu_timings = []
    last_world = None
    samples = {
        "20261112-100318": [6, 7, 18, 59],
        "20261112-100713": [6, 30, 41, 102, 112, 246, 256, 283],
        "20261112-082524": [120, 130, 150],
        "20261111-204712": [40, 90],
    }.get(name, [])
    saved = set()
    for item in frames:
        ok, bgr = capture.read()
        if not ok:
            break
        row = ticks.get(item["frame_id"])
        asks = request_frames.get(item["frame_id"], [])
        if row is None and not asks:
            continue
        t = row["t"] if row else item["t"]
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        crop = hud_crop(rgb)
        reading, moving, _ = pipeline.step(crop, t, feedback=False)
        for ask in asks:
            request = deepcopy(ask["request"])
            real_request = deepcopy(request)
            real_request["minimap"].update(asdict(reading))
            before = decide(old_head, request)
            after = decide(new_head, real_request)
            entry = {
                "id": ask["id"],
                "t": round(ask["t"] - origin, 3),
                "frame_id": item["frame_id"],
                "frame_t": t,
                "before": before,
                "after": after,
                "recorded_blips": request["minimap"].get("blips"),
                "blips": asdict(reading)["blips"],
                "north": north_bearing(crop),
                "request": real_request,
            }
            head_results.append(entry)
            skill = None
            skill_request = ask["id"]
            skill_start = t
            for call in after["plan"]:
                if call["name"] == "walk_road":
                    skill = WalkRoad(call["args"])
                    break
                skill_start += call["args"].get("duration", 0)
            if name in SESSIONS[:2] and (
                request["minimap"].get("blips") or asks[0] == requests[0]
            ):
                stem = f"{name}-request-{ask['id']}"
                cv2.imwrite(
                    str(OUT / (stem + ".jpg")), bgr, [cv2.IMWRITE_JPEG_QUALITY, 78]
                )
                cv2.imwrite(
                    str(OUT / (stem + "-map.png")),
                    cv2.cvtColor(crop, cv2.COLOR_RGB2BGR),
                )
        if row is None:
            continue
        for sample in samples:
            if sample not in saved and t >= sample:
                stem = f"{name}-{sample}"
                cv2.imwrite(
                    str(OUT / (stem + ".jpg")), bgr, [cv2.IMWRITE_JPEG_QUALITY, 78]
                )
                cv2.imwrite(
                    str(OUT / (stem + "-map.png")),
                    cv2.cvtColor(crop, cv2.COLOR_RGB2BGR),
                )
                saved.add(sample)
        fresh = None
        while upcoming is not None and upcoming["t"] - origin <= t:
            fresh = Judgment(
                upcoming["capture"] - origin,
                {key: Answer(**value) for key, value in upcoming["answers"].items()},
                upcoming["probabilities"],
                upcoming["duration"],
                upcoming["server"],
            )
            upcoming = next(judgments, None)
        mode = modes.update(fresh, t)
        judgment = fresh or judgment
        observation = Observation(
            reading, moving, t, frame=rgb, judgment=judgment, mode=mode
        )
        event = row.get("skill") or {}
        key = (event.get("name"), event.get("status"))
        walking = key[0] in ("walk", "walk_road", "walk_to") and key[1] == "running"
        if walking and previous != key:
            guard, old_guard = FootGuard(), old_foot.FootGuard()
            counts["runs"] += 1
        if not walking:
            guard = old_guard = None
        previous = key
        road = find_road(crop)
        if name in SESSIONS[:2] and (t <= 20 or road is not None):
            roads.append(
                {
                    "t": round(t, 3),
                    "road": asdict(road) if road else None,
                    "north": north_bearing(crop),
                }
            )
        if skill is not None and t >= skill_start and walking and name in SESSIONS[:2]:
            result = skill.step(observation)
            headings.append(
                {
                    "t": round(t, 3),
                    "request": skill_request,
                    "road": road is not None,
                    "north": north_bearing(crop),
                    "compass": skill.compass_heading,
                    "heading": skill.heading,
                    "state": result.status,
                    "reason": result.reason,
                }
            )
        if guard is None:
            continue
        pad = row.get("sent_pad") or (row.get("result") or {}).get("pad") or {}
        want = tuple(pad.get("left") or (0, 0))
        before_events = len(guard.events)
        start = time.perf_counter()
        cpu_start = time.process_time()
        steer = guard.step(observation, want)
        timings.append((time.perf_counter() - start) * 1000)
        cpu_timings.append((time.process_time() - cpu_start) * 1000)
        old_guard.step(observation, want)
        old_kind = old_guard.evidence[-1][1] if old_guard.evidence else None
        kind = guard.evidence[-1][1] if guard.evidence else None
        counts["walking_ticks"] += 1
        counts["before_" + (old_kind or "unknown")] += 1
        counts["after_" + (kind or "unknown")] += 1
        diagnostic = event.get("reason") or ""
        if "motion=unknown" in diagnostic:
            counts["recorded_unknown"] += 1
        bucket = int(t // 10) * 10
        bucket_count = intervals.setdefault(bucket, Counter())
        bucket_count["before_" + (old_kind or "unknown")] += 1
        bucket_count["after_" + (kind or "unknown")] += 1
        for when, state in guard.events[before_events:]:
            decisions.append(
                {
                    "t": round(when, 3),
                    "run": counts["runs"],
                    "state": state,
                    "sent": pad,
                    "left": steer.left,
                }
            )
        view = world_view(rgb)
        if last_world is None:
            last_world = (t, view)
        elif t - last_world[0] >= 0.45:
            if t - last_world[0] <= 0.65:
                pair_metrics.append(
                    {"t": round(t, 3), "shift": world_shift(last_world[1], view)}
                )
            last_world = (t, view)
    capture.release()
    import numpy as np

    summary = {
        "recording": name,
        "counts": dict(counts),
        "intervals": intervals,
        "guard_ms": {
            "median": float(np.median(timings)),
            "p95": float(np.percentile(timings, 95)),
            "cpu_median": float(np.median(cpu_timings)),
            "cpu_p95": float(np.percentile(cpu_timings, 95)),
        },
        "requests": head_results,
        "decisions": decisions,
        "roads": roads,
        "headings": headings,
        "world_pairs": pair_metrics,
    }
    (OUT / (name + ".json")).write_text(
        json.dumps(summary, separators=(",", ":")) + "\n"
    )
    print(
        name,
        dict(counts),
        summary["guard_ms"],
        "requests",
        len(head_results),
        flush=True,
    )
    return summary


def main():
    OUT.mkdir(exist_ok=True)
    old_foot, old_mission = baseline("foot"), baseline("mission").MissionHead
    result = comparisons(old_mission)
    old_reader = baseline("minimap")
    import numpy as np

    with np.load(ROOT / "lab/blips/crops.npz") as data:
        reader_changes = [
            str(key)
            for key, crop in zip(data["ids"], data["crops"])
            if asdict(old_reader.read(crop)) != asdict(read(crop))
        ]
    result["reader_corpus"] = {"count": 80, "changed": reader_changes}
    fixture_changes = []
    for path in sorted((ROOT / "pilot/tests/fixtures").glob("*.png")):
        crop = cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)
        if crop.shape != (170, 260, 3):
            continue
        before, after = asdict(old_reader.read(crop)), asdict(read(crop))
        if before != after:
            fixture_changes.append(
                {"file": path.name, "before": before, "after": after}
            )
    result["fixture_changes"] = fixture_changes
    result["baseline"] = BASE
    (OUT / "decisions.json").write_text(json.dumps(result, indent=2) + "\n")
    for name in sys.argv[1:] or SESSIONS:
        replay(name, old_foot, old_mission)


if __name__ == "__main__":
    main()
