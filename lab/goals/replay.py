"""P51 frozen-rule comparison and ordered four-session head replay; no model or console."""

import hashlib
import json
import subprocess
import sys
import types
from collections import Counter
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot/src"))
from pilot.head import HeadRequest, parse_response, response_data
from pilot.mission import MissionHead

BASELINE = "b396957"
SEED = 51
INPUTS = {}


def read(path, jsonl=False):
    raw = path.read_bytes()
    INPUTS[str(path)] = hashlib.sha256(raw).hexdigest()
    return [json.loads(line) for line in raw.splitlines() if line.strip()] if jsonl else json.loads(raw)


def baseline():
    module = types.ModuleType("pilot._p51_baseline")
    module.__package__ = "pilot"
    source = subprocess.check_output(["git", "show", f"{BASELINE}:pilot/src/pilot/mission.py"], cwd=ROOT, text=True)
    exec(compile(source, "baseline/mission.py", "exec"), module.__dict__)
    return module.MissionHead


class Fallback:
    def __init__(self, model=None):
        self.answer = parse_response(model or {"plan": [{"name": "wait", "args": {"duration": 1}}], "sentence": "Recorded fallback."})

    def decide(self, request):
        return self.answer


def decide(head, request):
    result = response_data(head.decide(HeadRequest(**deepcopy(request))))
    return {"rule": head.last_rule, **result}


def reason(after):
    if after["goal"]:
        return f"No screen objective: {after['goal']['name']} now owns the free-roam plan; {after['reason']}."
    if any({"kind", "place"} & set(call["args"]) for call in after["plan"]):
        return "No screen objective: the rules' trip asks the legend for a place, not for a point on the map."
    return after["reason"]


def behavior(result):
    return {key: result[key] for key in ("rule", "plan", "action")}


def main():
    old = baseline()
    corpus = []
    for name in ("saved_cases", "frame_cases", "extra_cases"):
        for case in read(ROOT / "lab/mission" / f"{name}.json"):
            corpus.append(("mission", case["id"], case["request"], case.get("model")))
    for i, case in enumerate(read(ROOT / "lab/take-out/cases.json")):
        corpus.append(("take-out", f"{case['recording']}:{case.get('sample_t', i)}", case["request"], None))
    p45 = read(ROOT / "lab/foot/p45-decisions.json")
    for i, case in enumerate(p45["changes"]):
        corpus.append(("p45-changes", str(case.get("id", i)), case["request"], None))
    for session in p45["sessions"]:
        for row in session["requests"]:
            corpus.append(("p45-sessions", f"{session['recording']}:{row['id']}", row["request"], None))
    changed, objective_changes = [], []
    for suite, ident, raw, model in corpus:
        request = {**raw, "time": 0}
        before = decide(old(Fallback(model)), request)
        after = decide(MissionHead(Fallback(model), goal_seed=SEED), request)
        if behavior(before) == behavior(after):
            continue
        row = {"suite": suite, "id": ident, "request": request, "before": before, "after": after,
               "reason": reason(after)}
        changed.append(row)
        if request["objective"].strip():
            objective_changes.append(row)
    sessions = []
    for name in ("20261112-102851", "20261112-103305", "20261112-100318", "20261112-100713"):
        root = Path("/Users/kerim/recordings/pilot") / name
        heads, play = read(root / "head.jsonl", True), read(root / "play.jsonl", True)
        origin = heads[0]["t"] - play[0]["t"]
        before_head, after_head = old(), MissionHead(goal_seed=SEED)
        rows = []
        for row in heads:
            if row.get("type") != "request":
                continue
            request = {**row["request"], "time": round(row["t"] - origin, 3)}
            before, after = decide(before_head, request), decide(after_head, request)
            append = any(e.get("kind") == "plan_ending" for e in request["events"])
            rows.append({"id": row["id"], "t": request["time"], "request": request,
                         "before": before, "after": after,
                         "before_disposition": "appended" if append else "replaced",
                         "after_disposition": "kept" if after["action"] == "go_on" else ("replaced" if after["goal"] or not append else "appended")})
        sessions.append({"recording": name, "seed": SEED, "requests": rows,
                         "before": dict(Counter(r["before_disposition"] for r in rows)),
                         "after": dict(Counter(r["after_disposition"] for r in rows)),
                         "recorded_applied": dict(Counter(r.get("disposition", "unspecified") for r in heads if r.get("type") == "response" and r.get("applied"))),
                         "timeline": after_head.goals.history})
    output = {"baseline": BASELINE, "seed": SEED, "source_sha256": INPUTS,
              "corpus_counts": dict(Counter(row[0] for row in corpus)),
              "objective_cases": sum(bool(row[2]["objective"].strip()) for row in corpus),
              "objective_changes": objective_changes, "changes": changed, "sessions": sessions,
              "limits": "Replays reuse recorded observations and runner descriptions, not a counterfactual game. Disposition counts are decision opportunities; recorded applied counts also reflect original latency/stale discards. No live completion is claimed."}
    (ROOT / "lab/goals/p51-replay.json").write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    lines = ["# P51 offline replay", "", output["limits"], "",
             "| Session | Requests | Before replace | After replace | After go on |", "| --- | ---: | ---: | ---: | ---: |"]
    for session in sessions:
        lines.append(f"| {session['recording']} | {len(session['requests'])} | {session['before'].get('replaced', 0)} | {session['after'].get('replaced', 0)} | {session['after'].get('kept', 0)} |")
    lines += ["", "| Session | Time | Goal | Outcome | Reason |", "| --- | ---: | --- | --- | --- |"]
    for session in sessions:
        for event in session["timeline"]:
            lines.append(f"| {session['recording']} | {event['time']:.3f} | {event['name']} | {event['outcome']} | {event['reason']} |")
    lines += ["", "| Corpus case | Before | After | Explanation |", "| --- | --- | --- | --- |"]
    for row in changed:
        def label(value):
            return value["rule"] + ": " + ", ".join(c["name"] for c in value["plan"])
        lines.append(f"| {row['suite']} / {row['id']} | {label(row['before'])} | {label(row['after'])} | {row['reason']} |")
    (ROOT / "lab/goals/p51-replay.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"corpus_counts": output["corpus_counts"], "objective_cases": output["objective_cases"], "objective_changes": len(objective_changes), "changes": len(changed), "sessions": [{k: s[k] for k in ("recording", "before", "after", "recorded_applied")} for s in sessions]}, indent=2))
    assert not objective_changes, "Objective behavior must remain unchanged"


if __name__ == "__main__":
    main()
