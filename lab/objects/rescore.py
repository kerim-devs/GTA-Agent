"""Apply a reviewed label correction to every saved candidate without rerunning inference."""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot/tools"))
from evaluate_objects import evaluate
from pilot.contract import Detection


class SavedPredictions:
    def __init__(self, details):
        self.rows = iter(details)

    def detect(self, frame, *, exclude_player=False):
        return tuple(
            Detection(d["kind"], tuple(d["box"]), d["confidence"]) for d in next(self.rows)["detections"]
        )


def main():
    folder = ROOT / "lab/objects"
    labels = folder / "labels.json"
    records = json.loads(labels.read_text())["frames"]
    summaries = []
    for path in sorted(folder.glob("candidate-*.json")):
        original = json.loads(path.read_text())
        result = evaluate(SavedPredictions(original["details"]), records, [None] * len(records))
        for key in (
            "candidate",
            "weights_sha256",
            "poller",
            "mean_ms",
            "p95_ms",
            "player_reported_frames",
            "player_reported_fraction",
            "removed_player_detections",
            "collateral_removed",
        ):
            result[key] = original[key]
        result["labels_sha256"] = hashlib.sha256(labels.read_bytes()).hexdigest()
        result["rescored"] = (
            "Saved filtered predictions; original runtime and player-filter measurements retained."
        )
        path.write_text(json.dumps(result, indent=2) + "\n")
        summary = {
            key: value
            for key, value in result.items()
            if key not in ("details", "per_kind", "large_per_kind", "collateral_removed")
        }
        summary["selection_score"] = (
            sum(g["recall"] for g in result["groups"].values()) + 1 - result["invented_fraction"]
        ) / 4
        summaries.append(summary)
    summaries.sort(key=lambda r: r["selection_score"], reverse=True)
    (folder / "candidates.json").write_text(json.dumps(summaries, indent=2) + "\n")
    print(
        json.dumps(
            [
                {k: r[k] for k in ("candidate", "selection_score", "groups", "invented_fraction", "poller")}
                for r in summaries[:5]
            ],
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
