"""Render evidence tables from completed P78 receipts, without decoding videos again."""

import gzip
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "lab/pursuit"


def median(values):
    return f"{statistics.median(values):.1f}" if values else "unavailable"


def classification(row):
    text, rec = row["objective"].lower(), row["rec"]
    if rec == "20261110-093238":
        return "historical chase, no objective label"
    if "yacht" in text or "lieferwagen" in text or "lleferwagen" in text or "l_ieferwagen" in text:
        if "steig" not in text:
            return "pursuit/reach evidence"
    if "biker" in text:
        return "catch with combat"
    return "boundary: " + ("low vehicle coverage" if (row["driving_s"] or 0) < 10 else "mixed context")


def main():
    inventory = json.loads((OUT / "inventory.json").read_text())
    summaries = [row for path in sorted(OUT.glob("summary-*.json")) for row in json.loads(path.read_text())]
    detailed = {}
    for path in OUT.glob("replay-*.jsonl.gz"):
        rec = path.name.removeprefix("replay-").removesuffix(".jsonl.gz")
        with gzip.open(path, "rt") as stream:
            for line in stream:
                block = json.loads(line)
                detailed[(rec, block["start"])] = block["rows"]
    header = (
        "| Recording / seconds | Objective (OCR) and context | Color; marker px p10/median/p90; rim | "
        "R2 / L2 mean; radar motion gas/coast | Ending in labels; replay end | Clear turns same/compared |"
    )
    table = [header, "| --- | --- | --- | --- | --- | --- |"]
    for row in inventory:
        summary = next((s for s in summaries if s["rec"] == row["rec"] and s["start"] == row["start"]), None)
        base = f"{row['rec']}<br>{row['start']:.3f}-{row['end']:.3f} ({row['end'] - row['start']:.1f}s)"
        context = classification(row)
        if summary is None:
            table.append(
                f"| {base} | {row['objective']} ({context}) | pending | pending | {row['ending']} | pending |"
            )
            continue
        percentiles = summary["distance_percentiles"]
        distances = "/".join(f"{percentiles[i]:.1f}" for i in (1, 2, 3)) if percentiles else "not read"
        ticks = detailed[(row["rec"], row["start"])]
        moving_gas = [r["move"] for r in ticks if r["move"] is not None and r["r2"] >= 0.9]
        moving_coast = [r["move"] for r in ticks if r["move"] is not None and r["r2"] <= 0.1]
        terminal = summary["terminal"]
        ending = f"{terminal['reason']} at {terminal['t']:.2f}s" if terminal else "still running"
        table.append(
            f"| {base} | {row['objective']} ({context}) | "
            f"{row['color']}; {distances}; {summary['rim_share']:.0%} | "
            f"{summary['r2_mean']:.2f}/{summary['l2_mean']:.2f}; "
            f"{median(moving_gas)}/{median(moving_coast)} px/s | "
            f"{row['ending']}; {ending} | {summary['same']}/{summary['compared']} |"
        )
    (OUT / "human-table.md").write_text("\n".join(table) + "\n")
    for label, selected in (
        (
            "objective-qualified pursuit/reach",
            [s for s in summaries if classification(s) in ("pursuit/reach evidence", "catch with combat")],
        ),
        ("all candidates", summaries),
    ):
        same = sum(s["same"] for s in selected)
        compared = sum(s["compared"] for s in selected)
        print(
            f"{label}: {same}/{compared} = {same / compared:.4f}"
            if compared
            else f"{label}: no comparable turns"
        )
        print(
            f"  human-clear={sum(s['human_clear'] for s in selected)}, "
            f"all-clear-same={sum(s['all_clear_same'] for s in selected)}, "
            f"eligible={sum(s['eligible'] for s in selected)}/{sum(s['frames'] for s in selected)} frames"
        )
    print(f"completed summaries: {len(summaries)}/{len(inventory)}")


if __name__ == "__main__":
    main()
