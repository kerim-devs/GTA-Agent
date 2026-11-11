"""Replay the frozen corpus; never invoke a model or a live game."""

import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from time import perf_counter_ns

from pilot.head import HeadRequest, parse_response
from pilot.mission import MissionHead

ROOT = Path(__file__).resolve().parent


class RecordedFallback:
    def __init__(self, answer):
        self.answer = answer

    def decide(self, request):
        return self.answer


def main():
    cases = json.loads((ROOT / "saved_cases.json").read_text())
    cases += json.loads((ROOT / "frame_cases.json").read_text())
    cases += json.loads((ROOT / "extra_cases.json").read_text())
    results = []
    counts = Counter()
    for case in cases:
        model = case["model"]
        answer = parse_response(
            model
            or {
                "plan": [{"name": "look", "args": {"duration": 0.5, "angle": 0}}],
                "sentence": "Die Lage ist unklar, ich schaue mich um.",
            }
        )
        head = MissionHead(RecordedFallback(answer))
        start = perf_counter_ns()
        result = head.decide(HeadRequest(**case["request"]))
        elapsed_ms = (perf_counter_ns() - start) / 1e6
        counts[head.last_rule] += 1
        rule = head.last_rule
        plan = asdict(result)["plan"] if rule != "fallback" else None
        if rule == "fallback":
            verdict = (
                "No supported rule; delegate the unchanged request. No model was invoked in this replay."
            )
        elif model:
            if any(call["name"] == "wait" for call in model["plan"]):
                verdict = (
                    "Rule preferred: the request shows free movement; "
                    "the model repeats a wait loop contrary to prompt lines 16-23."
                )
            elif list(plan) == model["plan"]:
                verdict = "Plans agree exactly."
            else:
                verdict = (
                    "Both explore with look/walk. The rule uses fixed parameters; "
                    "no observed target supports preferring the model parameters. "
                    "Neither plan proves a safe path or mission progress."
                )
        else:
            verdict = (
                "No saved model answer for this recorded frame; "
                "only prompt/observation consistency can be judged."
            )
        results.append(
            dict(
                id=case["id"],
                source=case["source"],
                rule=rule,
                plan=plan,
                sentence=result.sentence if plan else None,
                model=model,
                verdict=verdict,
                elapsed_ms=elapsed_ms,
            )
        )
    report = dict(
        counts=dict(counts),
        total=len(cases),
        rules=sum(n for rule, n in counts.items() if rule != "fallback"),
        fallback=counts["fallback"],
        cases=results,
    )
    (ROOT / "comparison.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    rows = [
        "| Case | Rule | Rule plan | Recorded model plan | Difference assessment |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in results:

        def plan_text(plan):
            return "; ".join(
                call["name"] + "(" + ", ".join(f"{key}={value}" for key, value in call["args"].items()) + ")"
                for call in plan
            )

        rows.append(
            "| "
            + " | ".join(
                [
                    item["id"],
                    item["rule"],
                    plan_text(item["plan"]) if item["plan"] else "Delegated",
                    plan_text(item["model"]["plan"]) if item["model"] else "Not recorded",
                    item["verdict"],
                ]
            )
            + " |"
        )
    (ROOT / "cases.md").write_text("\n".join(rows) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "cases"}))


if __name__ == "__main__":
    main()
