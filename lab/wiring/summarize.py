"""Extract screen decisions and recorded human button edges on the capture clock."""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("replay", type=Path)
    parser.add_argument("recording", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    rows = [json.loads(line) for line in (args.replay / "head.jsonl").read_text().splitlines()]
    human, previous = [], set()
    for line in (args.recording / "pad.jsonl").read_text().splitlines():
        row = json.loads(line)
        if row.get("src") != "human":
            continue
        buttons = set(row["buttons"])
        for edge, values in (("down", buttons - previous), ("up", previous - buttons)):
            for button in sorted(values & {"cross", "circle", "options", "l1", "up"}):
                human.append({"t": row["t"], "button": button, "edge": edge})
        previous = buttons
    episodes = []
    active = None
    for row in rows:
        if row["type"] == "flow_enter":
            assert active is None
            active = row
        if row["type"] != "flow_exit":
            continue
        assert active is not None
        events = [{"t": request["t"], "events": request["request"]["events"]}
                  for request in rows if request["type"] == "request" and active["t"] <= request["t"] <= row["t"]]
        episodes.append({"screen": active["screen"], "enter": active["t"], "exit": row["t"],
                         "seconds": row["seconds"],
                         "actions": [{"t": active["t"] + action["seconds"], **action} for action in row["actions"]],
                         "head": events,
                         "human": [edge for edge in human if active["t"] - 1 <= edge["t"] <= row["t"] + .3]})
        active = None
    assert active is None
    args.out.write_text(json.dumps({"episodes": episodes}, indent=2) + "\n")
    print(f"{len(episodes)} complete takeovers; {sum(len(item['head']) for item in episodes)} head requests in those intervals")


if __name__ == "__main__":
    main()
