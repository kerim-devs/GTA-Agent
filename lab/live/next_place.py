"""The arguments for the next try at a place from the map's legend in lab/live/basics.sh: by name a place
that the last try read in the legend and that was asked for longest ago or never, a shop by kind when no
try has read a legend yet.

    pilot/.venv/bin/python lab/live/next_place.py [/Users/kerim/recordings/pilot/basics.tsv]
"""

import json
import re
import sys
from pathlib import Path


def main(path):
    asked, named = [], []
    for line in Path(path).read_text().splitlines() if Path(path).exists() else []:
        _, step, folder = line.split("\t")
        if step != "place":
            continue
        try:
            rows = [json.loads(row) for row in (Path(folder) / "play.jsonl").open()]
        except (OSError, ValueError):
            continue
        reasons = [
            str(row["skill"]["reason"])
            for row in rows
            if (row.get("skill") or {}).get("name") == "set_waypoint"
            and row["skill"].get("reason")
        ]
        if not reasons:
            continue
        went = re.search(r"(?:waypoint set|place-not-in-legend): ([^;(]+)", reasons[-1])
        if went:
            asked.append(went[1].strip())
        if "places: " in reasons[-1]:
            named = [
                name.strip()
                for name in reasons[-1].rsplit("places: ", 1)[1].split(",")
                if name.strip()
            ]
    if not named:
        args = {"kind": "shop"}
    else:
        last = {
            name: max((i for i, other in enumerate(asked) if other == name), default=-1)
            for name in named
        }
        args = {"place": min(named, key=last.get)}
    print(json.dumps(args, ensure_ascii=False))


if __name__ == "__main__":
    main(
        sys.argv[1] if len(sys.argv) > 1 else "/Users/kerim/recordings/pilot/basics.tsv"
    )
