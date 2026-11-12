"""Score frozen visual labels; abstention is not a correct binary classification."""

import json
from collections import Counter, defaultdict

import numpy as np

from measure import HERE

LABELS = json.loads((HERE / "labels.json").read_text())
MEANINGS = {
    "C": "carriageway",
    "S": "roadside",
    "O": "open",
    "I": "inside",
    "P": "parked",
    "T": "traffic",
    "D": "driving",
}


def label(identifier):
    dataset = "foot" if identifier.startswith("f") else "vehicle"
    i = int(identifier[1:])
    code = LABELS[dataset + "_pages"][str(i // 24)].split()[i % 24]
    return code


def scores(rows, question):
    confusion = defaultdict(Counter)
    calibration = defaultdict(list)
    latency = []
    errors = 0
    for row in rows:
        code = label(row["id"])
        if code == "X":
            continue
        truth = (
            MEANINGS[code[0]]
            if question != "edge"
            else {"L": "left", "R": "right", "U": "unknown"}.get(code[-1], "unknown")
        )
        answer = row.get("answers", {}).get(question)
        if not answer:
            if "error" in row:
                errors += 1
                confusion[truth]["error"] += 1
                latency.append(row["duration"])
            continue
        value = answer["value"]
        confusion[truth][value] += 1
        latency.append(row["duration"])
        p = answer["probability"]
        if p is not None:
            bucket = (
                "<0.5"
                if p < 0.5
                else "0.5-0.8"
                if p < 0.8
                else "0.8-0.95"
                if p < 0.95
                else ">=0.95"
            )
            calibration[bucket].append((p, value == truth))
    n = sum(sum(c.values()) for c in confusion.values())
    result = {
        "n": n,
        "errors": errors,
        "confusion": dict(confusion),
        "accuracy": sum(c.get(t, 0) for t, c in confusion.items()) / n if n else None,
    }
    if latency:
        result["seconds"] = {
            "mean": float(np.mean(latency)),
            "p50": float(np.median(latency)),
            "p95": float(np.percentile(latency, 95)),
            "max": max(latency),
        }
    result["calibration"] = {
        k: {
            "n": len(v),
            "mean_probability": float(np.mean([p for p, _ in v])),
            "accuracy": float(np.mean([correct for _, correct in v])),
        }
        for k, v in calibration.items()
    }
    if question == "where" and n:
        lane = confusion["carriageway"]
        lane_n = sum(lane.values())
        false_safe = sum(lane.get(c, 0) for c in ("roadside", "open", "inside"))
        binary = lane.get("carriageway", 0) + sum(
            sum(
                count
                for pred, count in c.items()
                if pred in {"roadside", "open", "inside"}
            )
            for truth, c in confusion.items()
            if truth != "carriageway"
        )
        result.update(
            binary_accuracy=binary / n,
            carriageway_n=lane_n,
            false_safe=false_safe,
            false_safe_rate=false_safe / lane_n if lane_n else None,
        )
        result["gate_pass"] = bool(
            lane_n and binary / n >= 0.9 and false_safe / lane_n <= 0.05
        )
    if question == "vehicle" and n:
        negatives = sum(sum(confusion[k].values()) for k in ("traffic", "driving"))
        false_parked = sum(
            confusion[k].get("parked", 0) for k in ("traffic", "driving")
        )
        result.update(
            traffic_driving_n=negatives,
            false_parked=false_parked,
            false_parked_rate=false_parked / negatives if negatives else None,
        )
        result["negative_gate_pass"] = bool(
            negatives and false_parked / negatives <= 0.1
        )
    if question == "edge" and n:
        directional = sum(sum(confusion[k].values()) for k in ("left", "right"))
        correct = sum(confusion[k].get(k, 0) for k in ("left", "right"))
        result.update(directional_n=directional, directional_correct=correct)
    return result


def analyze():
    output = {}
    for path in sorted(HERE.glob("answers-*.jsonl")):
        grouped = defaultdict(list)
        for row in map(json.loads, path.read_text().splitlines()):
            grouped[row["variant"]].append(row)
        output[path.stem] = {
            variant: {
                q: scores(rows, q)
                for q in (
                    ("where", "edge")
                    if "foot" in path.name and variant.endswith("pair")
                    else ("where",)
                    if "foot" in path.name
                    else ("vehicle",)
                )
            }
            for variant, rows in grouped.items()
        }
    (HERE / "metrics.json").write_text(json.dumps(output, indent=2) + "\n")
    for dataset, variants in output.items():
        for variant, questions in variants.items():
            for question, s in questions.items():
                if not s["n"]:
                    continue
                print(
                    dataset,
                    variant,
                    question,
                    s["n"],
                    "accuracy",
                    round(s["accuracy"], 3),
                    "binary",
                    s.get("binary_accuracy"),
                    "false-safe",
                    s.get("false_safe_rate"),
                    "false-parked",
                    s.get("false_parked_rate"),
                    "p95",
                    round(s["seconds"]["p95"], 3),
                )


if __name__ == "__main__":
    analyze()
