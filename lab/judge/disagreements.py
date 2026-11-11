"""List the frames on which a measured model and the readers' labels disagree.

    pilot/.venv/bin/python lab/judge/disagreements.py lab/judge/results/<file>.json [--sheet out.jpg]

The labels come from the readers and are not the truth: look at each listed frame before counting it
against the model. `--sheet` writes the frames side by side with both answers printed on them.
"""

import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("result", type=Path)
parser.add_argument("--question", default="situation", choices=("situation", "wanted"))
parser.add_argument("--sheet", type=Path)
args = parser.parse_args()

rows = json.loads(args.result.read_text())["rows"]
wrong = []
for row in rows:
    answer = row["answers"][args.question]
    if args.question == "situation":
        label = row["situation"]
    elif row["wanted"] is None or row["situation"] not in ("foot", "vehicle"):
        continue
    else:
        label = row["wanted"] > 0
    if answer["value"] != label:
        # The margin between the two best letters says how sure the model was of its answer.
        best = sorted(answer["top"].values(), reverse=True)[:2]
        margin = round(math.exp(best[0]) - math.exp(best[1]), 2) if len(best) == 2 else None
        wrong.append((row["name"], label, answer["value"], margin))
        print(f"{row['name']:<16} readers {label!s:<15} model {answer['value']!s:<15} margin {margin}")
print(f"{len(wrong)} of {len(rows)}")

if args.sheet and wrong:
    tiles = []
    for name, label, value, _margin in wrong:
        tile = cv2.resize(cv2.imread(str(HERE / "sample" / f"{name}.jpg")), (480, 270))
        cv2.rectangle(tile, (0, 0), (480, 22), (0, 0, 0), -1)
        cv2.putText(tile, f"{name}  readers {label}  model {value}", (4, 16), 0, 0.45, (255, 255, 255), 1)
        tiles.append(tile)
    columns = 4
    while len(tiles) % columns:
        tiles.append(np.zeros_like(tiles[0]))
    sheet = np.vstack([np.hstack(tiles[i : i + columns]) for i in range(0, len(tiles), columns)])
    cv2.imwrite(str(args.sheet), sheet)
