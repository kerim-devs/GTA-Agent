"""Put recorded moments to the three-step head and count what the model chooses.

    PYTHONPATH=pilot/src <venv python> lab/simple/ask.py http://192.168.0.248:1234=qwen/qwen3-vl-4b [per state] [extra request fields as JSON]

Moments of the pilot's recordings of 14 November in three plain situations, by the minimap as read
then: on foot with no route, in a car with no route, in a car with a route. No console is touched;
the pictures go to the local model only. Prints for each situation what the model chose, how often
it did not answer, and the time an answer took.
"""

import bisect
import glob
import json
import random
import statistics
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

import cv2

from pilot import chooser, simple
from pilot.head import HeadRequest

WANT = {"foot": "car", "seat": "mark", "route": "drive"}


def moments(per):
    random.seed(3)
    found = {"foot": [], "seat": [], "route": []}
    for folder in sorted(glob.glob("/Users/kerim/recordings/pilot/20261114-*")):
        if not Path(folder, "video.mp4").exists():
            continue
        last = -30.0
        try:
            lines = open(folder + "/play.jsonl")
        except OSError:
            continue
        for line in lines:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            reading, skill = row.get("reading") or {}, (row.get("skill") or {}).get("name")
            if row["t"] - last < 20 or reading.get("corrupt"):
                continue
            shape, route = reading.get("minimap"), reading.get("route")
            kind = (
                "foot"
                if shape == "flat" and route == "none" and skill == "enter_vehicle"
                else "route"
                if shape == "tilted" and route == "purple" and skill == "drive_route"
                else "seat"
                if shape == "tilted" and route == "none" and skill in {"set_waypoint", "wait", "drive_on"}
                else None
            )
            if kind:
                found[kind].append((folder, row["t"], reading))
                last = row["t"]
    return {kind: random.sample(rows, min(per, len(rows))) for kind, rows in found.items()}


def frame(folder, seconds):
    times = [json.loads(line)["t"] for line in open(folder + "/frames.jsonl")]
    video = cv2.VideoCapture(folder + "/video.mp4")
    video.set(cv2.CAP_PROP_POS_FRAMES, min(bisect.bisect_left(times, seconds), len(times) - 1))
    ok, picture = video.read()
    return picture if ok else None


def main():
    server, per = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 20
    if len(sys.argv) > 3:
        # More fields for the request, as JSON: {"reasoning_effort": "none"} for a model that thinks.
        import urllib.request

        from pilot import judge

        extra, plain = json.loads(sys.argv[3]), urllib.request.Request

        def with_extra(url, data=None, headers={}, **more):
            return plain(url, json.dumps({**json.loads(data), **extra}).encode(), headers, **more)

        judge.urllib.request.Request = with_extra
    chooser.use([server])
    out = Path(tempfile.mkdtemp(prefix="simple-ask-"))
    for kind, rows in moments(per).items():
        steps, places, seconds, plain = Counter(), Counter(), [], 0
        for i, (folder, t, reading) in enumerate(rows):
            picture = frame(folder, t)
            if picture is None:
                continue
            path = out / f"{kind}-{i}.jpg"
            cv2.imwrite(str(path), picture)
            head = simple.SimpleHead()
            request = HeadRequest([], "", "", "", "", reading, None, "", str(path), {"wanted": 0})
            started = time.monotonic()
            response = head.decide(request)
            seconds.append(time.monotonic() - started)
            step = {"enter_vehicle": "car", "set_waypoint": "mark", "drive_route": "drive"}[response.plan[0].name]
            answered = response.reason.startswith("model chose")
            steps[step if answered else "no answer"] += 1
            plain += answered and step == WANT[kind]
            if step == "mark" and "destination: model chose" in response.reason:
                places[response.plan[0].args["place"]] += 1
            time.sleep(0.2)
        if not seconds:
            print(f"{kind}: no moments")
            continue
        print(
            f"{kind}: {len(seconds)} moments, the fitting step ({WANT[kind]}) chosen {plain}, "
            f"choices {dict(steps)}, median {statistics.median(seconds):.2f} s, places {dict(places)}"
        )


if __name__ == "__main__":
    main()
