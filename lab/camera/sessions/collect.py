"""Collect the detector's output on the recorded frames of the pilot's own sessions; reads only.

    pilot/.venv/bin/python lab/camera/sessions/collect.py OUT.json SESSION[:SECONDS]...

Each session is a folder of /Users/kerim/recordings/pilot. For every fresh tick of play.jsonl, at
most ten a second, the frame of that tick is decoded from video.mp4 (by the frame_id of frames.jsonl)
and run through Detector.detect(exclude_player=False). The presses and the end of set_far_view are
taken from play.jsonl, and from the failure the skill's own opening_failed row in head.jsonl.
"""

import json
import math
import sys
from pathlib import Path

import cv2

from pilot.objects import Detector

RECORDINGS = Path("/Users/kerim/recordings/pilot")


def collect(detector, name, seconds=math.inf):
    rows = [json.loads(line) for line in (RECORDINGS / name / "play.jsonl").read_text().splitlines()]
    rows = [row for row in rows if row["t"] <= seconds]
    index = {}
    for line in (RECORDINGS / name / "frames.jsonl").read_text().splitlines():
        item = json.loads(line)
        index[item["frame_id"]] = item["i"]
    wanted, last = {}, -1.0
    for row in rows:
        if row["fresh"] and row["frame_id"] in index and row["t"] - last >= 0.1:
            wanted[index[row["frame_id"]]] = row["t"]
            last = row["t"]
    samples, capture = [], cv2.VideoCapture(str(RECORDINGS / name / "video.mp4"))
    i = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        if i in wanted:
            found = detector.detect(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), exclude_player=False)
            samples.append(
                {
                    "t": round(wanted[i], 2),
                    "dets": [[d.kind, *(round(v) for v in d.box), round(d.confidence, 2)] for d in found],
                }
            )
        i += 1
    presses, held, result, ended = [], False, None, None
    for row in rows:
        pad = row["result"]["pad"] if row["result"] else {"buttons": []}
        down = "touchpad" in pad["buttons"]
        if down and not held:
            presses.append(round(row["t"], 2))
        held = down
        skill = row["skill"] or {}
        if ended is None and skill.get("name") not in (None, "set_far_view"):
            ended = round(row["t"], 2)  # the next skill's first tick: where a failed one ended
        if row["result"] and row["result"]["status"] == "done" and skill.get("name") == "set_far_view":
            result = [round(row["t"], 2), "done", row["result"]["reason"]]
    if result is None:
        for line in (RECORDINGS / name / "head.jsonl").read_text().splitlines():
            row = json.loads(line)
            if row.get("type") == "opening_failed":
                result = [ended, "failed", row["reason"]]
    return {"recorded_presses": presses, "recorded_result": result, "samples": samples}


def main():
    out, names = Path(sys.argv[1]), sys.argv[2:]
    detector = Detector()
    with out.open("x") as stream:
        found = {}
        for item in names:
            name, _, seconds = item.partition(":")
            found[name] = collect(detector, name, float(seconds) if seconds else math.inf)
        json.dump(found, stream, separators=(",", ":"))


if __name__ == "__main__":
    main()
