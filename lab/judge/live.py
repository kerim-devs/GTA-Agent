"""Run the pilot's judge over a stretch of a recording in real time, against a real server.

    pilot/.venv/bin/python lab/judge/live.py --judge http://<server>:1234=qwen/qwen3-vl-8b \
        /Users/kerim/recordings/kerim/20261111-065022 15600-17400

The frames are polled at the pace they were recorded, thirty times a second as the pilot does, so
the judgments per second, their age when they arrive and the accepted mode are what a session gets.
"""

import argparse
import json
import statistics
import time
from pathlib import Path

import cv2
from pilot.judge import ModeFilter, Reader

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("recording", type=Path)
parser.add_argument("stretch", metavar="FIRST-LAST")
parser.add_argument("--judge", action="append", required=True, metavar="URL=MODEL")
args = parser.parse_args()

first, last = (int(part) for part in args.stretch.split("-"))
times = [json.loads(line)["t"] for line in (args.recording / "frames.jsonl").read_text().splitlines()]
video = cv2.VideoCapture(str(args.recording / "video.mp4"))
video.set(cv2.CAP_PROP_POS_FRAMES, first)
reader, modes = Reader(args.judge), ModeFilter()
started, origin = time.monotonic(), times[first]
judgments, ages, changes, failures, mode = [], [], [], [], None
try:
    for index in range(first, last + 1):
        ok, bgr = video.read()
        if not ok:
            break
        if (index - first) % 2:  # the recording has 60 frames a second, the pilot ticks at 30
            continue
        due = started + times[index] - origin
        time.sleep(max(0.0, due - time.monotonic()))
        now = time.monotonic()
        judgment = reader.poll(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), now)
        accepted = modes.update(judgment, now)
        failures.extend(reader.drain_failures())
        if judgment is not None:
            judgments.append(judgment)
            ages.append(now - judgment.capture)
        if accepted != mode:
            changes.append((index, mode, accepted))
            mode = accepted
finally:
    reader.close()
seconds = time.monotonic() - started
durations = sorted(judgment.duration for judgment in judgments)
print(
    json.dumps(
        {
            "seconds": round(seconds, 1),
            "judgments": len(judgments),
            "per_second": round(len(judgments) / seconds, 2),
            "duration_median": round(statistics.median(durations), 3) if durations else None,
            "duration_p90": round(durations[int(len(durations) * 0.9)], 3) if durations else None,
            "age_at_arrival_median": round(statistics.median(ages), 3) if ages else None,
            "servers": sorted({judgment.server for judgment in judgments}),
            "failures": [failure["error"] for failure in failures],
            "mode_changes": changes,
            "answers": "".join(
                {"foot": "A", "vehicle": "B", "none": "C"}[judgment.answers["mode"].value]
                for judgment in judgments
            ),
        },
        indent=1,
    )
)
