"""Offline P37 evidence. Run with pilot/.venv/bin/python; never opens a bridge or judge server."""

import argparse
import bisect
import gzip
import json
import subprocess
import types
from dataclasses import asdict, replace
from pathlib import Path

import cv2
from pilot.contract import Answer, Detection, Judgment, Observation, Reading
from pilot.head import HeadRequest
from pilot.judge import ModeFilter
from pilot.mission import MissionHead
from pilot.replay import json_lines
from pilot.vehicle_entry import EnterVehicle

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "7aa2464906916c2cd81948d93252d19df3ebbe42"
SESSIONS = ("134519", "135330", "122034")


def write_rows(path, rows):
    contents = "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows)
    if path.suffix == ".gz":
        with gzip.open(path, "wt") as stream:
            stream.write(contents)
    else:
        path.write_text(contents)


def read_rows(path):
    if path.suffix == ".gz":
        with gzip.open(path, "rt") as stream:
            return [json.loads(line) for line in stream]
    return json_lines(path)


def capture(recording, output, stride):
    from pilot.loop import Pipeline, log_row
    from pilot.objects import Detector
    from pilot.replay import hud_crop

    pipeline, detector = Pipeline(), Detector()
    video = cv2.VideoCapture(str(recording / "video.mp4"))
    readings, objects = [], []
    try:
        for frame in json_lines(recording / "frames.jsonl"):
            ok, bgr = video.read()
            if not ok:
                raise ValueError(f"Missing frame {frame['i']}")
            reading, moving, command = pipeline.step(
                hud_crop(bgr), frame["t"], feedback=False
            )
            readings.append(
                log_row(
                    frame["t"],
                    frame["frame_id"],
                    0,
                    frame["t"],
                    reading,
                    moving,
                    command,
                )
            )
            if frame["i"] % stride == 0:
                detections = detector(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
                objects.append(
                    {**frame, "objects": [asdict(obj) for obj in detections]}
                )
    finally:
        video.release()
        pipeline.close()
    write_rows(output / f"{recording.name[-6:]}-readers.jsonl.gz", readings)
    write_rows(output / f"{recording.name[-6:]}-objects.jsonl.gz", objects)


def observations(recording, cache):
    session = recording.name[-6:]
    frames = json_lines(recording / "frames.jsonl")
    readings = read_rows(cache / f"{session}-readers.jsonl.gz")
    objects = read_rows(cache / f"{session}-objects.jsonl.gz")
    assert len(readings) == len(frames)
    head = next(
        row for row in json_lines(recording / "head.jsonl") if row["type"] == "request"
    )
    play = json_lines(recording / "play.jsonl")[0]
    origin = head["t"] - play["t"]
    judges = [row for row in json_lines(recording / "judge.jsonl") if "answers" in row]
    object_index, judge_index = 0, 0
    mode_filter, latest = ModeFilter(), None
    for frame, row in zip(frames, readings, strict=True):
        now = frame["t"]
        while object_index + 1 < len(objects) and objects[object_index + 1]["t"] <= now:
            object_index += 1
        while judge_index < len(judges) and judges[judge_index]["t"] - origin <= now:
            value = judges[judge_index]
            latest = Judgment(
                value["capture"] - origin,
                {key: Answer(**answer) for key, answer in value["answers"].items()},
                value["probabilities"],
                value["duration"],
                "recorded",
            )
            mode_filter.update(latest, value["t"] - origin)
            judge_index += 1
        detected = objects[object_index]
        yield (
            frame,
            Observation(
                Reading(**row["reading"]),
                row["moving"],
                now,
                objects=tuple(Detection(**obj) for obj in detected["objects"]),
                objects_time=detected["t"],
                judgment=latest,
                mode=mode_filter.update(None, now),
            ),
        )


def replay_head(recording, cache, output):
    samples = list(observations(recording, cache))
    times = [obs.time for _, obs in samples]
    requests = [
        row for row in json_lines(recording / "head.jsonl") if row["type"] == "request"
    ]
    origin = requests[0]["t"] - json_lines(recording / "play.jsonl")[0]["t"]
    head, rows = MissionHead(), []
    for row in requests:
        relative = row["t"] - origin
        frame, obs = samples[max(0, bisect.bisect_right(times, relative) - 1)]
        original = HeadRequest(**row["request"])
        minimap = asdict(obs.reading)
        # The synchronous map replay has no asynchronous GPS OCR delivery. Preserve the recorded fix.
        for key in ("gps_distance", "gps_time", "gps_speed", "gps_arrow"):
            minimap[key] = original.minimap.get(key)
        request = replace(
            original, minimap=minimap, objects=[asdict(obj) for obj in obs.objects]
        )
        response = head.decide(request)
        rows.append(
            {
                "request": row["id"],
                "t": relative,
                "frame": frame["i"],
                "last_skill": original.last_skill,
                "gps_distance": minimap["gps_distance"],
                "rule": head.last_rule,
                "plan": [asdict(call) for call in response.plan],
            }
        )
    write_rows(output / "134519-head.jsonl", rows)
    return {
        "requests": len(rows),
        "abandon": [row for row in rows if row["rule"] == "abandon_vehicle"],
    }


def old_entry():
    source = subprocess.check_output(
        ["git", "show", f"{BASELINE}:pilot/src/pilot/vehicle_entry.py"],
        cwd=ROOT,
        text=True,
    )
    module = types.ModuleType("p37_baseline_entry")
    exec(compile(source, "baseline_vehicle_entry.py", "exec"), module.__dict__)  # noqa: S102 - fixed local baseline
    return module.EnterVehicle


def replay_entry(recording, cache, output, strategy):
    entry = EnterVehicle({"strategy": strategy})
    baseline = old_entry()({}) if strategy == "normal" else None
    rows, differences, first_target, terminal = [], 0, None, None
    start = float("-inf")
    if baseline:
        play = json_lines(recording / "play.jsonl")
        first_frame = json_lines(recording / "frames.jsonl")[0]
        offset = play[0]["t"] - first_frame["t"]
        start = (
            next(
                row["t"]
                for row in play
                if (row.get("skill") or {}).get("name") == "enter_vehicle"
            )
            - offset
        )
    for frame, obs in observations(recording, cache):
        if obs.time < start:
            continue
        result = entry.step(obs)
        if baseline is not None:
            differences += result != baseline.step(obs)
        target = asdict(entry.target) if entry.target else None
        if first_target is None and target is not None:
            first_target = {"i": frame["i"], "t": obs.time, "target": target}
        if terminal is None and result.status != "running":
            terminal = {
                "i": frame["i"],
                "t": obs.time,
                "status": result.status,
                "reason": result.reason,
            }
        rows.append(
            {
                "i": frame["i"],
                "t": obs.time,
                "mode": obs.mode,
                "minimap": obs.reading.minimap,
                "corrupt": obs.reading.corrupt,
                "leaving": entry.leaving,
                "phase": entry.phase,
                "excluded": asdict(entry.excluded) if entry.excluded else None,
                "exclusion_visible": entry.exclusion_visible,
                "target": target,
                "objects": [asdict(obj) for obj in obs.objects],
                "result": asdict(result),
            }
        )
    write_rows(output / f"{recording.name[-6:]}-entry.jsonl", rows)
    return {
        "frames": len(rows),
        "first_target": first_target,
        "terminal": terminal,
        "baseline_pad_status_reason_differences": differences if baseline else None,
        "first_exclusion": next(
            (
                {"i": row["i"], "t": row["t"], "box": row["excluded"]}
                for row in rows
                if row["excluded"]
            ),
            None,
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--recordings", type=Path, default=Path("/Users/kerim/recordings/pilot")
    )
    parser.add_argument("--cache", type=Path, default=Path(__file__).with_name("cache"))
    parser.add_argument(
        "--out", type=Path, default=Path(__file__).with_name("evidence")
    )
    parser.add_argument(
        "--capture",
        action="store_true",
        help="Run real detector/readers again, offline",
    )
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)
    if args.capture:
        for session in SESSIONS:
            capture(
                args.recordings / f"20261111-{session}",
                args.cache,
                1 if session == "135330" else 6,
            )
    summary = {
        "baseline": BASELINE,
        "caveat": "Counterfactual pad outputs do not change recorded pixels. Judge answers and GPS fixes are recorded, not rerun.",
    }
    for session in SESSIONS:
        recording = args.recordings / f"20261111-{session}"
        summary[session] = (
            replay_head(recording, args.cache, args.out)
            if session == "134519"
            else replay_entry(
                recording,
                args.cache,
                args.out,
                "normal" if session == "122034" else "replace",
            )
        )
        summary[session]["reader_frames"] = len(
            read_rows(args.cache / f"{session}-readers.jsonl.gz")
        )
        summary[session]["detector_frames"] = len(
            read_rows(args.cache / f"{session}-objects.jsonl.gz")
        )
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
