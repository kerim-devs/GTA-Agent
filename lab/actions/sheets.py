"""Contact sheets of labelled stretches, to look at whether a label shows what it says.

    sheets.py <labelled folder> [--per 20] [--seed 42] [--min 20] [--out DIR] [--actions a b ...]

For every action with at least --min stretches (or the ones named) it draws --per stretches at random with
the seed and puts the frame from the middle of each on a sheet of four by five, with the stretch's number,
times and the rule that decided it. One pass over the video, nothing decoded is kept.
"""

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

TILE = (400, 225)
COLUMNS = 4


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("labelled", type=Path)
    parser.add_argument("--per", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min", type=int, default=20)
    parser.add_argument("--actions", nargs="*")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    info = json.loads((args.labelled / "labels.json").read_text())
    stretches = [json.loads(line) for line in (args.labelled / "actions.jsonl").read_text().splitlines()]
    for number, stretch in enumerate(stretches):
        stretch["n"] = number
    by_action = defaultdict(list)
    for stretch in stretches:
        by_action[stretch["action"]].append(stretch)
    chosen = {}
    for action, group in sorted(by_action.items()):
        if args.actions and action not in args.actions:
            continue
        if not args.actions and len(group) < args.min:
            continue
        chosen[action] = sorted(
            random.Random(f"{args.seed}-{action}").sample(group, min(args.per, len(group))),
            key=lambda s: s["start"],
        )
    wanted = {}
    for group in chosen.values():
        for stretch in group:
            wanted[(stretch["first_frame"] + stretch["last_frame"]) // 2] = None
    capture = cv2.VideoCapture(str(Path(info["recording"]) / "video.mp4"))
    targets = sorted(wanted)
    index = 0
    for target in targets:
        while index < target:
            capture.grab()
            index += 1
        ok, bgr = capture.read()
        index += 1
        wanted[target] = cv2.resize(bgr, TILE, interpolation=cv2.INTER_AREA) if ok else None
    capture.release()
    out = args.out or Path(__file__).parent / "sheets" / args.labelled.name
    out.mkdir(parents=True, exist_ok=True)
    for action, group in chosen.items():
        rows = (len(group) + COLUMNS - 1) // COLUMNS
        sheet = np.zeros((rows * (TILE[1] + 34), COLUMNS * TILE[0], 3), np.uint8)
        for k, stretch in enumerate(group):
            tile = wanted[(stretch["first_frame"] + stretch["last_frame"]) // 2]
            y, x = (k // COLUMNS) * (TILE[1] + 34), (k % COLUMNS) * TILE[0]
            if tile is not None:
                sheet[y : y + TILE[1], x : x + TILE[0]] = tile
            head = f"#{k + 1} n{stretch['n']} {stretch['start']:.1f}-{stretch['end']:.1f}s"
            rule = stretch["evidence"]["rule"][:52]
            for line, text in enumerate((head, rule)):
                cv2.putText(
                    sheet,
                    text,
                    (x + 4, y + TILE[1] + 13 + 15 * line),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.42,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )
        cv2.imwrite(str(out / f"{action}.jpg"), sheet, [cv2.IMWRITE_JPEG_QUALITY, 80])
        listing = [
            {
                "tile": k + 1,
                **{key: s[key] for key in ("n", "start", "end", "action")},
                "rule": s["evidence"]["rule"],
            }
            for k, s in enumerate(group)
        ]
        (out / f"{action}.json").write_text(json.dumps(listing, indent=1) + "\n")
        print(f"{action}: {len(group)} of {len(by_action[action])} stretches -> {out / (action + '.jpg')}")


if __name__ == "__main__":
    main()
