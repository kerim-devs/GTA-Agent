"""Measure every labelled fire stretch from cached HUD and original pad records."""

import argparse
import json
import math
import statistics
from itertools import pairwise
from pathlib import Path


def intervals(rows, key, start, end):
    active, since = False, None
    spans = []
    for row in rows:
        time = row["t"]
        if time > end:
            break
        value = row.get(key, 0) > 0.5 if key in ("l2", "r2") else key in row["buttons"]
        if value and not active:
            since = max(start, time)
        if active and not value and time > start:
            spans.append([since, min(time, end)])
        active = value
    if active:
        spans.append([since, end])
    return [span for span in spans if span[1] > span[0]]


def describe(values):
    values = sorted(values)
    return {
        "count": len(values),
        "min": min(values) if values else None,
        "median": statistics.median(values) if values else None,
        "p10": values[int((len(values) - 1) * 0.1)] if values else None,
        "p25": values[int((len(values) - 1) * 0.25)] if values else None,
        "p90": values[int((len(values) - 1) * 0.9)] if values else None,
        "max": max(values) if values else None,
    }


def jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def overlaps(a, b):
    return a[0] < b[1] and b[0] < a[1]


def stick(rows, start, end, key):
    """Time-weighted stick components, magnitude and moving fraction."""
    total = [0.0] * 4
    for index, row in enumerate(rows):
        until = rows[index + 1]["t"] if index + 1 < len(rows) else end
        weight = max(0, min(end, until) - max(start, row["t"]))
        x, y = row[key]
        magnitude = math.hypot(x, y)
        for k, value in enumerate((x, y, magnitude, float(magnitude > 0.2))):
            total[k] += weight * value
    return dict(zip(("x", "y", "magnitude", "moving_share"), (v / (end - start) for v in total), strict=True))


def measure_corpus(root, cases_path):
    rows, hit_rows, missing = [], [], []
    cases = json.loads(cases_path.read_text())["cases"]
    for action_path in sorted((root / "derived" / "kerim").glob("*/actions.jsonl")):
        recording = root / "kerim" / action_path.parent.name
        if not (recording / "pad.jsonl").exists():
            missing.append(str(recording))
            continue
        actions = [a for a in jsonl(action_path) if a["action"] == "fire"]
        pads = jsonl(recording / "pad.jsonl")
        hud = jsonl(action_path.parent / "hud.jsonl")
        spans = {key: intervals(pads, key, 0, pads[-1]["t"]) for key in ("l2", "r2", "r1", "square")}
        labels = json.loads((action_path.parent / "labels.json").read_text())
        lead = labels.get("lead", 0.16)
        if not isinstance(lead, (int, float)):
            raise ValueError(f"unexpected lead: {lead!r}")
        fight, previous_end = 0, -10.0
        for action in actions:
            begin, finish = action["start"] - lead, action["end"] - lead
            if begin - previous_end > 2:
                fight += 1
            previous_end = finish
            window = (max(0, begin), finish)
            firing = [s for s in spans["r2"] if overlaps(s, window)]
            locks = [s for s in spans["l2"] if overlaps(s, window)]
            pictures = [h for h in hud if action["start"] <= h["t"] <= action["end"]]
            group = "red" if any(h["red"] and not h["corrupt"] for h in pictures) else "no-red"
            record = {
                "recording": recording.name,
                "fight": fight,
                "picture_window": [action["start"], action["end"]],
                "lead": lead,
                "group": group,
                "burst_intervals": firing,
                "lock_measurements": [],
                "r1_intervals": [s for s in spans["r1"] if overlaps(s, window)],
                "reload_intervals": [s for s in spans["square"] if overlaps(s, window)],
                "left_firing": stick(pads, *window, "left"),
                "right_firing": stick(pads, *window, "right"),
            }
            for lock in locks:
                shots = [s for s in spans["r2"] if overlaps(s, lock)]
                first = max(lock[0], shots[0][0]) if shots else None
                history = [h for h in hud if h["t"] <= lock[0] + lead]
                onset = None
                # Require a preceding readable no-red sample; censor recording boundaries.
                if history and history[-1]["red"] and not history[-1]["corrupt"]:
                    index = len(history) - 1
                    while index and history[index - 1]["red"] and not history[index - 1]["corrupt"]:
                        index -= 1
                    if index and not history[index - 1]["corrupt"]:
                        onset = history[index]["t"]
                next_lock = next((s for s in spans["l2"] if s[0] >= lock[1]), None)
                record["lock_measurements"].append(
                    {
                        "interval": lock,
                        "first_shot_delay": first - lock[0] if first is not None else None,
                        "bursts": len(shots),
                        "relock_gap": next_lock[0] - lock[1] if next_lock else None,
                        "marker_to_l2": lock[0] - (onset - lead) if onset is not None else None,
                        "onset_censored": onset is None,
                        "right_before": stick(pads, max(0, lock[0] - 0.5), lock[0], "right")
                        if lock[0] > 0
                        else None,
                        "right_during": stick(pads, *lock, "right"),
                    }
                )
            rows.append(record)
        for case in cases:
            if case.get("kind") != "hit" or case["recording"] != f"kerim/{recording.name}":
                continue
            start = case["first"][1] - lead
            hit_rows.append(
                {
                    "name": case["name"],
                    "recording": recording.name,
                    "group": "red" if case["red_markers"] else "no-red",
                    "time": start,
                    "left": stick(pads, start, start + 2, "left"),
                    "right": stick(pads, start, start + 2, "right"),
                    "r1": intervals(pads, "r1", start, start + 2),
                    "reload": intervals(pads, "square", start, start + 2),
                    "aim": intervals(pads, "l2", start, start + 2),
                    "fire": intervals(pads, "r2", start, start + 2),
                }
            )
        print(f"{recording.name}: {len(actions)} fire stretches", flush=True)
    return {
        "method": (
            "All derived fire stretches, red if a noncorrupt cached HUD sample has red. "
            "Full raw pad intervals deduplicated per group. Fights split at >2s between fire stretches. "
            "Marker onset is last contiguous red run before aim, censored at boundary/corruption. "
            "Hand-picture lead from labels. No-red is not proof of unarmed; labels can include mistakes."
        ),
        "rows": rows,
        "hits": hit_rows,
        "missing": missing,
        "summary": summarize(rows, hit_rows),
    }


def summarize(rows, hits):
    output = {}
    for group in ("red", "no-red"):
        selected = [r for r in rows if r["group"] == group]
        unique = {
            key: {} for key in ("burst_intervals", "lock_measurements", "r1_intervals", "reload_intervals")
        }
        for row in selected:
            for key in unique:
                for item in row[key]:
                    span = item["interval"] if isinstance(item, dict) else item
                    unique[key][(row["recording"], *span)] = item
        locks = list(unique["lock_measurements"].values())
        bursts = sorted(unique["burst_intervals"])
        values = {
            "l2_hold": [m["interval"][1] - m["interval"][0] for m in locks],
            "l2_to_r2": [m["first_shot_delay"] for m in locks if m["first_shot_delay"] is not None],
            "bursts_per_lock": [m["bursts"] for m in locks],
            "relock_gap": [
                m["relock_gap"] for m in locks if m["relock_gap"] is not None and m["relock_gap"] <= 2
            ],
            "marker_to_l2": [m["marker_to_l2"] for m in locks if m["marker_to_l2"] is not None],
            "r2_burst": [b[2] - b[1] for b in bursts],
            "r2_gap": [b[1] - a[2] for a, b in pairwise(bursts) if a[0] == b[0] and 0 <= b[1] - a[2] <= 2],
            "r1_hold": [b[1] - b[0] for b in unique["r1_intervals"].values()],
            "reload_hold": [b[1] - b[0] for b in unique["reload_intervals"].values()],
            "right_before_aim": [m["right_before"]["magnitude"] for m in locks if m["right_before"]],
            "right_during_aim": [m["right_during"]["magnitude"] for m in locks],
            "left_firing": [r["left_firing"]["magnitude"] for r in selected],
            "left_firing_x": [r["left_firing"]["x"] for r in selected],
            "left_firing_y": [r["left_firing"]["y"] for r in selected],
        }
        selected_hits = [h for h in hits if h["group"] == group]
        for axis in ("x", "y", "magnitude", "moving_share"):
            values[f"hit_left_{axis}"] = [h["left"][axis] for h in selected_hits]
        moving = [h for h in selected_hits if h["left"]["moving_share"] > 0]
        values["hit_moving_x"] = [h["left"]["x"] for h in moving]
        values["hit_moving_y"] = [h["left"]["y"] for h in moving]
        values["hit_moving_magnitude"] = [h["left"]["magnitude"] for h in moving]
        output[group] = {
            "stretches": len(selected),
            "fights": len({(r["recording"], r["fight"]) for r in selected}),
            "recordings": len({r["recording"] for r in selected}),
            "hits": len(selected_hits),
            "hit_cover": sum(bool(h["r1"]) for h in selected_hits),
            "hit_reload": sum(bool(h["reload"]) for h in selected_hits),
            "metrics": {key: describe(value) for key, value in values.items()},
        }
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/Users/kerim/recordings"))
    parser.add_argument("--cases", type=Path, default=Path("../lab/health/cases.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = measure_corpus(args.root, args.cases)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
