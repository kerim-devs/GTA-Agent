"""P104's bounded recording audit. Run with pilot/.venv/bin/python, at nice 15."""

import argparse
import json
import subprocess
import sys
import types
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np

from pilot import gps
from pilot.replay import hud_crop

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "lab/gps"
RECORDINGS = Path("/Users/kerim/recordings/pilot")
SESSIONS = ("024431", "015901")


def original():
    name = "pilot.p104_original"
    module = types.ModuleType(name)
    module.__package__ = "pilot"
    sys.modules[name] = module
    source = subprocess.check_output(
        ["git", "show", "HEAD:pilot/src/pilot/gps.py"], cwd=ROOT, text=True
    )
    exec(compile(source, "baseline-gps.py", "exec"), module.__dict__)
    return module


def load(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def dump(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def trace(module, crop):
    texts = []
    parse = module.parse

    def capture(values):
        values = list(values)
        texts.append(values)
        return parse(values)

    module.parse = capture
    start = perf_counter()
    try:
        fix = module.recognize(crop)
    finally:
        module.parse = parse
    return {
        "value": None if fix is None else fix.distance,
        "quantum": None if fix is None else fix.quantum,
        "texts": texts,
        "ms": round(1000 * (perf_counter() - start), 3),
    }


def collect():
    gaps, labels = [], []
    label_path = OUT / "p104-labels.jsonl"
    existing = {r["crop"]: r for r in load(label_path)} if label_path.exists() else {}
    for session in SESSIONS:
        directory = RECORDINGS / ("20261114-" + session)
        rows = load(directory / "play.jsonl")
        frames = load(directory / "frames.jsonl")
        times = np.array([r["t"] for r in frames])
        selections = []
        start = None
        for index, row in enumerate(rows + [{}]):
            bad = (row.get("skill") or {}).get("name") == "drive_route" and (
                row.get("reading") or {}
            ).get("gps_distance") is None
            if bad and start is None:
                start = index
            if start is not None and not bad:
                part = rows[start:index]
                end = rows[min(index, len(rows) - 1)]["t"]
                middle = (part[0]["t"] + end) / 2
                gap = dict(session=session, start=part[0]["t"], end=end, ticks=len(part))
                selections.append((middle, "gap", len(gaps)))
                gaps.append(gap)
                start = None
        # Named hard cases and evenly spaced controls, selected before changing OCR.
        extra = [32, 38, 44, 52, 68, 74, 118, 132, 191, 199] if session == "024431" else []
        extra += list(range(35 if session == "015901" else 15, 365 if session == "015901" else 220, 15))
        selections += [(t, "control", None) for t in extra]
        cap = cv2.VideoCapture(str(directory / "video.mp4"))
        for wanted, kind, gap_index in sorted(selections):
            i = int(np.argmin(abs(times - wanted)))
            cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            ok, bgr = cap.read()
            if not ok:
                raise RuntimeError((session, i))
            crop = hud_crop(bgr)
            name = f"p104-{session}-{i:05}.png"
            cv2.imwrite(str(OUT / name), cv2.cvtColor(crop, cv2.COLOR_RGB2BGR))
            label = dict(session=session, t=frames[i]["t"], frame=i, crop=name, kind=kind)
            for key in ("value", "label_source", "background"):
                if key in existing.get(name, {}):
                    label[key] = existing[name][key]
            if gap_index is not None:
                gaps[gap_index]["crop"] = name
            labels.append(label)
        cap.release()
    dump(OUT / "p104-gaps.jsonl", gaps)
    dump(OUT / "p104-labels.jsonl", labels)
    for session in SESSIONS:
        selected = [r for r in labels if r["session"] == session]
        for page in range((len(selected) + 23) // 24):
            batch = selected[page * 24 : (page + 1) * 24]
            sheet = np.zeros((len(batch) * 64, 520, 3), np.uint8)
            for j, row in enumerate(batch):
                crop = cv2.imread(str(OUT / row["crop"]))
                patch = cv2.resize(crop[114:146, 28:130], (204, 64), interpolation=cv2.INTER_NEAREST)
                sheet[j * 64 : (j + 1) * 64, :204] = patch
                cv2.putText(sheet, f'{row["frame"]:05}  {row["t"]:.2f}s', (215, j * 64 + 30),
                            cv2.FONT_HERSHEY_SIMPLEX, .55, (255,255,255), 1)
            cv2.imwrite(str(OUT / f"p104-sheet-{session}-{page}.png"), sheet)
    print(f"Collected {len(gaps)} gaps and {len(labels)} labelled-frame candidates", flush=True)


def bench():
    baseline = original()
    rows = []
    for label in load(OUT / "p104-labels.jsonl"):
        crop = cv2.cvtColor(cv2.imread(str(OUT / label["crop"])), cv2.COLOR_BGR2RGB)
        row = dict(label, before=trace(baseline, crop), after=trace(gps, crop))
        rows.append(row)
    dump(OUT / "p104-bench.jsonl", rows)
    for name in ("before", "after"):
        judged = [r for r in rows if "value" in r]
        print(name, "total", len(judged), "correct", sum(r[name]["value"] == r["value"] and r["value"] is not None for r in judged),
              "wrong", sum(r[name]["value"] is not None and r[name]["value"] != r["value"] for r in judged),
              "ms p50/p95", np.percentile([r[name]["ms"] for r in rows], [50,95]).round(2).tolist(), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("collect", "bench"))
    args = parser.parse_args()
    globals()[args.mode]()
