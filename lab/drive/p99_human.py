"""Sample local human recordings, then retain route-behind windows and pad intervals."""

import argparse
import gzip
import itertools
import json
from bisect import bisect_right
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np
from pilot.minimap import read
from pilot.replay import hud_crop

HERE = Path(__file__).resolve().parent
ROOT = Path("/Users/kerim/recordings/kerim")
SESSIONS = (
    "20261113-141634",
    "20261113-142257",
    "20261113-172808",
    "20261113-180503",
    "20261113-184225",
    "20261113-185312",
)


def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def angle(value):
    return (value + 180) % 360 - 180


def samples(folder):
    cache = HERE / f"p99-human-{folder.name}.json.gz"
    if cache.exists():
        with gzip.open(cache, "rt") as stream:
            return json.load(stream)
    frames = lines(folder / "frames.jsonl")
    pads = lines(folder / "pad.jsonl")
    times = [p["t"] for p in pads]
    cap = cv2.VideoCapture(str(folder / "video.mp4"))
    rows, next_at = [], 0.0
    for f in frames:
        if not cap.grab():
            raise RuntimeError(f"Missing frame {folder.name}:{f['i']}")
        if f["t"] < next_at:
            continue
        next_at = f["t"] + 0.5
        ok, image = cap.retrieve()
        if not ok:
            raise RuntimeError(f"Cannot decode {folder.name}:{f['i']}")
        reading = read(hud_crop(image))
        i = bisect_right(times, f["t"]) - 1
        rows.append(
            {
                "t": f["t"],
                "i": f["i"],
                "reading": asdict(reading),
                "pad": pads[max(0, i)],
            }
        )
    cap.release()
    with gzip.open(cache, "wt") as stream:
        json.dump(rows, stream, separators=(",", ":"))
    return rows


def windows(folder, rows):
    events, last_end = [], -1
    pads = lines(folder / "pad.jsonl")
    for i, row in enumerate(rows):
        r = row["reading"]
        if (
            row["t"] <= last_end
            or r["minimap"] != "tilted"
            or r["corrupt"]
            or r["bearing"] is None
            or r["arrow"] is None
            or abs(angle(r["bearing"] - r["arrow"])) < 120
        ):
            continue
        # Require a second readable behind sample, then a sustained forward result.
        if i + 1 >= len(rows):
            continue
        nxt = rows[i + 1]["reading"]
        if (
            nxt["bearing"] is None
            or nxt["arrow"] is None
            or abs(angle(nxt["bearing"] - nxt["arrow"])) < 120
        ):
            continue
        end, ahead_since = None, None
        for candidate in rows[i + 1 :]:
            if candidate["t"] - row["t"] > 25:
                break
            c = candidate["reading"]
            ahead = (
                c["minimap"] == "tilted"
                and not c["corrupt"]
                and c["far_bearing"] is not None
                and c["arrow"] is not None
                and abs(angle(c["far_bearing"] - c["arrow"])) < 30
            )
            if ahead:
                if ahead_since is None:
                    ahead_since = candidate["t"]
                if candidate["t"] - ahead_since >= 0.5:
                    end = candidate["t"]
                    break
            else:
                ahead_since = None
        stop = end or min(row["t"] + 25, rows[-1]["t"])
        intervals, began = [], None
        for p, q in itertools.pairwise(pads):
            a, b = max(row["t"], p["t"]), min(stop, q["t"])
            if a >= b:
                continue
            if p.get("l2", 0) > 0.2 and p.get("r2", 0) < 0.1:
                if began is None:
                    began = a
            elif began is not None:
                intervals.append([began, a])
                began = None
        if began is not None:
            intervals.append([began, stop])
        last_end = stop + 1
        events.append(
            {
                "session": folder.name,
                "start": row["t"],
                "end": end,
                "duration": None if end is None else end - row["t"],
                "first_i": row["i"],
                "near": angle(r["bearing"] - r["arrow"]),
                "far": None
                if r["far_bearing"] is None
                else angle(r["far_bearing"] - r["arrow"]),
                "l2_intervals": intervals,
                "l2_seconds": sum(b - a for a, b in intervals),
            }
        )
    return events


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sheets", action="store_true")
    args = parser.parse_args()
    if args.sheets:
        strips = []
        events = json.loads((HERE / "p99-human.json").read_text())["events"]
        for index, event in enumerate(events):
            if event["end"] is None:
                continue
            folder = ROOT / event["session"]
            frames = lines(folder / "frames.jsonl")
            cap = cv2.VideoCapture(str(folder / "video.mp4"))
            images = []
            for fraction in (0, 1 / 3, 2 / 3, 1):
                t = event["start"] + event["duration"] * fraction
                f = min(frames, key=lambda f: abs(f["t"] - t))
                cap.set(cv2.CAP_PROP_POS_FRAMES, f["i"])
                ok, bgr = cap.read()
                if not ok:
                    raise RuntimeError(f"Missing context {folder.name}:{f['i']}")
                image = cv2.resize(bgr, (400, 225))
                cv2.rectangle(image, (0, 0), (400, 23), (0, 0, 0), -1)
                title = f"{index} {folder.name[-6:]} {f['t']:.2f}s"
                cv2.putText(
                    image,
                    title,
                    (5, 16),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    (255, 255, 255),
                    1,
                )
                images.append(image)
            cap.release()
            strips.append(np.concatenate(images, axis=1))
        for offset in range(0, len(strips), 4):
            cv2.imwrite(
                str(HERE / f"p99-human-context-{offset // 4 + 1}.jpg"),
                np.concatenate(strips[offset : offset + 4], axis=0),
            )
        return
    events, counts = [], {}
    for session in SESSIONS:
        rows = samples(ROOT / session)
        counts[session] = len(rows)
        found = windows(ROOT / session, rows)
        events.extend(found)
        print(
            json.dumps({"session": session, "samples": len(rows), "events": found}),
            flush=True,
        )
    (HERE / "p99-human.json").write_text(
        json.dumps({"samples": counts, "events": events}, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
