"""Compare the frozen visual truth and the existing judge proxy with section output."""

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
AFTERNOON = ("20261111-164039", "20261111-165543", "20261111-171046", "20261111-172549")
SOURCES = {"kerim": "20261111-065022", "wifi": "20261110-093238", "pilot": "20261110-231512"}


def overlap(a, b):
    return max(0, min(a["end"], b["end"]) - max(a["start"], b["start"]))


def compare(predicted, truth):
    known = [(i, part) for i, part in enumerate(truth) if part["kind"] != "unknown"]
    candidates = sorted(
        (
            (overlap(p, t), pi, ti)
            for pi, p in enumerate(predicted)
            for ti, t in known
            if p["kind"] == t["kind"] and overlap(p, t) > 0
        ),
        reverse=True,
    )
    matches, used = {}, set()
    for _, pi, ti in candidates:
        if ti not in matches and pi not in used:
            matches[ti] = pi
            used.add(pi)
    eligible = [ti for ti, part in known if part["end"] - part["start"] >= 3]
    found = [
        ti
        for ti in eligible
        if ti in matches
        and overlap(predicted[matches[ti]], truth[ti]) >= (truth[ti]["end"] - truth[ti]["start"]) / 2
    ]
    bounded = [
        ti
        for ti in found
        if max(abs(predicted[matches[ti]][edge] - truth[ti][edge]) for edge in ("start", "end")) <= 2
    ]
    false = [
        pi
        for pi, part in enumerate(predicted)
        if pi not in used
        and part["kind"] != "unknown"
        and sum(overlap(part, t) for _, t in known) >= (part["end"] - part["start"]) / 2
    ]
    unknown_seconds = sum(overlap(p, t) for p in predicted if p["kind"] == "unknown" for _, t in known)
    return {
        "true_sections_ge_3s": len(eligible),
        "kind_found": len(found),
        "kind_and_bounds_within_2s": len(bounded),
        "false_sections": len(false),
        "false_per_5_minutes": len(false) * 300 / (truth[-1]["end"] - truth[0]["start"]),
        "unknown_seconds_on_known_truth": unknown_seconds,
        "matches": {str(ti): pi for ti, pi in matches.items()},
        "false_indices": false,
    }


def main():
    outputs = {
        p.parent.name: json.loads(p.read_text()) for p in sorted((HERE / "out").glob("*/sections.json"))
    }
    initial_truth = json.loads((HERE / "truth.json").read_text())["recordings"]
    truth = json.loads((HERE / "truth-audited.json").read_text())["recordings"]
    metrics = {"recordings": {}, "judge": {}, "afternoon_minutes": {}, "timing": {}}
    metrics["initial_truth_recordings"] = {
        name: compare(outputs[name]["sections"], parts) for name, parts in initial_truth.items()
    }
    for name, parts in truth.items():
        metrics["recordings"][name] = compare(outputs[name]["sections"], parts)
    judge_truth = json.loads((ROOT / "lab/judge/truth.json").read_text())
    sample = json.loads((ROOT / "lab/judge/sample.json").read_text())
    clocks = {
        source: [
            json.loads(line)["t"]
            for line in (Path(outputs[name]["recording"]) / "frames.jsonl").read_text().splitlines()
        ]
        for source, name in SOURCES.items()
    }
    details = []
    for item in sample:
        if item["source"] not in SOURCES or item["name"] in judge_truth["unclear"]:
            continue
        name = SOURCES[item["source"]]
        timestamp = clocks[item["source"]][item["frame"]]
        expected = (
            "foot"
            if item["name"] in judge_truth["foot"]
            else {"vehicle": "drive", "dead_or_failed": "banner"}.get(item["situation"], item["situation"])
        )
        predicted = next(
            (p["kind"] for p in outputs[name]["sections"] if p["start"] <= timestamp <= p["end"]), "unknown"
        )
        details.append(
            {
                "name": item["name"],
                "recording": name,
                "frame": item["frame"],
                "time": timestamp,
                "expected": expected,
                "predicted": predicted,
                "correct": expected == predicted,
            }
        )
    for name in (*SOURCES.values(), "total"):
        group = [row for row in details if name == "total" or row["recording"] == name]
        metrics["judge"][name] = {
            "count": len(group),
            "correct": sum(row["correct"] for row in group),
            "unknown": sum(row["predicted"] == "unknown" for row in group),
            "agreement": sum(row["correct"] for row in group) / len(group),
        }
    totals = Counter()
    for name in AFTERNOON:
        for part in outputs[name]["sections"]:
            totals[part["kind"]] += (part["end"] - part["start"]) / 60
    metrics["afternoon_minutes"] = dict(totals)
    metrics["afternoon_metadata_minutes"] = sum(outputs[name]["seconds"] for name in AFTERNOON) / 60
    for line in (HERE / "timing.txt").read_text().splitlines():
        match = re.match(r"(\d+-\d+): (\d+) sections; ([\d.]+)s; ([\d.]+)s/recording-minute", line)
        if match:
            name, count, elapsed, rate = match.groups()
            metrics["timing"][name] = {
                "sections": int(count),
                "elapsed": float(elapsed),
                "seconds_per_minute": float(rate),
            }
    (HERE / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    (HERE / "judge-comparison.json").write_text(json.dumps(details, indent=2) + "\n")
    text = [
        "P38 adds an offline recording section reader, a command, deterministic reader-sequence tests and reproducible evaluation artifacts. It reads the existing minimap and HUD readers at 10 Hz on frames.jsonl timestamps. It never instantiates Pipeline, starts OCR or connects to a console. The decision callable accepts a Sample including frame index, source time, wanted level, minimap and aligned human pad, so a later judge can replace it without changing segmentation.",
        "The original truth in lab/sections/truth.json was frozen before the first section run and is preserved unchanged. A later visual audit found missed short overlays, scripted HUD-free animations and source-gap timing errors. The tables below use the explicitly post-run correction in truth-audited.json; initial scores are retained in metrics.json under initial_truth_recordings. No classifier threshold was tuned against either version. Every distinct nearest frame on the one-second contact sheets was visually reviewed, using printed capture timestamps. There are 886 distinct frames for the 901-second afternoon sample and 693 for the 695-second Wi-Fi sample; multiple target seconds can point to the same source frame across gaps. Boundaries have approximately one-second uncertainty. System overlays and unreadable transitions were labelled unknown. The first car entry was placed at 330 seconds, when the player is seated, rather than at the door-opening animation.",
        "Segmentation requires a second of stable clean evidence. A damaged sample cannot call the decision function, advance a boundary, contribute wanted/route/speed, or confirm a change across a long gap. Short unconfirmed changes keep the preceding section. Adjacent equal kinds merge. Sections use half-open intervals except the final source frame. Human activity integrates held human controller events over the exact interval; no human events or a single event means picture-only. Menu screen is the most frequent clean reader screen within a section.",
        "The pixel readers cannot establish that absent minimap means a cutscene, so that case stays unknown. A later judge can emit cutscene. Tilt with wanted stars needs controller evidence; tilt without stars retains the existing geometric vehicle cue. This can still confuse stationary cars, brief entry/exit states, and unusual camera angles. Pad and picture are not latency-corrected; the Wi-Fi source can lag controller events. GPS speed remains null because the current speed reader requires forbidden OCR. The schema accepts injected GPS speed, tested with synthetic reader output. Route share is the fraction of clean sampled drive readings that have a route; damaged is the fraction of all sampled readings marked corrupt.",
        "Against the original pre-run truth, 164039 found 10/13 kinds, 5/13 with both boundaries within two seconds, and 9 false sections (3.00 per five minutes). Wi-Fi found 14/18 kinds, 3/18 with both boundaries within two seconds, and 7 false sections (3.02 per five minutes). The later correction is reported separately below rather than silently replacing these initial results.",
        "Evaluation uses one-to-one same-kind matches by largest temporal overlap. Kind found requires at least half the true interval covered; the strict target additionally requires both boundaries within two seconds. True unknown intervals are excluded from accuracy and false-section scoring. Extra known predictions overlapping known truth by at least half their duration count as false sections, including fragmentation. Unknown predictions count as missed coverage and are reported separately.",
        "| Recording | True >=3s | Kind found | Kind and ends <=2s | False sections | False /5min | Unknown on known truth (s) |\n|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, metric in metrics["recordings"].items():
        text.append(
            f"| {name} | {metric['true_sections_ge_3s']} | {metric['kind_found']} | {metric['kind_and_bounds_within_2s']} | {metric['false_sections']} | {metric['false_per_5_minutes']:.2f} | {metric['unknown_seconds_on_known_truth']:.1f} |"
        )
    text.extend(
        [
            "",
            "The target is every true section of at least three seconds with both boundaries within two seconds, and at most one false section per five minutes. Any row below full recall or above 1.00 false sections per five minutes fails that target.",
            "The existing judge truth corrects movement labels only; other labels are inherited from sample.json. This is a partially hand-corrected proxy, not independent complete truth for cutscenes, banners or menus. Unclear frames are excluded. Unknown predictions count as misses. None of the four afternoon recordings or the stationary-car recording appears in that existing sample.",
            "| Judge recording | Correct / eligible | Agreement | Unknown misses |\n|---|---:|---:|---:|",
        ]
    )
    for name, metric in metrics["judge"].items():
        text.append(
            f"| {name} | {metric['correct']}/{metric['count']} | {metric['agreement']:.1%} | {metric['unknown']} |"
        )
    text.extend(
        [
            "",
            f"The judge target is 90%; measured aggregate agreement is {metrics['judge']['total']['agreement']:.1%}.",
            f"The four afternoon recordings total {metrics['afternoon_metadata_minutes']:.2f} metadata minutes. The section clock accounts for {sum(totals.values()):.2f} minutes; recording setup/tail time outside frame timestamps is not invented.",
            "| Kind | Afternoon minutes |\n|---|---:|",
        ]
    )
    for kind in ("drive", "foot", "cutscene", "menu", "banner", "loading", "unknown"):
        text.append(f"| {kind} | {totals[kind]:.2f} |")
    text.extend(
        [
            "",
            "Timing includes decoding, readers, JSON and midpoint contact sheet output in one process. The performance limit is 10 seconds per recording minute, equivalent to ten minutes per hour. The full gate ran concurrently, so this is an observed end-to-end run under that load.",
            "| Recording | Metadata seconds | Has human pad | Sections | Runtime seconds | Seconds / recording minute |\n|---|---:|---|---:|---:|---:|",
        ]
    )
    for name, output in outputs.items():
        timing = metrics["timing"].get(name, {})
        text.append(
            f"| {name} | {output['seconds']} | {output['has_pad']} | {len(output['sections'])} | {timing.get('elapsed', 'pending')} | {timing.get('seconds_per_minute', 'pending')} |"
        )
    for name, output in outputs.items():
        text.extend(
            [
                "",
                f"Sections for {name}. The full contract and labelled midpoint sheet are in lab/sections/out/{name}/.",
                "| Start | End | Kind | Screen | Wanted | Route | Damaged | Human | Route share | Speed m/s |\n|---:|---:|---|---|---:|---|---:|---:|---:|---:|",
            ]
        )
        for part in output["sections"]:

            def number(value):
                return "null" if value is None else f"{value:.3f}"

            text.append(
                f"| {part['start']:.2f} | {part['end']:.2f} | {part['kind']} | {part['screen']} | {part['wanted']} | {', '.join(part['route']) or 'none'} | {part['damaged']:.3f} | {number(part['human'])} | {number(part['route_share'])} | {number(part['speed'])} |"
            )
        if name in truth:
            text.extend(
                [
                    "",
                    "Audited visual truth beside its best same-kind predicted interval. Missing matches remain explicit; mismatched kinds are visible in the complete table above.",
                    "| True start | True end | True kind | Predicted start | Predicted end | Boundary errors (s) |\n|---:|---:|---|---:|---:|---|",
                ]
            )
            matches = metrics["recordings"][name]["matches"]
            for index, part in enumerate(truth[name]):
                predicted = output["sections"][matches[str(index)]] if str(index) in matches else None
                tail = (
                    f"{predicted['start']:.2f} | {predicted['end']:.2f} | {abs(predicted['start'] - part['start']):.2f}, {abs(predicted['end'] - part['end']):.2f}"
                    if predicted
                    else "missing | missing | not scored"
                    if part["kind"] == "unknown"
                    else "missing | missing | missed"
                )
                text.append(f"| {part['start']:.2f} | {part['end']:.2f} | {part['kind']} | {tail} |")
    (HERE / "report-tables.md").write_text("\n\n".join(text[:6]) + "\n\n" + "\n".join(text[6:]) + "\n")
    print(json.dumps({k: v for k, v in metrics.items() if k != "recordings"}, indent=2))


if __name__ == "__main__":
    main()
