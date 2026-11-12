"""Score the sections with and without the judge on the two hand-labelled recordings.

The reader-only sections are kept in readers/, the judged ones are in out/ (the afternoon one) and
judged/ (the Wi-Fi one). Writes judge-metrics.json and judge-tables.md.
"""

import json
from collections import Counter
from pathlib import Path

from evaluate import compare

HERE = Path(__file__).resolve().parent
RUNS = {"20261111-164039": "out", "20261110-093238": "judged"}


def minutes(sections):
    totals = Counter()
    for part in sections:
        totals[part["kind"]] += (part["end"] - part["start"]) / 60
    return totals


def main():
    truth = json.loads((HERE / "truth-audited.json").read_text())["recordings"]
    metrics, text = {}, []
    header = (
        "| Recording | Pass | True >=3s | Kind found | Kind and ends <=2s | False sections | False /5min "
        "| Unknown on known truth (s) | Unknown minutes |\\n|---|---|---:|---:|---:|---:|---:|---:|---:|"
    ).replace("\\n", "\n")
    text.append(header)
    for name, folder in RUNS.items():
        metrics[name] = {}
        for label, path in (("readers", HERE / "readers" / name), ("judge", HERE / folder / name)):
            sections = json.loads((path / "sections.json").read_text())["sections"]
            result = compare(sections, truth[name])
            result.pop("matches")
            result.pop("false_indices")
            result["minutes"] = dict(minutes(sections))
            metrics[name][label] = result
            text.append(
                f"| {name} | {label} | {result['true_sections_ge_3s']} | {result['kind_found']} "
                f"| {result['kind_and_bounds_within_2s']} | {result['false_sections']} "
                f"| {result['false_per_5_minutes']:.2f} | {result['unknown_seconds_on_known_truth']:.1f} "
                f"| {result['minutes'].get('unknown', 0):.2f} |"
            )
    (HERE / "judge-metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    (HERE / "judge-tables.md").write_text("\n".join(text) + "\n")
    print("\n".join(text))


if __name__ == "__main__":
    main()
