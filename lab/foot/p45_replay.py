"""Offline P45 rule comparison using the requests produced by the real readers.

Run from the repository root with pilot/.venv/bin/python lab/foot/p45_replay.py.
The baseline is pinned to the original task commit; no console or model is called.
"""

import json
import subprocess
import sys
import types
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

BASELINE = "c76c5d2ffcc8f9b0fa0a761b142b00bb767cfa64"
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot" / "src"))
from pilot.head import HeadRequest
from pilot.mission import MissionHead


def baseline():
    module = types.ModuleType("pilot.p45_before")
    module.__package__ = "pilot"
    sys.modules[module.__name__] = module
    source = subprocess.check_output(
        ["git", "show", f"{BASELINE}:pilot/src/pilot/mission.py"], cwd=ROOT, text=True
    )
    # Execute only the pinned local Git source for an offline behavioral comparison.
    exec(compile(source, "baseline/mission.py", "exec"), module.__dict__)
    return module.MissionHead


def decide(head, request):
    answer = head.decide(HeadRequest(**deepcopy(request)))
    return {"rule": head.last_rule, "plan": asdict(answer)["plan"]}


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main():
    old_head = baseline()
    corpus = []
    for name in ("saved_cases", "frame_cases", "extra_cases"):
        for case in json.loads((ROOT / "lab/mission" / f"{name}.json").read_text()):
            corpus.append(("mission", case["id"], case["request"]))
    for case in json.loads((ROOT / "lab/take-out/cases.json").read_text()):
        corpus.append(
            ("take-out", f"{case['recording']}-{case['sample_t']:.3f}", case["request"])
        )
    diffs = []
    for suite, case_id, request in corpus:
        before, after = decide(old_head(), request), decide(MissionHead(), request)
        if before != after:
            diffs.append(
                {
                    "suite": suite,
                    "id": case_id,
                    "request": request,
                    "before": before,
                    "after": after,
                }
            )

    sessions = []
    blue_ticks = []
    for name in ("20261111-204712", "20261112-082524"):
        recording = Path("/Users/kerim/recordings/pilot") / name
        heads = records(recording / "head.jsonl")
        play = records(recording / "play.jsonl")
        origin = heads[0]["t"] - play[0]["t"]
        responses = {r["id"]: r for r in heads if r.get("type") == "response"}
        before_head, after_head = old_head(), MissionHead()
        requests = []
        for row in heads:
            if row.get("type") != "request":
                continue
            request = row["request"]
            requests.append(
                {
                    "id": row["id"],
                    "t": round(row["t"] - origin, 3),
                    "request": request,
                    "recorded": responses.get(row["id"], {}).get("plan"),
                    "before": decide(before_head, request),
                    "after": decide(after_head, request),
                }
            )
        sessions.append({"recording": name, "requests": requests})
        for row in play:
            if not row.get("fresh") or not row.get("reading"):
                continue
            blue = [b for b in row["reading"].get("blips", []) if b["color"] == "blue"]
            if blue:
                blue_ticks.append(
                    {
                        "recording": name,
                        "t": round(row["t"], 3),
                        "frame_id": row["frame_id"],
                        "blue": blue,
                    }
                )
    summary = {
        "baseline": subprocess.check_output(
            ["git", "rev-parse", BASELINE], cwd=ROOT, text=True
        ).strip(),
        "corpus_counts": {
            suite: sum(row[0] == suite for row in corpus)
            for suite in ("mission", "take-out")
        },
        "changes": diffs,
        "sessions": sessions,
    }
    out = ROOT / "lab/foot"
    (out / "p45-decisions.json").write_text(json.dumps(summary, indent=2) + "\n")
    (out / "p45-blue-ticks.json").write_text(
        json.dumps(blue_ticks, separators=(",", ":")) + "\n"
    )
    print(
        json.dumps(
            {
                "corpus_counts": summary["corpus_counts"],
                "changes": [
                    {
                        "suite": d["suite"],
                        "id": d["id"],
                        "before": d["before"],
                        "after": d["after"],
                    }
                    for d in diffs
                ],
            },
            indent=2,
        )
    )
    for session in sessions:
        for row in session["requests"]:
            vehicles = [
                o["kind"]
                for o in row["request"].get("objects", [])
                if o["kind"] in {"car", "truck", "motorcycle"}
            ]
            print(
                session["recording"],
                row["id"],
                row["t"],
                row["before"]["rule"],
                "->",
                row["after"]["rule"],
                vehicles,
            )


if __name__ == "__main__":
    main()
