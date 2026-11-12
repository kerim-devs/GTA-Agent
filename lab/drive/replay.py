"""P55 tick replay. Reads recordings only; writes compact evidence beside this file."""

import argparse
import csv
import gzip
import json
import sys
import types
from collections import Counter, deque
from dataclasses import asdict, replace
from pathlib import Path
from subprocess import check_output

import cv2

from pilot.cli import LIVE, MEASURED_DELAY_S
from pilot.contract import Observation, Reading
from pilot.drive import DriveConfig, Driver
from pilot.gps import Speedometer, recognize
from pilot.motion import map_motion, motion_state
from pilot.replay import hud_crop
from pilot.skills import DriveRoute

ROOT = Path("/Users/kerim/recordings/pilot")
OUT = Path(__file__).resolve().parent
# Replacements can retain the same skill name; boundaries were matched to head.jsonl.
WINDOWS = {
    "102851": [(199.018, 206.610)],
    "103305": [(112.997, 172.985), (173.024, 198.435)],
    "104424": [(3.110, 63.124), (63.163, 99.902), (155.304, 173.418)],
    "104827": [(25.474, 65.308), (65.408, 125.336), (125.346, 171.183), (174.896, 234.877)],
    "105230": [(4.329, 36.872), (36.949, 54.972), (55.053, 59.992)],
    "105332": [(3.229, 21.109)],
}


def lines(path):
    with path.open() as f:
        return [json.loads(line) for line in f]


def offset_for(play, head):
    # Head request clocks and play ticks use the identical received timestamp.
    candidates = Counter(
        round(h["t"] - p["t"], 6) for h in head if h["type"] == "request" for p in play if p.get("fresh")
    )
    offset, matches = candidates.most_common(1)[0]
    if matches < 2:
        raise ValueError("Cannot establish the shared clock from two exact tick matches")
    return offset, matches


def crops_for(folder, play):
    frames = lines(folder / "frames.jsonl")
    wanted = {row["frame_id"] for row in play if row.get("fresh") and row.get("reading")}
    capture = cv2.VideoCapture(str(folder / "video.mp4"))
    try:
        for index, frame in enumerate(frames):
            if frame["i"] != index or not capture.grab():
                raise ValueError(f"Frame index/decode mismatch at {folder}:{index}")
            if frame["frame_id"] not in wanted:
                continue
            ok, bgr = capture.retrieve()
            if not ok:
                raise ValueError(f"Cannot retrieve {folder}:{index}")
            yield frame, hud_crop(bgr)
    finally:
        capture.release()


def motion_for(folder, play):
    return motion_for_rows(folder, play, OUT / f"{folder.name}-motion.json.gz")


def motion_for_rows(folder, play, cache):
    if cache.exists():
        with gzip.open(cache, "rt") as f:
            return {int(k): v for k, v in json.load(f).items()}
    history = deque()
    result = {}
    for frame, crop in crops_for(folder, play):
        t = frame["t"]
        while history and history[0][0] < t - 1.2:
            history.popleft()
        moving = None
        if history and t - history[0][0] >= 0.15:
            _, previous = min(history, key=lambda item: abs(t - item[0] - 0.2))
            moving = motion_state(map_motion(previous, crop))
            if moving is not True and t - history[0][0] >= 0.8:
                moving = motion_state(map_motion(history[0][1], crop))
        history.append((t, crop.copy()))
        result[frame["frame_id"]] = moving
    with gzip.open(cache, "wt") as f:
        json.dump(result, f, separators=(",", ":"))
    return result


def native(folder, play, windows):
    # Baseline is the committed reader, loaded without writing or importing the CLI.
    old = types.ModuleType("pilot._p55_baseline_gps")
    sys.modules[old.__name__] = old
    source = check_output(["git", "show", "f6df0ab:pilot/src/pilot/gps.py"], cwd=OUT, text=True)
    exec(compile(source, "<baseline gps>", "exec"), old.__dict__)
    meters = [old.Speedometer(), Speedometer()]
    last_ocr = None
    counts = [0, 0]
    total = calls = 0
    for frame, crop in crops_for(folder, play):
        t = frame["t"]
        if not any(a <= t <= b for a, b in windows):
            continue
        fixes = [None, None]
        if last_ocr is None or t - last_ocr >= 0.25:
            last_ocr = t
            fixes = [old.recognize(crop), recognize(crop)]
            calls += 1
        for i, meter in enumerate(meters):
            meter.update(t, fixes[i])
            counts[i] += int(meter.time is not None and 0 <= t - meter.time <= meter.stale)
        total += 1
    return dict(session=folder.name, sampled_ticks=total, ocr_pairs=calls, before=counts[0], after=counts[1])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", action="store_true", help="Repeat original/new Vision OCR on frames")
    args = parser.parse_args()
    summary = []
    native_results = []
    if args.native:
        for suffix, windows in WINDOWS.items():
            folder = ROOT / f"20261112-{suffix}"
            try:
                native_results.append(native(folder, lines(folder / "play.jsonl"), windows))
            except RuntimeError as exc:
                native_results.append({"session": folder.name, "unavailable": str(exc)})
                break
        (OUT / "native.json").write_text(json.dumps(native_results, indent=2) + "\n")
        print(json.dumps(native_results), flush=True)
        return
    with gzip.open(OUT / "ticks.csv.gz", "wt") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "session",
                "drive_start",
                "t",
                "moving",
                "recorded_distance",
                "after_distance",
                "age",
                "status",
                "reason",
            ]
        )
        for suffix, windows in WINDOWS.items():
            folder = ROOT / f"20261112-{suffix}"
            play, head = lines(folder / "play.jsonl"), lines(folder / "head.jsonl")
            offset, matches = offset_for(play, head)
            motion = motion_for(folder, play)
            for start, end in windows:
                selected = [
                    r
                    for r in play
                    if start - 0.0005 <= r["t"] <= end + 0.0005
                    and (r.get("skill") or {}).get("name") == "drive_route"
                ]
                skill = DriveRoute({}, driver=Driver(DriveConfig(command_delay=MEASURED_DELAY_S, **LIVE)))
                before = retained = fresh = 0
                distances = []
                ended_at = None
                last_distance = last_at = None
                counts = Counter()
                for row in selected:
                    raw = row.get("reading")
                    if raw and raw.get("gps_distance") is not None:
                        before += 1
                        distances.append(raw["gps_distance"])
                        last_distance, last_at = raw["gps_distance"], raw["gps_time"] - offset
                    retained += last_distance is not None
                    fresh += last_at is not None and 0 <= row["t"] - last_at <= skill.driver.config.gps_stale
                    if raw and row.get("fresh"):
                        reading = Reading(
                            **{k: v for k, v in raw.items() if k in Reading.__dataclass_fields__}
                        )
                        reading = replace(
                            reading,
                            blips=(),
                            gps_time=None if reading.gps_time is None else reading.gps_time - offset,
                        )
                        moving = motion.get(row["frame_id"])
                        counts[str(moving)] += 1
                        result = skill.step(Observation(reading, moving, row["t"]))
                        if result.status != "running" and ended_at is None:
                            ended_at = row["t"]
                    else:
                        result = skill.finished
                        moving = None
                    writer.writerow(
                        [
                            suffix,
                            start,
                            round(row["t"], 4),
                            moving,
                            None if raw is None else raw["gps_distance"],
                            last_distance,
                            None if last_at is None else round(row["t"] - last_at, 3),
                            None if result is None else result.status,
                            None if result is None else result.reason,
                        ]
                    )
                output = dict(
                    session=suffix,
                    start=start,
                    end=end,
                    ticks=len(selected),
                    recorded_start=distances[0] if distances else None,
                    recorded_end=distances[-1] if distances else None,
                    read_before=before,
                    read_after=before,
                    retained_with_age=retained,
                    fresh_with_age=fresh,
                    clock_offset=offset,
                    clock_matches=matches,
                    motion=counts,
                    ended_at=ended_at,
                    ending=asdict(skill.finished)
                    if skill.finished
                    else {
                        "status": "running",
                        "reason": "recording-ended-or-replaced",
                        "start_distance": skill.start_distance,
                        "end_distance": skill.end_distance,
                    },
                )
                summary.append(output)
                print(json.dumps(output), flush=True)
    (OUT / "replay.json").write_text(json.dumps(summary, indent=2) + "\n")
    if args.native:
        (OUT / "native.json").write_text(json.dumps(native_results, indent=2) + "\n")


if __name__ == "__main__":
    main()
