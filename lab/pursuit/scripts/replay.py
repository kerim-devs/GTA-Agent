"""P78 human inventory and sequential frame replay. Run with pilot/.venv/bin/python.

No live inputs. Results are recorded replay measurements, never closed-loop driving.
"""

import argparse
import bisect
import gzip
import itertools
import json
import math
import sys
from collections import deque
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "pilot/src"))

from pilot import hud as hud_reader  # noqa: E402
from pilot import minimap  # noqa: E402
from pilot.contract import Observation  # noqa: E402
from pilot.motion import map_motion, motion_state  # noqa: E402
from pilot.pursuit import DriveToBlip  # noqa: E402
from pilot.replay import hud_crop  # noqa: E402

OUT = ROOT / "lab/pursuit"
DERIVED = Path("/Users/kerim/recordings/derived/kerim")
RAW = Path("/Users/kerim/recordings/kerim")


def jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def integral(pad, times, start, end, key="left"):
    result = 0.0
    index = max(0, bisect.bisect_right(times, start) - 1)
    while index < len(pad) and times[index] < end:
        value = pad[index].get(key, [0, 0] if key == "left" else 0)
        if key == "left":
            value = value[0]
        stop = times[index + 1] if index + 1 < len(pad) else end
        result += value * max(0, min(stop, end) - max(times[index], start))
        index += 1
    return result


def inventory():
    rows = []
    for file in sorted(DERIVED.glob("*/missions.json")):
        data = json.loads(file.read_text())
        actions = jsonl(file.with_name("actions.jsonl")) if file.with_name("actions.jsonl").exists() else []
        for mission in data.get("missions", []):
            for step in mission.get("steps", []):
                driving = step.get("human", {}).get("seconds", {}).get("driving", 0)
                sample = step.get("sample_observation") or {}
                markers = [b for b in sample.get("blips", []) if b.get("color") in ("blue", "red", "yellow")]
                if not driving or step.get("route") or not markers:
                    continue
                objective = step["objective"]
                color = markers[0]["color"]
                mode = (
                    "follow" if "folge" in objective.lower() else "catch" if "Biker" in objective else "reach"
                )
                rows.append(
                    {
                        "rec": file.parent.name,
                        "start": step["start"],
                        "end": step["end"],
                        "objective": objective,
                        "driving_s": driving,
                        "markers": markers,
                        "ending": step.get("ending", "unknown"),
                        "incidents": step.get("incidents", []),
                        "color": color,
                        "mode": mode,
                        "source": str(file),
                        "actions": [
                            a for a in actions if a["end"] > step["start"] and a["start"] < step["end"]
                        ],
                    }
                )
    # The task explicitly asks for this old motorbike run; no objective was labelled in this window.
    rows.append(
        {
            "rec": "20261110-093238",
            "start": 150.0,
            "end": 210.0,
            "objective": "Unlabelled motorbike chase (task reference)",
            "driving_s": None,
            "markers": [],
            "ending": "unlabelled",
            "incidents": [],
            "color": "blue",
            "mode": "catch",
            "source": "lab/notes/out/20261110-093238/missions.json",
            "actions": [],
        }
    )
    return rows


def replay_recording(rec, stretches):
    raw = (
        RAW / rec if rec != "20261110-093238" else Path("/Users/kerim/Documents/ChatGPT/gta/recordings") / rec
    )
    frames = jsonl(raw / "frames.jsonl")
    assert all(row["i"] == i for i, row in enumerate(frames))
    assert all(a["t"] < b["t"] for a, b in itertools.pairwise(frames))
    pads = jsonl(raw / "pad.jsonl")
    pt = [r["t"] for r in pads]
    hud_file = DERIVED / rec / "hud.jsonl"
    hud_rows = {r["i"]: r for r in jsonl(hud_file)} if hud_file.exists() else {}
    judge_file = DERIVED / rec / "judge.json"
    judge = json.loads(judge_file.read_text()).get("frames", {}) if judge_file.exists() else {}
    judge_indices = sorted(int(i) for i in judge)
    capture = cv2.VideoCapture(str(raw / "video.mp4"))
    active = []
    for stretch in stretches:
        duration = stretch["end"] - stretch["start"]
        skill = DriveToBlip({"color": stretch["color"], "mode": stretch["mode"], "duration": duration + 1})
        active.append({"stretch": stretch, "skill": skill, "rows": [], "end_reason": None})
    last = max(s["end"] for s in stretches)
    history = deque()
    # Sequential grab preserves frames.jsonl indices even for codecs with imprecise seeking.
    for meta in frames:
        t = meta["t"]
        if t > last:
            break
        if not capture.grab():
            raise RuntimeError(f"short video: {rec}:{meta['i']}")
        selected = [a for a in active if a["stretch"]["start"] <= t <= a["stretch"]["end"]]
        if not selected:
            continue
        ok, bgr = capture.retrieve()
        if not ok:
            raise RuntimeError(f"failed decode: {rec}:{meta['i']}")
        crop = hud_crop(bgr)
        reading = minimap.read(crop)
        full = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        logged = hud_rows.get(meta["i"], {})
        motion = logged.get("move")
        while history and history[0][0] < t - 1.2:
            history.popleft()
        moving = None
        if history and t - history[0][0] >= 0.15:
            _, previous = min(history, key=lambda item: abs(t - item[0] - 0.2))
            moving = motion_state(map_motion(previous, crop))
            if moving is not True and t - history[0][0] >= 0.8:
                moving = motion_state(map_motion(history[0][1], crop))
        history.append((t, crop))
        hud = hud_reader.read(full)
        mode_index = bisect.bisect_right(judge_indices, meta["i"]) - 1
        mode = judge[str(judge_indices[mode_index])].get("mode") if mode_index >= 0 else None
        stick = integral(pads, pt, t + 0.2, t + 1.5)
        pedal = integral(pads, pt, t, t + 0.1, "r2") / 0.1
        for item in selected:
            skill = item["skill"]
            result = skill.step(Observation(reading, moving, t, frame=full, hud=hud, mode=mode))
            blips = [b for b in reading.blips if b.color == skill.color]
            marker = (
                min(blips, key=lambda b: abs(math.degrees(math.atan2(b.x, b.y)) - (skill.bearing or 0)))
                if blips
                else None
            )
            eligible = (
                not reading.corrupt
                and reading.minimap == "tilted"
                and reading.route == "none"
                and reading.arrow is not None
                and marker is not None
                and result.status == "running"
            )
            raw_error = (
                None
                if marker is None or reading.arrow is None
                else (math.degrees(math.atan2(marker.x, marker.y)) - reading.arrow + 180) % 360 - 180
            )
            item["rows"].append(
                {
                    "t": round(t, 4),
                    "i": meta["i"],
                    "eligible": eligible,
                    "heading": round(skill.heading, 3),
                    "raw_heading": raw_error,
                    "stick": round(stick, 4),
                    "r2": round(pedal, 4),
                    "move": motion,
                    "d": math.hypot(marker.x, marker.y) if marker else None,
                    "rim": marker.border if marker else None,
                    "status": result.status,
                    "reason": result.reason,
                }
            )
            if result.status != "running" and item["end_reason"] is None:
                item["end_reason"] = {"t": t, "status": result.status, "reason": result.reason}
    capture.release()
    summaries = []
    with gzip.open(OUT / f"replay-{rec}.jsonl.gz", "wt") as output:
        for item in active:
            rows, stretch = item["rows"], item["stretch"]
            eligible = [r for r in rows if r["eligible"]]
            clear = [r for r in eligible if abs(r["stick"]) >= 0.15]
            turns = [r for r in clear if abs(r["heading"]) >= 30]
            distances = [r["d"] for r in rows if r["d"] is not None]
            total = stretch["end"] - stretch["start"]
            summary = {k: v for k, v in stretch.items() if k != "actions"}
            summary["mode_source"] = "causal-judge" if judge else "minimap-fallback"
            summary.update(
                {
                    "frames": len(rows),
                    "eligible": len(eligible),
                    "human_clear": len(clear),
                    "compared": len(turns),
                    "same": sum(r["stick"] * r["heading"] > 0 for r in turns),
                    "all_clear_same": sum(r["stick"] * r["heading"] > 0 for r in clear),
                    "distance_percentiles": np.percentile(distances, [0, 10, 50, 90, 100]).tolist()
                    if distances
                    else [],
                    "rim_share": sum(bool(r["rim"]) for r in rows) / max(1, len(distances)),
                    "r2_mean": integral(pads, pt, stretch["start"], stretch["end"], "r2") / total,
                    "l2_mean": integral(pads, pt, stretch["start"], stretch["end"], "l2") / total,
                    "terminal": item["end_reason"],
                }
            )
            summaries.append(summary)
            output.write(json.dumps({"start": stretch["start"], "rows": rows}, separators=(",", ":")) + "\n")
    (OUT / f"summary-{rec}.json").write_text(json.dumps(summaries, indent=2, ensure_ascii=False) + "\n")
    print(
        json.dumps(
            {
                "recording": rec,
                "frames": sum(r["frames"] for r in summaries),
                "compared": sum(r["compared"] for r in summaries),
                "same": sum(r["same"] for r in summaries),
                "ends": [r["terminal"] for r in summaries],
            }
        ),
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory-only", action="store_true")
    parser.add_argument("--recording")
    args = parser.parse_args()
    cv2.setNumThreads(1)
    rows = inventory()
    (OUT / "inventory.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
    print(f"{len(rows)} candidate stretches", flush=True)
    if not args.inventory_only:
        for rec in sorted({r["rec"] for r in rows}):
            if not args.recording or args.recording == rec:
                summary_path = OUT / f"summary-{rec}.json"
                if not args.recording and summary_path.exists():
                    previous = json.loads(summary_path.read_text())
                    repair_context = rec in {
                        "20261111-180814",
                        "20261112-092019",
                        "20261112-130333",
                    } and not previous[0].get("mode_source")
                    if not repair_context:
                        print(f"Keeping existing replay result: {rec}", flush=True)
                        continue
                replay_recording(rec, [r for r in rows if r["rec"] == rec])


if __name__ == "__main__":
    main()
