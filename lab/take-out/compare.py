"""Old against new rules on every objective step P39 reconstructed from Kerim's recordings.

Copies the recorded requests into cases.json beside this script, so the tests keep them once the
P39 worktree is gone, then decides each with the rules of fc82d78 and with the current ones.
"""

import importlib.util
import json
import subprocess
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from pilot.head import HeadRequest
from pilot.mission import MissionHead

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
P39 = Path("/Users/kerim/Documents/ChatGPT/gta-worktrees/p39-notes/lab/notes/out")
BASE = "fc82d78"


def old_rules():
    source = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{BASE}:pilot/src/pilot/mission.py"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    spec = importlib.util.spec_from_loader("pilot._mission_before", loader=None)
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "pilot"
    exec(compile(source, f"{BASE}:mission.py", "exec"), module.__dict__)
    return module.MissionHead


def collect(out):
    cases = []
    for path in sorted(out.glob("*/cases.json")):
        for case in json.loads(path.read_text()):
            cases.append(
                {
                    "recording": path.parent.name,
                    "step": case["objective"],
                    "sample_t": case["sample_t"],
                    "frame": case["frame"],
                    "p39_rule": case["rule"],
                    "request": case["request"],
                }
            )
    return cases


def decide(head_class, request):
    head = head_class()
    answer = head.decide(HeadRequest(**deepcopy(request)))
    return head.last_rule, answer.plan[0].name


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else P39
    cases = collect(out)
    (ROOT / "cases.json").write_text(json.dumps(cases, indent=1, ensure_ascii=False) + "\n")
    before = old_rules()
    rows = []
    for case in cases:
        old_rule, old_skill = decide(before, case["request"])
        assert old_rule == case["p39_rule"], (case["recording"], case["sample_t"], old_rule)
        new_rule, new_skill = decide(MissionHead, case["request"])
        # Where the reconstructed request holds no objective, what the step's own objective would change.
        stepped = None
        if not case["request"]["objective"].strip():
            request = HeadRequest(**deepcopy(case["request"]))
            head = MissionHead()
            answer = head.decide(replace(request, objective=case["step"]))
            stepped = f"{answer.plan[0].name} ({head.last_rule})"
        rows.append(
            {
                "recording": case["recording"],
                "time": round(case["sample_t"], 3),
                "step": case["step"],
                "objective": case["request"]["objective"],
                "red": sum(
                    1 for blip in case["request"]["minimap"].get("blips", []) if blip["color"] == "red"
                ),
                "old": f"{old_skill} ({old_rule})",
                "new": f"{new_skill} ({new_rule})",
                "with_step_objective": stepped,
            }
        )
    (ROOT / "comparison.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n")
    print(
        "| Recording | Time | Step objective | Objective in request | Red | Old | New | New, step objective |"
    )
    print("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for row in rows:
        print(
            f"| {row['recording']} | {row['time']:.3f} | {row['step']} | {row['objective'] or '(none)'} "
            f"| {row['red']} | {row['old']} | {row['new']} | {row['with_step_objective'] or ''} |"
        )


if __name__ == "__main__":
    main()
