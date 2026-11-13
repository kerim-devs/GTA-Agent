"""Locate human entry labels and measure raw pad intervals without video decoding."""

import bisect
import json
import statistics
from pathlib import Path

OUT = Path(__file__).parent
INDEX = Path("/Users/kerim/recordings/derived/kerim/index.jsonl")


def main():
    by_session = {}
    for line in INDEX.open():
        row = json.loads(line)
        by_session.setdefault(row["recording"], []).append(row)
    entries = []
    for folder, labels in by_session.items():
        pads = [json.loads(line) for line in (Path(folder) / "pad.jsonl").open()]
        times = [p["t"] for p in pads]
        i = 0
        while i < len(labels):
            if labels[i]["action"] != "enter_vehicle":
                i += 1
                continue
            start = i
            while i < len(labels) and labels[i]["action"] == "enter_vehicle":
                i += 1
            end = i
            window = pads[
                max(
                    0, bisect.bisect_left(times, labels[start]["time"] - 0.65)
                ) : bisect.bisect_right(times, labels[start]["time"] + 0.65)
            ]
            press = next((p["t"] for p in window if "triangle" in p["buttons"]), None)
            release = (
                next(
                    (
                        p["t"]
                        for p in pads[bisect.bisect_left(times, press or 0) :]
                        if "triangle" not in p["buttons"]
                    ),
                    None,
                )
                if press is not None
                else None
            )
            approach = start
            while approach > 0 and labels[approach - 1]["action"] in {
                "walk",
                "sprint",
                "look",
                "idle",
                "wait",
            }:
                if labels[start]["time"] - labels[approach - 1]["time"] > 20:
                    break
                approach -= 1
            entry = {
                "session": Path(folder).name,
                "label_start": labels[start]["time"],
                "label_end": labels[end]["time"] if end < len(labels) else None,
                "after": labels[end]["action"] if end < len(labels) else None,
                "press": press,
                "hold": release - press if release is not None else None,
                "approach_label_start": labels[approach]["time"],
                "preceding": [
                    (l["time"], l["action"]) for l in labels[max(0, start - 25) : start]
                ],
            }
            entries.append(entry)
    holds = [e["hold"] for e in entries if e["hold"] is not None]
    summary = {
        "entries": len(entries),
        "matched_presses": len(holds),
        "median_hold": statistics.median(holds),
        "records": entries,
    }
    (OUT / "p100-human-labels.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(
        "entries",
        len(entries),
        "matched",
        len(holds),
        "median hold",
        statistics.median(holds),
    )
    for e in entries:
        print(
            e["session"],
            round(e["label_start"], 2),
            round(e["label_end"] - e["label_start"], 2) if e["label_end"] else None,
            e["after"],
            "press",
            round(e["press"], 2) if e["press"] else None,
            "approach",
            round(e["approach_label_start"], 2),
        )


if __name__ == "__main__":
    main()
