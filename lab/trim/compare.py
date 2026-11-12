"""Compare rebuilt labels on the retained original clock and reject gap-spanning output."""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAME = "20261111-183820"
SOURCE = Path("/Users/kerim/recordings/derived/kerim") / NAME
RECORDING = ROOT / "work/trimmed/kerim" / NAME
DERIVED = ROOT / "work/trimmed/derived/kerim" / NAME


def jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def compare(before, after, times, key):
    def at(rows, timestamp):
        return next((row[key] for row in rows if row["start"] <= timestamp < row["end"]), "unmatched")

    pairs = Counter((at(before, t), at(after, t)) for t in times)
    equal = sum(count for (a, b), count in pairs.items() if a == b)
    return {
        "source_intervals": len(before), "rebuilt_intervals": len(after),
        "kept_frames": len(times), "matching_frames": equal, "agreement": equal / len(times),
        "disagreements": {f"{a} -> {b}": n for (a, b), n in pairs.most_common() if a != b},
    }


def main():
    frames = jsonl(RECORDING / "frames.jsonl")
    gaps = [(a["t"], b["t"]) for a, b in zip(frames, frames[1:]) if b["t"] - a["t"] > 1]
    results = {"recording": NAME, "clock_gaps": gaps}
    for name, key in (("sections", "kind"), ("actions", "action")):
        if name == "sections":
            before = json.loads((SOURCE / "sections.json").read_text())["sections"]
            after = json.loads((DERIVED / "sections.json").read_text())["sections"]
        else:
            before, after = jsonl(SOURCE / "actions.jsonl"), jsonl(DERIVED / "actions.jsonl")
        crossing = [row for row in after if any(row["start"] < b - .002 and row["end"] > a + .002 for a, b in gaps)]
        if crossing:
            raise ValueError(f"Rebuilt {name} spans missing footage: {crossing}")
        results[name] = dict(compare(before, after, [row["t"] for row in frames], key), gap_crossings=0)
    results["unavailable"] = [name for name in ("texts.jsonl", "missions.json", "incidents.jsonl") if not (DERIVED / name).exists()]
    (ROOT / "comparison.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
