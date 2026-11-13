"""Sparse, read-only P100 recording audit. Run with nice -n 15 from the repo root."""

import argparse
import bisect
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent
PILOT = Path("/Users/kerim/recordings/pilot")
WINDOWS = {
    "20261113-225835": [(1, 0.59, 25.65), (3, 27.29, 52.35), (5, 62.49, 87.52)],
    "20261113-230030": [
        (3, 440.44, 465.51),
        (5, 467.13, 492.19),
        (7, 502.31, 527.38),
        (9, 528.99, 558),
    ],
    "20261113-234407": [(15, 622.82, 627)],
}


def rows(path):
    return [json.loads(line) for line in path.open()]


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + "\n")


def pilot():
    from pilot.objects import Detector

    detector = Detector()
    runs = []
    for session, windows in WINDOWS.items():
        folder = PILOT / session
        play = rows(folder / "play.jsonl")
        frames = rows(folder / "frames.jsonl")
        times = [r["t"] for r in play]
        indices = {r["frame_id"]: r["i"] for r in frames}
        head = rows(folder / "head.jsonl")
        origin = next(r["t"] for r in head if r["type"] == "request") - play[0]["t"]
        judges = rows(folder / "judge.jsonl")
        judge_times = [r["t"] - origin for r in judges]
        video = cv2.VideoCapture(str(folder / "video.mp4"))
        for attempt, start, end in windows:
            raw = [
                r for r in play if (r.get("skill") or {}).get("attempt_id") == attempt
            ]
            raw = [r for r in raw if start - 0.1 <= r["t"] <= end]
            samples, tiles = [], []
            for n, wanted in enumerate(np.arange(start, end, 0.5)):
                row = play[bisect.bisect_left(times, wanted)]
                index = indices[row["frame_id"]]
                video.set(cv2.CAP_PROP_POS_FRAMES, index)
                ok, bgr = video.read()
                if not ok:
                    raise RuntimeError(f"Missing frame {session}:{index}")
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                objects, figure, own = detector.detect_split(rgb)
                ji = bisect.bisect_right(judge_times, row["t"]) - 1
                judge = judges[ji] if ji >= 0 else None
                sample = {
                    "play": row,
                    "video_frame": index,
                    "video_time": frames[index]["t"],
                    "objects": [asdict(d) for d in objects],
                    "figure": asdict(figure) if figure else None,
                    "figure_vehicle": asdict(own) if own else None,
                    "judge": judge,
                    "judge_origin": origin,
                }
                samples.append(sample)
                if n % 6 == 0 or wanted + 0.5 >= end:
                    marked = bgr.copy()
                    for d in (*objects, *((own,) if own else ())):
                        x0, y0, x1, y1 = map(int, d.box)
                        color = (0, 255, 255) if d is own else (0, 255, 0)
                        cv2.rectangle(marked, (x0, y0), (x1, y1), color, 2)
                    tile = cv2.resize(marked, (640, 360))
                    cv2.putText(
                        tile,
                        f"{session} {row['t']:.2f}s f{index}",
                        (8, 20),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (255, 255, 255),
                        1,
                    )
                    tiles.append(tile)
            while len(tiles) % 3:
                tiles.append(np.zeros_like(tiles[0]))
            sheet = np.vstack(
                [np.hstack(tiles[i : i + 3]) for i in range(0, len(tiles), 3)]
            )
            cv2.imwrite(str(OUT / f"p100-{session}-{attempt}.jpg"), sheet)
            run = {
                "session": session,
                "attempt": attempt,
                "start": raw[0]["t"],
                "end": raw[-1]["t"],
                "last_skill": raw[-1]["skill"],
                "presses": [
                    r["t"]
                    for r in raw
                    if "triangle" in (r.get("sent_pad") or {}).get("buttons", [])
                ],
                "sprint_ticks": sum(
                    "cross" in (r.get("sent_pad") or {}).get("buttons", []) for r in raw
                ),
                "reasons": dict(
                    Counter((r.get("result") or {}).get("reason") or "" for r in raw)
                ),
                "samples": samples,
            }
            runs.append(run)
            print(session, attempt, len(samples), "presses", run["presses"], flush=True)
        video.release()
    save(
        "p100-recorded.json",
        {
            "scope": "Original play rows lack objects, figure, accepted mode and moving. Boxes and figure are fresh sparse detector inference, not historical detector deliveries. Judge rows are carried causally by arrival time; their origin is estimated from startup. No counterfactual travel or success is measured.",
            "runs": runs,
        },
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    cv2.setNumThreads(1)
    pilot()
