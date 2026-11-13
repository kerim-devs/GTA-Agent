"""Replay saved head requests offline; no runner, provider, image read or network."""

import argparse
import json
from collections import Counter
from dataclasses import fields
from pathlib import Path

from pilot.head import HeadRequest, parse_response, response_data
from pilot.mission import MissionHead


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--recordings", type=Path, default=Path("/Users/kerim/recordings/pilot")
    )
    parser.add_argument(
        "--output", type=Path, default=Path(__file__).with_name("replay.json")
    )
    args = parser.parse_args()
    paths = sorted(args.recordings.glob("*/head.jsonl"))
    allowed = {f.name for f in fields(HeadRequest)}
    before = Counter()
    after = Counter()
    rules = Counter()
    sessions = []
    for path in paths:
        head = MissionHead(goal_seed=70)
        rows = [
            json.loads(line) for line in path.read_text().splitlines() if line.strip()
        ]
        for row in rows:
            if row.get("type") != "response":
                continue
            before["responses"] += 1
            last = (row.get("request") or {}).get("last_skill") or {}
            plan = row.get("plan") or []
            if (
                row.get("disposition") == "replaced"
                and last.get("status") == "running"
                and plan
                and plan[0]["name"] == last.get("name")
            ):
                before["same_name"] += 1
                if "args" not in last:
                    before["same_name_missing_args"] += 1
                elif plan[0].get("args", {}) == last["args"]:
                    before["same_name_and_args"] += 1
        requests = [
            row for row in rows if row.get("type") == "request" and row.get("request")
        ]
        count = 0
        for row in requests:
            data = {k: v for k, v in row["request"].items() if k in allowed}
            if data.get("time") is None:
                data["time"] = row.get("t", count)
            request = HeadRequest(**data)
            answer = head.decide(request)
            assert parse_response(response_data(answer)) == answer
            rules[head.last_rule] += 1
            after["requests"] += 1
            count += 1
            last = request.last_skill or {}
            wanted = (request.hud or {}).get("wanted")
            if wanted:
                assert all(call.name != "set_waypoint" for call in answer.plan), (
                    path.name,
                    count,
                )
            if (
                answer.plan
                and last.get("status") == "running"
                and answer.plan[0].name == last.get("name")
            ):
                after["same_name"] += 1
                if "args" not in last:
                    after["same_name_missing_args"] += 1
                elif answer.plan[0].args == last["args"]:
                    after["same_name_and_args"] += 1
                    kinds = {event.get("kind") for event in request.events}
                    if kinds & {
                        "failure",
                        "skill_failed",
                        "screen",
                        "standing",
                        "guard",
                    } or any(str(k).startswith("guard_") for k in kinds):
                        after["same_call_permitted_exception"] += 1
        if count:
            sessions.append({"session": path.parent.name, "requests": count})
    assert len(sessions) >= 10
    result = {
        "seed": 70,
        "files": len(paths),
        "sessions_replayed": len(sessions),
        "before": dict(before),
        "after": dict(after),
        "rules": dict(sorted(rules.items())),
        "sessions": sessions,
        "limitation": "Historical running skills often omit args; same-name counts are proxies, not proven identical calls. Replay has no live dispositions or console effects.",
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "sessions"}, indent=2))


if __name__ == "__main__":
    main()
