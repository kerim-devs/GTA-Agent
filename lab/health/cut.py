"""Cut the HUD strips of the cases in cases.json out of the recordings.

For every case the frames a loop at thirty ticks a second would read in the case's window (the
newest frame at each tick) are decoded, and rows 670 to 682, columns 64 to 243 of each are stacked
into <name>.png beside this file; the native index and capture time of each go into the case's
"frames". Recordings are only read.

usage: cut.py [--recordings ~/recordings] [names...]
"""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
ROWS, COLUMNS = (670, 683), (64, 244)
TICK = 1 / 30


def ticks(times):
    """Indices of the frames a 30 Hz loop reads fresh: the newest frame at each tick."""
    out, k, now = [], -1, times[0]
    while now <= times[-1]:
        while k + 1 < len(times) and times[k + 1] <= now:
            k += 1
        if k >= 0 and (not out or out[-1] != k):
            out.append(k)
        now += TICK
    return out


def cut(case, recordings):
    root = recordings / case["recording"]
    rows = [json.loads(line) for line in (root / "frames.jsonl").read_text().splitlines() if line.strip()]
    t0, t1 = case["window"]
    inside = [row for row in rows if t0 <= row["t"] <= t1]
    picked = [inside[k] for k in ticks([row["t"] for row in inside])]
    capture = cv2.VideoCapture(str(root / "video.mp4"))
    capture.set(cv2.CAP_PROP_POS_FRAMES, inside[0]["i"])
    strips, frames, wanted, index = [], [], {row["i"] for row in picked}, inside[0]["i"]
    while index <= picked[-1]["i"]:
        ok, bgr = capture.read()
        if not ok:
            raise RuntimeError(f"{root}: frame {index} could not be decoded")
        if index in wanted:
            strips.append(bgr[ROWS[0] : ROWS[1], COLUMNS[0] : COLUMNS[1]])
        index += 1
    frames = [[row["i"], row["t"]] for row in picked]
    cv2.imwrite(str(HERE / f"{case['name']}.png"), np.concatenate(strips), [cv2.IMWRITE_PNG_COMPRESSION, 9])
    return frames


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--recordings", type=Path, default=Path.home() / "recordings")
    parser.add_argument("names", nargs="*")
    args = parser.parse_args()
    path = HERE / "cases.json"
    data = json.loads(path.read_text())
    for case in data["cases"]:
        if args.names and case["name"] not in args.names:
            continue
        case["frames"] = cut(case, args.recordings)
        print(case["name"], len(case["frames"]))
        path.write_text(dump(data))


def dump(data):
    """One case to a line, so that the file reads as a list."""
    head = "".join(f" {json.dumps(k)}: {json.dumps(v)},\n" for k, v in data.items() if k != "cases")
    cases = ",\n".join("  " + json.dumps(case) for case in data["cases"])
    return f'{{\n{head} "cases": [\n{cases}\n ]\n}}\n'


if __name__ == "__main__":
    main()
