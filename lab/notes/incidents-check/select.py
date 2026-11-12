"""Pick what the check by eye looks at: every death, arrest and failed mission, and twenty
collisions drawn with seed 43 from all collisions of lab/notes/out."""

import json
import random
from pathlib import Path

here = Path(__file__).parent
pool, key = [], []
for path in sorted(here.parent.glob("out/20261111-*/incidents.jsonl")):
    for line in path.read_text().splitlines():
        row = dict(json.loads(line), recording=path.parent.name)
        if row["class"] == "collision":
            pool.append(row)
        elif row["class"] in ("death", "arrest", "mission_failed"):
            key.append(row)
chosen = sorted(random.Random(43).sample(pool, min(20, len(pool))), key=lambda r: (r["recording"], r["t"]))
fields = ("recording", "t", "frame", "class", "cause")
(here / "selected.json").write_text(
    json.dumps({"seed": 43, "collisions": len(pool), "chosen": [{k: r[k] for k in fields} for r in chosen + key]}, indent=1)
    + "\n"
)
by = {}
for row in chosen + key:
    by.setdefault(row["recording"], []).append(row)
for name, rows in by.items():
    (here / f"{name}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
print(len(pool), "collisions,", len(chosen), "drawn,", len(key), "deaths, arrests and failures")
