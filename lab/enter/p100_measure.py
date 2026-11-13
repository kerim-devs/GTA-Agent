"""Pad-time measurements for the visually marked final approaches in P100.

Starts are the first directed movement of the final attempt (or its door press
when already beside the car). Seat endpoints are the first inspected frame
with the player in the seat, sustained in subsequent frames. Contact sheets
bound the endpoints to approximately 0.25 s. These are not thoughts or metres.
"""

import bisect
import json
import math
import statistics
from itertools import pairwise
from pathlib import Path

OUT = Path(__file__).parent
CASES = [
    ("kerim", "20261111-190825", 93.9477, 94.9464, 100.506, "stopped black sedan"),
    ("kerim", "20261111-165543", 214.2378, 216.6667, 222.570, "parked white coupe"),
    (
        "kerim",
        "20261111-171046",
        148.001,
        149.2357,
        154.597,
        "parked white van; turn from following Lamar",
    ),
    (
        "kerim",
        "20261112-085011",
        881.233,
        884.2341,
        886.260,
        "parked black van after the doorway",
    ),
    (
        "kerim",
        "20261111-185323",
        799.2858,
        803.3072,
        808.771,
        "stopped police car after firing",
    ),
    (
        "pilot",
        "20261113-230030",
        528.989,
        548.830819,
        554.519,
        "stopped black SUV; final attempt only",
    ),
    (
        "pilot",
        "20261113-234407",
        623.277308,
        623.277308,
        625.752,
        "white coupe already beside the figure",
    ),
]


def main():
    records = []
    for who, session, start, press, seat, description in CASES:
        folder = Path("/Users/kerim/recordings") / who / session
        pads = [json.loads(line) for line in (folder / "pad.jsonl").open()]
        frames = [json.loads(line) for line in (folder / "frames.jsonl").open()]
        times = [frame["t"] for frame in frames]
        marked = {}
        for name, time in (("start", start), ("press", press), ("seat", seat)):
            after = min(len(times) - 1, bisect.bisect_left(times, time))
            index = min((max(0, after - 1), after), key=lambda i: abs(times[i] - time))
            marked[name] = {"video_frame": index, "video_time": times[index]}
        walked = run = stick = 0.0
        for a, b in pairwise(pads):
            dt = max(0, min(press, b["t"]) - max(start, a["t"]))
            magnitude = math.hypot(*a["left"])
            walked += dt if magnitude > 0.3 else 0
            stick += dt * min(1, magnitude)
            run += dt if magnitude > 0.3 and "cross" in a["buttons"] else 0
        records.append(
            {
                "who": who,
                "session": session,
                "start": start,
                "press": press,
                "seat": seat,
                "description": description,
                "decision_to_seat": seat - start,
                "press_to_seat": seat - press,
                "approach_seconds": press - start,
                "commanded_movement_seconds": walked,
                "cross_down_seconds": run,
                "stick_seconds": stick,
                "frames": marked,
            }
        )
    summaries = {}
    for who in ("kerim", "pilot"):
        chosen = [r for r in records if r["who"] == who]
        summaries[who] = {
            "count": len(chosen),
            **{
                key: statistics.median(r[key] for r in chosen)
                for key in (
                    "decision_to_seat",
                    "press_to_seat",
                    "approach_seconds",
                    "commanded_movement_seconds",
                    "cross_down_seconds",
                )
            },
        }
    result = {
        "definition": __doc__,
        "scope": "Five visually verified human successes, chosen from the five P53 audited examples before measuring; two pilot successes conditional on eventual seating. Seven original skill failures include the delayed hospital success. Failed/censored attempts are not assigned fictitious seat times. Starts identify final approaches rather than all search or earlier failed attempts. Distances in metres cannot be recovered from pad logs.",
        "summaries": summaries,
        "records": records,
    }
    (OUT / "p100-measurements.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
