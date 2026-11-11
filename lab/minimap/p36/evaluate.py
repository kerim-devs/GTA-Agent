"""Audit the manual town labels and every previously labelled damaged crop."""
import argparse
import csv
import json
from pathlib import Path

import numpy as np

from before import ROOT, module as before
from pilot import minimap as after

HERE = Path(__file__).parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crops", type=Path, default=ROOT / "lab/minimap/data/crops.npy")
    args = parser.parse_args()
    labels = json.loads((HERE / "frames.json").read_text())
    results = {}
    for phase in ("before", "after"):
        with (HERE / f"20261111-130955-{phase}.csv").open() as stream:
            frames = {int(r["frame_id"]): r for r in csv.DictReader(stream)}
        for name, sample in (("named_stretches", [r for r in labels if 80 <= r["sample_t"] < 110 or 150 <= r["sample_t"] < 180]), ("all_manual", labels)):
            wrong = [r["sample_t"] for r in sample if bool(int(frames[r["frame_id"]]["corrupt"])) != r["corrupt"]]
            results[f"{name}_{phase}"] = {"n": len(sample), "correct": len(sample) - len(wrong), "false_positive_times": wrong}
        results[f"stretches_{phase}"] = {
            f"{start}-{end}": {"n": len(subset), "corrupt": sum(int(r["corrupt"]) for r in subset)}
            for start, end in ((20, 50), (80, 110), (150, 180))
            for subset in [[r for r in frames.values() if start <= float(r["t"]) < end]]
        }
    data = ROOT / "lab/minimap/data"
    golden = {r["id"]: r for r in json.loads((data / "golden.json").read_text())}
    damaged = [golden[r["id"]]["k"] for p in sorted((data / "labels").glob("G*.json"))
               for r in json.loads(p.read_text()) if r["corrupt"]]
    crops = np.load(args.crops, mmap_mode="r")
    misses = [k for k in damaged if not before.read(crops[k]).corrupt]
    lost = [k for k in damaged if before.read(crops[k]).corrupt and not after.read(crops[k]).corrupt]
    assert not lost, f"Previously detected damage became clean: {lost}"
    results["old_damage"] = {"labelled": len(damaged), "detected_before": len(damaged) - len(misses), "detected_after": sum(after.read(crops[k]).corrupt for k in damaged), "baseline_misses": misses, "new_misses": lost}
    demoted = []
    changed = []
    for k, crop in enumerate(crops):
        old, new = before.read(crop), after.read(crop)
        if old != new:
            changed.append(k)
        if old.corrupt and not new.corrupt:
            demoted.append({"k": k, "before_blocks": before._debug(crop)["blocks"], "after_blocks": after._debug(crop)["blocks"]})
    (HERE / "old-demoted.json").write_text(json.dumps(demoted, indent=2) + "\n")
    results["old_corpus_demoted"] = [r["k"] for r in demoted]
    results["old_readings_changed"] = changed
    assert not demoted, f"Old corpus alarms lost: {demoted}"
    assert not changed, f"Old corpus readings changed: {changed}"
    (HERE / "audit.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
