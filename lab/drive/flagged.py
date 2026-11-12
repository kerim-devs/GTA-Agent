"""What the driver sends over the stretch of 20261112-142428 in which every tick was flagged corrupt.

Reads the recording only. The recorded readings, the motion read from the frames and the clock go to the
driver as they were. The car there stood still because the driver of the time sent nothing, so the replay
answers what each driver sends to those readings, not the drive that would have followed from it.
"""

import csv
import gzip
import json
import sys
from dataclasses import replace
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from subprocess import check_output

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT))

import replay  # noqa: E402

from pilot.cli import LIVE, MEASURED_DELAY_S  # noqa: E402
from pilot.contract import Observation, Reading  # noqa: E402
from pilot.drive import DriveConfig, Driver  # noqa: E402
from pilot.skills import DriveRoute  # noqa: E402

SESSION = replay.ROOT / "20261112-142428"
WINDOW = (168.0, 242.0)
BEFORE = "a66e975"  # the last commit before this change
ONSET = 170.56  # the first tick of the flag that stayed
# A rough car for the third run: metres per second squared at full throttle, at full brake, rolling drag.
PUSH, BRAKE, DRAG = 5.0, 9.0, 0.5


def before_module():
    """The driver as the commit had it, loaded beside the one in the working tree."""
    source = check_output(["git", "show", f"{BEFORE}:pilot/src/pilot/drive.py"], cwd=OUT, text=True)
    spec = spec_from_file_location("pilot._flagged_before_drive", OUT / "flagged.py")
    module = module_from_spec(spec)
    module.__package__ = "pilot"
    sys.modules[spec.name] = module
    exec(compile(source, "<drive before>", "exec"), module.__dict__)
    return module


def drive_window(play):
    """The rows of the one drive that runs through the stretch, from twenty seconds before it."""
    drives = [r for r in play if r["t"] <= WINDOW[1] and (r.get("skill") or {}).get("name") == "drive_route"]
    kept = []
    for row in reversed(drives):
        if kept and kept[-1]["t"] - row["t"] > 1.0:
            break
        kept.append(row)
    return [r for r in reversed(kept) if r["t"] >= WINDOW[0] - 20.0]


def run(driver, rows, moves, offset, car=False):
    """The driver over the recorded readings. With `car` the speed after the onset is the one of a rough
    car that answers the driver's own commands, instead of the recorded one of a car left standing."""
    skill = DriveRoute({"duration": 120}, driver=driver)
    driver.flagged_time = getattr(driver, "flagged_time", 0.0)
    ticks, ending = [], None
    speed = last_t = None
    for row in rows:
        raw = row.get("reading")
        if not (raw and row.get("fresh")):
            continue
        reading = Reading(**{k: v for k, v in raw.items() if k in Reading.__dataclass_fields__})
        reading = replace(
            reading, blips=(), gps_time=None if reading.gps_time is None else reading.gps_time - offset
        )
        if car and row["t"] >= ONSET:
            if speed is None:
                speed = max(0.0, next(r["reading"]["gps_speed"] or 0 for r in rows if r["t"] >= ONSET))
            elif ticks:
                step = row["t"] - last_t
                last = ticks[-1]
                speed = max(0.0, speed + (PUSH * last["r2"] - BRAKE * last["l2"] - DRAG) * step)
            reading = replace(reading, gps_speed=speed)
        last_t = row["t"]
        result = skill.step(Observation(reading, moves.get(row["frame_id"]), row["t"]))
        ticks.append(
            dict(
                t=round(row["t"], 3),
                flag=bool(reading.corrupt),
                moving=moves.get(row["frame_id"]),
                speed=None if reading.gps_speed is None else round(reading.gps_speed, 1),
                state=driver._last.state,
                steer=round(result.pad.left[0], 3),
                r2=round(result.pad.r2, 3),
                l2=round(result.pad.l2, 3),
                status=result.status,
                reason=result.reason,
                flagged=round(driver.flagged_time, 2),
                recorded_r2=round(row["sent_pad"]["r2"], 3),
            )
        )
        if result.status != "running" and ending is None:
            ending = dict(t=row["t"], status=result.status, reason=result.reason)
            break
    return ticks, ending


def seconds(ticks):
    table = {}
    for tick in ticks:
        table.setdefault(int(tick["t"]), []).append(tick)
    rows = []
    for second, group in sorted(table.items()):
        states = {}
        for tick in group:
            states[tick["state"]] = states.get(tick["state"], 0) + 1
        rows.append(
            dict(
                second=second,
                ticks=len(group),
                states=states,
                mean_r2=round(sum(x["r2"] for x in group) / len(group), 2),
                mean_l2=round(sum(x["l2"] for x in group) / len(group), 2),
                mean_steer=round(sum(x["steer"] for x in group) / len(group), 2),
                speed=group[-1]["speed"],
            )
        )
    return rows


def main():
    play, head = replay.lines(SESSION / "play.jsonl"), replay.lines(SESSION / "head.jsonl")
    offset, _ = replay.offset_for(play, head)
    rows = drive_window(play)
    moves = replay.motion_for_rows(SESSION, rows, OUT / "flagged-motion.json.gz")
    old = before_module()
    before = old.Driver(old.DriveConfig(command_delay=MEASURED_DELAY_S, **LIVE))
    after = Driver(DriveConfig(command_delay=MEASURED_DELAY_S, **LIVE))
    rolling = Driver(DriveConfig(command_delay=MEASURED_DELAY_S, **LIVE))
    runs = {
        "before": run(before, rows, moves, offset),
        "after": run(after, rows, moves, offset),
        "after-with-a-car-that-answers": run(rolling, rows, moves, offset, car=True),
    }
    summary = {}
    with gzip.open(OUT / "flagged-ticks.csv.gz", "wt") as stream:
        writer = csv.writer(stream)
        writer.writerow(["driver", *runs["before"][0][0].keys()])
        for name, (ticks, ending) in runs.items():
            for tick in ticks:
                writer.writerow([name, *tick.values()])
            summary[name] = dict(ending=ending, seconds=seconds([t for t in ticks if t["t"] >= 168]))
    (OUT / "flagged.json").write_text(json.dumps(summary, indent=1) + "\n")
    for name, (_, ending) in runs.items():
        print(name, "ending:", ending)
        for row in summary[name]["seconds"]:
            if row["second"] <= 178 or row["second"] % 10 == 0:
                print(" ", row)


if __name__ == "__main__":
    main()
