"""Prints what lab/models/bench.py has measured as one table per question set.

    pilot/.venv/bin/python lab/models/table.py
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = Path(__file__).with_name("results")


def load(path):
    return json.loads(path.read_text())


def seconds(spread, high="p90"):
    return f"{spread['median']:.2f} / {spread.get(high, spread.get('p95', 0)):.2f}" if spread else ""


print("fast questions, 210 frames (share right; seconds median / p90)")
for path in sorted((ROOT / "lab" / "judge" / "results").glob("*-640-joint-bench.json")):
    data = load(path)
    data = data.get("summary", data)
    print(
        f"  {data['model']:28s} mode {data['mode']:.3f}  overlay {data['overlay']:.3f}  wanted {data['wanted']:.3f}"
        f"  banner {data['banner']:.3f}  {seconds(data['seconds_frame'])}"
    )

print("\npicks, 150 situations, the rules' first option is right in 141 (right; seconds median / p90 or p95)")
for path in sorted(RESULTS.glob("chooser-*.json")):
    data = load(path)
    at = next(row for row in data["thresholds"] if row["threshold"] == 0.4)
    print(f"  {data['server'].split('=')[-1]:28s} one letter      {at['right']:3d}  {seconds(data['latency_seconds'])}")
for path in sorted(RESULTS.glob("think-*.json")):
    data = load(path)
    how = "own thinking  " if path.stem.endswith("-native") else "brief reasons "
    tokens = data.get("completion_tokens_median")
    print(f"  {data['model']:28s} {how}  {data['right']:3d}  {seconds(data['seconds'])}  {tokens} tokens")

print("\nplace, room / landing / street (right of frames; seconds median / p90)")
for path in sorted(RESULTS.glob("scene-*.json")):
    data = load(path)
    how = "own thinking" if "-native" in path.stem else "brief reasons" if data["think"] else "one letter"
    places = "  ".join(f"{name} {row['right']}/{row['n']}" for name, row in data["by_place"].items() if name != "porch")
    print(f"  {data['model']:28s} {how:13s} {data['right']:3d}/{data['frames']:3d}  {places}  {seconds(data['seconds'])}")

print("\nbeside each other: the fast one asked at 4 Hz, seconds median / p99, answers over 1 s")
for path in sorted(RESULTS.glob("beside-*.json")):
    data = load(path)
    how = "reasoning" if data["big_tokens"] > 3 else "one letter"
    alone, beside, big = data["fast_alone"], data["fast_beside_big"], data["big_beside_fast"]
    name = re.sub(r"^qwen/", "", data["fast"]) + " + " + re.sub(r"^qwen/", "", data["big"])
    print(
        f"  {name:44s} big {how:10s} fast alone {seconds(alone, 'p99')} ({data['fast_alone_over_1s']} late)"
        f"  beside {seconds(beside, 'p99')} ({data['fast_beside_big_over_1s']} late)  big {seconds(big, 'p99')}"
    )
