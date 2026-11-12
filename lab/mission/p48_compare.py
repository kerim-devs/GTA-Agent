"""Replay frozen requests and measure available derived evidence without raw media."""

import hashlib
import json
import subprocess
import sys
import types
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot/src"))
from pilot.head import HeadRequest, parse_response
from pilot.mission import MissionHead
from pilot.notes import intent

DERIVED = Path("/Users/kerim/recordings/derived/kerim")
BASELINE = subprocess.check_output(
    ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
).strip()
source = subprocess.check_output(
    ["git", "show", f"{BASELINE}:pilot/src/pilot/mission.py"], cwd=ROOT, text=True
)
module = types.ModuleType("pilot._p48_baseline")
module.__package__ = "pilot"
exec(compile(source, "baseline/mission.py", "exec"), module.__dict__)  # noqa: S102 -- trusted local Git baseline


INPUTS = {}


def read_json(path):
    payload = path.read_bytes()
    INPUTS[str(path)] = hashlib.sha256(payload).hexdigest()
    return json.loads(payload)


class Fallback:
    def __init__(self, model=None):
        self.answer = parse_response(
            model
            or {
                "plan": [{"name": "wait", "args": {"duration": 1}}],
                "sentence": "Recorded fallback.",
            }
        )

    def decide(self, request):
        return self.answer


def decide(head_type, request, model=None):
    head = head_type(Fallback(model))
    answer = head.decide(HeadRequest(**request))
    return {"rule": head.last_rule, "plan": asdict(answer)["plan"]}


def category(result):
    if result["rule"] == "fallback":
        return "delegated"
    names = {call["name"] for call in result["plan"]}
    for skill, label in [
        ("fight", "combat"),
        ("enter_vehicle", "vehicle_entry"),
        ("drive_route", "drive"),
        ("set_waypoint", "drive"),
        ("walk_to", "foot"),
        ("walk_road", "foot"),
        ("walk", "foot"),
        ("wait", "wait"),
    ]:
        if skill in names:
            return label
    return "look"


def human_category(human):
    values = human.get("seconds", {})
    groups = {
        "drive": values.get("driving", 0),
        "foot": max(values.get("walking", 0), values.get("running", 0)),
        "combat": max(values.get("aiming", 0), values.get("firing", 0)),
        "vehicle_entry": values.get("vehicle_input", 0),
        "look": values.get("looking", 0),
        "neutral": values.get("neutral", 0),
    }
    return max(groups, key=groups.get) if any(groups.values()) else "unknown"


def main():
    cases = []
    for name in ("saved_cases", "frame_cases", "extra_cases"):
        for case in read_json(ROOT / f"lab/mission/{name}.json"):
            cases.append(("mission", case["id"], case["request"], case.get("model")))
    for i, case in enumerate(read_json(ROOT / "lab/take-out/cases.json")):
        cases.append(
            (
                "take-out",
                f"{case['recording']}:{case.get('step', i)}:{i}",
                case["request"],
                None,
            )
        )
    p45 = read_json(ROOT / "lab/foot/p45-decisions.json")
    for i, case in enumerate(p45["changes"]):
        cases.append(("p45-changes", str(case.get("id", i)), case["request"], None))
    for session in p45["sessions"]:
        for i, case in enumerate(session["requests"]):
            cases.append(
                (
                    "p45-sessions",
                    f"{session['recording']}:{case.get('id', i)}",
                    case["request"],
                    None,
                )
            )
    changes = []
    for suite, case_id, request, model in cases:
        before, after = (
            decide(module.MissionHead, request, model),
            decide(MissionHead, request, model),
        )
        if before != after:
            changes.append(
                {
                    "suite": suite,
                    "id": case_id,
                    "request": request,
                    "before": before,
                    "after": after,
                    "reason": f"Intent {intent(request.get('objective', ''))['class']} now selects its class rule; safety and recovery still take priority except stationary wait recovery.",
                }
            )
    stats = defaultdict(
        lambda: {
            "steps": 0,
            "recordings": set(),
            "observed_seconds": 0,
            "coarse_seconds": Counter(),
            "first20_action_labels": None,
            "whole_step_action_labels": None,
        }
    )
    rows = []
    mission_files = sorted(DERIVED.glob("*/missions.json"))
    for path in mission_files:
        data = read_json(path)
        sections = read_json(path.with_name("sections.json"))["sections"]
        frozen = read_json(path.with_name("cases.json"))
        for mission in data["missions"]:
            for step in mission["steps"]:
                start = step["start"]
                cls = intent(step["objective"])["class"]
                human = step.get("human") or {}
                stat = stats[cls]
                stat["steps"] += 1
                stat["recordings"].add(path.parent.name)
                stat["observed_seconds"] += human.get("observed_seconds", 0)
                stat["coarse_seconds"].update(human.get("seconds", {}))
                section = next(
                    (s for s in sections if s["start"] <= start < s["end"]), {}
                )
                mode = section.get("kind", "unknown")
                sample = step.get("sample_observation") or {}
                minimap = {
                    "route": sample.get("route", "none"),
                    "blips": sample.get("blips", []),
                }
                if mode in {"drive", "foot"}:
                    minimap["minimap"] = {"drive": "tilted", "foot": "flat"}[mode]
                wanted = section.get("wanted")
                wanted = wanted if isinstance(wanted, (int, float)) else None
                request = {
                    "events": [],
                    "help": "",
                    "objective": step["objective"],
                    "subtitle": "",
                    "banner": "",
                    "minimap": minimap,
                    "last_skill": None,
                    "notebook": {},
                    "jpeg_path": "unused-derived-only.jpg",
                    "hud": {"screen": section.get("screen", "game"), "wanted": wanted},
                    "objects": [],
                }
                matches = [
                    c
                    for c in frozen
                    if abs(c.get("step_start", -100) - start) < 0.02
                    and c["objective"] == step["objective"]
                ]
                sample_human = matches[0].get("human", {}) if len(matches) == 1 else {}
                before, after = (
                    decide(module.MissionHead, request),
                    decide(MissionHead, request),
                )
                observed = human_category(sample_human)
                planned = category(after)
                agreement = (
                    "unknown"
                    if observed in {"unknown", "neutral"} or planned == "delegated"
                    else (
                        "same category" if planned == observed else "different category"
                    )
                )
                rows.append(
                    {
                        "recording": path.parent.name,
                        "start": start,
                        "end": step["end"],
                        "objective": step["objective"],
                        "class": cls,
                        "section_mode": mode,
                        "minimap_sample_t": sample.get("t"),
                        "request": request,
                        "before": before,
                        "after": after,
                        "human_whole_step": human,
                        "human_frozen_3s": sample_human,
                        "human_category": observed,
                        "agreement": agreement,
                        "frozen_case_matches": len(matches),
                    }
                )
    for cls in (
        "go_to",
        "bring",
        "enter_vehicle",
        "take_out",
        "follow",
        "escape",
        "steal",
        "pick_up",
        "wait",
        "return_to",
        "protect",
        "destroy",
        "use",
        "sneak",
        "unknown",
    ):
        stats[cls]
    for row in rows:
        if row["before"] != row["after"]:
            changes.append(
                {
                    "suite": "derived-steps",
                    "id": f"{row['recording']}:{row['start']}",
                    "request": row["request"],
                    "before": row["before"],
                    "after": row["after"],
                    "reason": f"The {row['class']} objective selects its existing-skill class mapping instead of the generic route/blip default.",
                }
            )
    for stat in stats.values():
        stat["recordings"] = sorted(stat["recordings"])
        denominator = stat["observed_seconds"]
        stat["coarse_shares"] = {
            k: v / denominator if denominator else None
            for k, v in stat["coarse_seconds"].items()
        }
        stat["insufficient"] = stat["steps"] < 5 or len(stat["recordings"]) < 3
    output = {
        "baseline": BASELINE,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_sha256": INPUTS,
        "data_root": str(DERIVED),
        "mission_files": len(mission_files),
        "actions_files": len(list(DERIVED.glob("*/actions.jsonl"))),
        "corpus_counts": {
            **dict(Counter(c[0] for c in cases)),
            "derived-steps": len(rows),
        },
        "changes": changes,
        "classes": dict(stats),
        "steps": rows,
        "limitations": [
            "P42 actions.jsonl absent: 18-label shares and first-20-second action/drive/walk shares cannot be measured.",
            "Whole-step coarse human signals overlap; they are not mutually exclusive action labels.",
            "Three-second human categories use maxima of overlapping signals (walking/running and aiming/firing), not dominant action labels. They are frozen sample windows, not the first 20 seconds; neutral is not proof of intentional waiting.",
            "Minimap comes from the derived sample at its recorded timestamp, not necessarily objective onset; objects and absent state stay empty.",
            "Replay is one independent initial decision per step; it does not demonstrate live skill success.",
        ],
    }
    out = ROOT / "lab/mission/p48-decisions.json"
    out.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n")
    lines = [
        "# P48 derived comparison",
        "",
        "The baseline is `"
        + BASELINE
        + "`. P42 action files are absent. Whole-step coarse signals and frozen three-second samples below are proxies, not the requested 18-label or first-20-second measurements.",
        "",
        "| Class | Steps | Recordings | Observed seconds | Driving share | Walking share | Sample |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for cls, stat in sorted(stats.items()):
        shares = stat["coarse_shares"]
        lines.append(
            f"| {cls} | {stat['steps']} | {len(stat['recordings'])} | {stat['observed_seconds']:.2f} | {shares.get('driving', 0):.1%} | {shares.get('walking', 0):.1%} | {'insufficient' if stat['insufficient'] else 'small descriptive sample'} |"
        )
    lines.extend(
        [
            "",
            "| Class | Recording / start | Objective | Mode | First plan | Kerim 3s signal proxy | Agreement |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in sorted(rows, key=lambda r: (r["class"], r["recording"], r["start"])):
        plan = ", ".join(c["name"] for c in row["after"]["plan"])
        lines.append(
            f"| {row['class']} | {row['recording']} / {row['start']:.2f} | {row['objective'].replace('|', '/')} | {row['section_mode']} | {row['after']['rule']}: {plan} | {row['human_category']} | {row['agreement']} |"
        )
    lines.extend(
        [
            "",
            "| Corpus | Case | Before | After | Reason |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for c in changes:
        before = (
            c["before"]["rule"]
            + ": "
            + ", ".join(x["name"] for x in c["before"]["plan"])
        )
        after = (
            c["after"]["rule"] + ": " + ", ".join(x["name"] for x in c["after"]["plan"])
        )
        lines.append(
            f"| {c['suite']} | {c['id']} | {before} | {after} | {c['reason']} |"
        )
    (ROOT / "lab/mission/p48-comparison.md").write_text("\n".join(lines) + "\n")
    print(
        json.dumps(
            {
                "corpus_counts": output["corpus_counts"],
                "changes": len(changes),
                "changed_by_suite": dict(Counter(c["suite"] for c in changes)),
                "steps": len(rows),
                "classes": {k: v["steps"] for k, v in stats.items()},
                "agreement": dict(Counter(r["agreement"] for r in rows)),
                "derived_changes": sum(r["before"] != r["after"] for r in rows),
                "actions_files": output["actions_files"],
                "unmatched_samples": sum(r["frozen_case_matches"] != 1 for r in rows),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
