"""Contact sheets around incidents, or over a whole recording, on the clock of frames.jsonl.

    incident_sheets.py <recording> --incidents incidents.jsonl --classes death,arrest --out DIR
    incident_sheets.py <recording> --span 670 690 --step 0.5 --out DIR
    incident_sheets.py <recording> --overview 2 --out DIR

One sequential decode per call; frames are taken in time order, never cached.
"""

import argparse
import json
import random
from bisect import bisect_left
from pathlib import Path

import cv2
import numpy as np

CELL_W, CELL_H, LABEL = 320, 180, 18


def frame_index(frames, times, t):
    return frames[min(len(frames) - 1, bisect_left(times, t))]["i"]


def grab(recording, wanted):
    """Decode once, in order, and return {frame index: small BGR image} for the wanted indices."""
    wanted = sorted(set(wanted))
    images = {}
    capture = cv2.VideoCapture(str(recording / "video.mp4"))
    try:
        position = 0
        for index in wanted:
            if index - position > 400:
                capture.set(cv2.CAP_PROP_POS_FRAMES, index)
                position = index
            while position < index:
                capture.grab()
                position += 1
            ok, image = capture.read()
            position += 1
            if ok:
                images[index] = cv2.resize(image, (CELL_W, CELL_H), interpolation=cv2.INTER_AREA)
    finally:
        capture.release()
    return images


def sheet(cells, images, columns, title):
    rows = (len(cells) + columns - 1) // columns
    canvas = np.zeros((LABEL + rows * (CELL_H + LABEL), columns * CELL_W, 3), np.uint8)
    cv2.putText(canvas, title[:150], (4, 13), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 255), 1)
    for n, (t, index, mark) in enumerate(cells):
        y, x = LABEL + (n // columns) * (CELL_H + LABEL), (n % columns) * CELL_W
        if index in images:
            canvas[y : y + CELL_H, x : x + CELL_W] = images[index]
        colour = (0, 0, 255) if mark else (255, 255, 255)
        cv2.putText(canvas, f"{t:.1f}s #{index}", (x + 4, y + CELL_H + 13), cv2.FONT_HERSHEY_SIMPLEX, 0.42, colour, 1)
    return canvas


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--incidents", type=Path)
    parser.add_argument("--classes", default="death,arrest,mission_failed")
    parser.add_argument("--sample", default="", help="class:count:seed, e.g. collision:20:43")
    parser.add_argument("--span", type=float, nargs=2)
    parser.add_argument("--step", type=float, default=0.5)
    parser.add_argument("--overview", type=float, help="one frame every this many seconds, whole recording")
    args = parser.parse_args()
    frames = [json.loads(line) for line in (args.recording / "frames.jsonl").read_text().splitlines()]
    times = [row["t"] for row in frames]
    args.out.mkdir(parents=True, exist_ok=True)
    jobs = []  # (file name, title, [(t, index, mark)], columns)
    if args.incidents:
        rows = [json.loads(line) for line in args.incidents.read_text().splitlines() if line.strip()]
        chosen = [row for row in rows if row["class"] in args.classes.split(",")]
        if args.sample:
            kind, count, seed = args.sample.split(":")
            pool = [row for row in rows if row["class"] == kind]
            chosen = random.Random(int(seed)).sample(pool, min(int(count), len(pool)))
        for row in chosen:
            steps = [row["t"] + k * 0.5 for k in range(-10, 7)]
            cells = [(t, frame_index(frames, times, t), abs(t - row["t"]) < 0.25) for t in steps]
            title = f"{args.recording.name} {row['t']:.1f}s {row['class']} {row.get('cause')} {row.get('detail', '')}"
            jobs.append((f"{args.recording.name}-{row['t']:07.1f}-{row['class']}.jpg", title, cells, 6))
    if args.span:
        start, end = args.span
        steps = np.arange(start, end + 1e-6, args.step)
        cells = [(float(t), frame_index(frames, times, t), False) for t in steps]
        jobs.append((f"{args.recording.name}-span-{start:.0f}-{end:.0f}.jpg", f"{args.recording.name} {start}-{end}", cells, 8))
    if args.overview:
        steps = np.arange(0, times[-1], args.overview)
        for page in range(0, len(steps), 80):
            cells = [(float(t), frame_index(frames, times, t), False) for t in steps[page : page + 80]]
            jobs.append((f"{args.recording.name}-overview-{page // 80 + 1:02}.jpg", f"{args.recording.name} overview", cells, 10))
    images = grab(args.recording, [cell[1] for job in jobs for cell in job[2]])
    for name, title, cells, columns in jobs:
        cv2.imwrite(str(args.out / name), sheet(cells, images, columns, title), [cv2.IMWRITE_JPEG_QUALITY, 80])
    print(f"{len(jobs)} sheets in {args.out}")


if __name__ == "__main__":
    main()
