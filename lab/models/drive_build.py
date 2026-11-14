"""Build the set the models are asked driving decisions on: lab/models/drive-set.json and its pictures.

    pilot/.venv/bin/python lab/models/drive_build.py

Three sources, one item a moment, each with the picture, the picture half a second before, the
vehicles and people the pilot's detector sees in both, and for the pilot's own trips the speed and
the route as read:

`night`: the 170 onsets of the avoider's brake in eight trips of 14 November that P107 sorted by the
picture (lab/avoid/p107-labels.json): a standing vehicle in the path, a slower one ahead, a crossing
one, an oncoming one, one beside the lane, nothing. One item a group of onsets, a quarter second
before the first. With them the approach of 20261114-073626 to a car standing at a red light.

`clear`: moments of the same trips in which the pilot followed its route at 8 m/s and more with no
brake of any kind within three seconds and no manoeuvre: nothing to slow down for.

`kerim`: moments of Kerim's own driving from the index of his recordings
(/Users/kerim/recordings/derived/kerim/index.jsonl, two a second, with his controller): where he
begins to brake after accelerating, where he lifts off for a second, where he holds the pedal for
four seconds. His controller was logged on the Mac while he looked at the television, and the
recorded picture lags it; the picture is taken 0.4 s after the hand.

Pictures go to /Users/kerim/recordings/derived/drive-bench/ and are not part of the repository.
"""

from __future__ import annotations

import bisect
import json
import random
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot" / "src"))

from pilot import judge  # noqa: E402
from pilot.avoid import _minimap, _seen  # noqa: E402
from pilot.objects import Detector  # noqa: E402

OUT = Path("/Users/kerim/recordings/derived/drive-bench")
PILOT = "/Users/kerim/recordings/pilot/20261114-"
WIDTH = 640
BACK = 0.5


class Video:
    def __init__(self, folder):
        self.times = [json.loads(line)["t"] for line in open(folder + "/frames.jsonl")]
        self.video = cv2.VideoCapture(folder + "/video.mp4")

    def at(self, seconds):
        index = min(max(bisect.bisect_left(self.times, seconds), 0), len(self.times) - 1)
        self.video.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = self.video.read()
        return frame if ok and frame is not None and frame.shape == (720, 1280, 3) else None


def things(detector, frame):
    objects = detector.detect(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    return [(o.kind, [round(v, 1) for v in o.box]) for o in objects if not _minimap(o.box)]


def describe(now, before):
    """The detector's boxes in words: what, where across the picture, how near, and how that changes."""

    class Box:
        def __init__(self, kind, box):
            self.kind, self.box = kind, box

    lines = []
    for kind, box in now:
        offset, wide, near = _seen(Box(kind, box))
        height = box[3] - box[1]
        centre = (box[0] + box[2]) / 2
        where = (
            "straight ahead"
            if abs(offset) < 0.06
            else f"slightly to the {'left' if offset < 0 else 'right'}"
            if abs(offset) < 0.15
            else f"to the {'left' if offset < 0 else 'right'}"
        )
        far = "very close" if near >= 0.75 else "close" if near >= 0.5 else "at a medium distance" if near >= 0.25 else "far"
        change = ""
        same = [b for k, b in before if k == kind and abs((b[0] + b[2]) / 2 - centre) < 0.12 * 1280]
        if same:
            old = min(same, key=lambda b: abs((b[0] + b[2]) / 2 - centre))
            growth = height / max(old[3] - old[1], 1e-6) - 1
            drift = (centre - (old[0] + old[2]) / 2) / 1280
            change = (
                ", coming closer fast"
                if growth >= 0.15
                else ", coming closer"
                if growth >= 0.04
                else ", moving away"
                if growth <= -0.04
                else ", at a steady distance"
            )
            if abs(drift) >= 0.03:
                change += f", moving to the {'left' if drift < 0 else 'right'} across the picture"
        lines.append((near, f"{kind} {where}, {far}{change}"))
    lines.sort(reverse=True)
    return [text for _, text in lines[:6]]


def route(reading):
    near, far, arrow = reading.get("bearing"), reading.get("far_bearing"), reading.get("arrow")
    if near is None or arrow is None:
        return None
    turn = lambda value: (value - arrow + 180) % 360 - 180  # noqa: E731
    first, later = turn(near), turn(far if far is not None else near)
    if abs(first) < 10 and abs(later) < 15:
        return "straight ahead"
    side = "left" if later < 0 else "right"
    return f"bends to the {side} ahead" if abs(later) < 50 else f"turns {side} at the next junction"


def rows(run):
    out = []
    for line in open(PILOT + run + "/play.jsonl"):
        try:
            row = json.loads(line)
        except Exception:
            continue
        result, reading, pad = row.get("result") or {}, row.get("reading") or {}, row.get("sent_pad") or {}
        out.append(
            (
                row["t"],
                result.get("driver_state"),
                (pad.get("l2") or 0) > 0.05,
                result.get("around_pedal") is not None and result.get("around_pedal") < 0,
                reading,
            )
        )
    return out


def main():
    random.seed(14)
    OUT.mkdir(parents=True, exist_ok=True)
    detector = Detector()
    items = []

    def add(ident, source, label, video, seconds, reading=None, note=""):
        frame, earlier = video.at(seconds), video.at(seconds - BACK)
        if frame is None or earlier is None:
            return
        now, before = things(detector, frame), things(detector, earlier)
        for name, picture in ((ident, frame), (ident + "-before", earlier)):
            (OUT / f"{name}.b64").write_text(judge.encode(picture, WIDTH))
        items.append(
            {
                "id": ident,
                "source": source,
                "label": label,
                "seconds": round(seconds, 2),
                "speed": None if not reading or reading.get("gps_speed") is None else round(reading["gps_speed"], 1),
                "route": route(reading) if reading else None,
                "things": describe(now, before),
                "note": note,
            }
        )

    labels = json.loads((ROOT / "lab/avoid/p107-labels.json").read_text())
    for run, onsets in labels.items():
        video, play = Video(PILOT + run), rows(run)
        times = [r[0] for r in play]
        last = -10.0
        for onset in sorted(onsets, key=lambda o: o["start"]):
            if onset["start"] - last < 1.5:
                last = onset["end"]
                continue
            last = onset["end"]
            at = onset["start"] - 0.25
            reading = play[max(bisect.bisect_right(times, at) - 1, 0)][4]
            add(f"night-{run}-{onset['id']}", "night", onset["class"], video, at, reading, onset.get("note", ""))
        busy = [t for t, state, l2, hit, _ in play if l2 or hit or state not in ("follow", "coast")]
        chosen = -10.0
        count = 0
        for t, state, _l2, _hit, reading in play:
            speed = reading.get("gps_speed")
            if state != "follow" or speed is None or speed < 8 or t - chosen < 8 or count >= 16:
                continue
            i = bisect.bisect_left(busy, t - 3)
            if i < len(busy) and busy[i] <= t + 3:
                continue
            add(f"clear-{run}-{int(t)}", "clear", "clear", video, t, reading)
            chosen, count = t, count + 1
    run = "073626"
    video, play = Video(PILOT + run), rows(run)
    times = [r[0] for r in play]
    for at in (93.8, 94.3, 94.9, 95.4):
        reading = play[max(bisect.bisect_right(times, at) - 1, 0)][4]
        add(f"night-{run}-{at}", "night", "standing", video, at, reading, "dark car standing at a red light, struck at 96.2 s")

    by = {}
    for line in open("/Users/kerim/recordings/derived/kerim/index.jsonl"):
        row = json.loads(line)
        by.setdefault(row["recording"], []).append(row)
    found = {"brake": [], "lift": [], "cruise": []}
    for recording, seq in by.items():
        drive = [r["action"] in ("follow_route", "drive_free") for r in seq]
        for i in range(4, len(seq) - 4):
            if not all(drive[i - 4 : i + 5]):
                continue
            pad = lambda k: seq[k]["pad"]  # noqa: E731
            if seq[i + 4]["time"] - seq[i - 4]["time"] > 4.5:
                continue
            fast = pad(i - 1)["r2"] > 0.5 and pad(i - 2)["r2"] > 0.5 and pad(i - 1)["l2"] < 0.05
            if fast and pad(i)["l2"] > 0.3:
                found["brake"].append((recording, seq[i]["time"]))
            elif fast and pad(i)["r2"] < 0.1 and pad(i + 1)["r2"] < 0.1 and max(pad(i)["l2"], pad(i + 1)["l2"], pad(i + 2)["l2"]) < 0.05:
                found["lift"].append((recording, seq[i]["time"]))
            elif all(pad(k)["r2"] > 0.6 and pad(k)["l2"] < 0.02 for k in range(i - 4, i + 5)):
                found["cruise"].append((recording, seq[i]["time"]))
    videos = {}
    for label, want in (("brake", 60), ("lift", 50), ("cruise", 70)):
        pool = found[label]
        random.shuffle(pool)
        per, taken = {}, []
        for recording, t in pool:
            if per.get(recording, 0) >= 5 or any(r == recording and abs(t - u) < 6 for r, u in taken):
                continue
            per[recording] = per.get(recording, 0) + 1
            taken.append((recording, t))
            if len(taken) >= want:
                break
        for recording, t in taken:
            video = videos.setdefault(recording, Video(recording))
            add(f"kerim-{Path(recording).name}-{int(t)}-{label}", "kerim", label, video, t + 0.4)
        print(label, "found", len(pool), "taken", len(taken))
    Path(__file__).with_name("drive-set.json").write_text(json.dumps(items, indent=1))
    counts = {}
    for item in items:
        counts[(item["source"], item["label"])] = counts.get((item["source"], item["label"]), 0) + 1
    print(len(items), "items", counts)


if __name__ == "__main__":
    main()
