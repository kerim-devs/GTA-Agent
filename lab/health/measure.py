"""Run the health reader and the hit signal over the recorded frames themselves.

No replay of the reaction bench: every native frame of the windows below is decoded, the frames a
loop at thirty ticks a second reads go through the reader, and a fresh `Hits` per stretch is fed
their readings. The windows are the 55 scenes of lab/reaction/scenes.json from seven seconds
before the onset (one second for the signal to settle, six counted), the 47 hits of cases.json
from 2.5 s before to 1.2 s after their first shorter frame, the fight stretches and the extra
windows of cases.json. Windows that overlap in a recording are read as one stretch.

  measure.py run OUT [--part K/N] [--old OLD_HUD.py]   decode and read; one JSON line a stretch
  measure.py summary OUT...                            the counts the report gives
  measure.py time [--old OLD_HUD.py] [--repeats R]     time per frame on lab/hud's full frames

Run from pilot/ with its interpreter. The old reader is `git show 974d9a0:pilot/src/pilot/hud.py`.
Recordings are only read.
"""

import argparse
import importlib.util
import json
import time
from pathlib import Path
from statistics import median

import cv2
import numpy as np

from pilot import hud
from pilot.contract import Hud
from pilot.hits import Hits

HERE = Path(__file__).resolve().parent
LAB = HERE.parent
CASES = json.loads((HERE / "cases.json").read_text())
SCENES = json.loads((LAB / "reaction/scenes.json").read_text())["scenes"]
RECORDINGS = Path.home() / "recordings"
ROWS, COLUMNS = (670, 683), (64, 244)
NO_BARS = ("loading", "failed", "pause", "map", "wasted", "interaction_menu")
TICK = 1 / 30


def windows():
    """(recording, start, end) of every window to read."""
    out = []
    for scene in SCENES:
        recording = scene["recording"].split("recordings/")[1]
        end = scene["onset"] + (4.0 if scene["kind"] == "calm" else 1.5)
        out.append((recording, scene["onset"] - 7.0, end))
    for case in CASES["cases"]:
        if case["kind"] == "hit":
            out.append((case["recording"], case["first"][1] - 2.5, case["first"][1] + 1.2))
    out += [(r, t0, t1) for r, t0, t1 in CASES["fights"]]
    out += [(r, t0, t1) for r, t0, t1, _ in CASES["more"]]
    return out


def stretches():
    """The windows merged where they overlap, per recording, in a fixed order."""
    merged = []
    for recording in sorted({w[0] for w in windows()}):
        spans = sorted((t0, t1) for r, t0, t1 in windows() if r == recording)
        current = list(spans[0])
        for t0, t1 in spans[1:]:
            if t0 <= current[1]:
                current[1] = max(current[1], t1)
            else:
                merged.append((recording, *current))
                current = [t0, t1]
        merged.append((recording, *current))
    return merged


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


def orange(strip):
    """Columns of the health track the game paints orange over the lost part of a hit."""
    r, g, b = strip[6:10, :89].astype(np.int16).transpose(2, 0, 1)
    paint = (r > 140) & (r - g > 40) & (g - b > 12) & (g > 70)
    return int((paint.sum(axis=0) >= 2).sum())


def signal(times, screens, readings):
    """The hits of a fresh Hits over the ticks, and the reflex's one-frame falls (P62 and P64:
    one reading lower than the last by more than 0.03)."""
    hits, falls, last = Hits(), [], None
    found = []
    for t, screen, (health, armour, special) in zip(times, screens, readings, strict=True):
        hit = hits.update(t, Hud(health=health, armour=armour, special=special, screen=screen))
        if hit is not None:
            found.append({"time": hit.time, "since": hit.since, "before": hit.before, "after": hit.after})
        if health is not None:
            if last is not None and health < last - 0.03:
                falls.append({"time": t, "from": last, "to": health})
            last = health
    return found, falls


def run(out, part, old_path):
    readers = {"new": hud}
    if old_path:
        spec = importlib.util.spec_from_file_location("hud_old", old_path)
        readers["old"] = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(readers["old"])
    k, n = map(int, part.split("/"))
    with open(out, "a") as sink:
        for number, (recording, t0, t1) in enumerate(stretches()):
            if number % n != k - 1:
                continue
            root = RECORDINGS / recording
            rows = [
                json.loads(line) for line in (root / "frames.jsonl").read_text().splitlines() if line.strip()
            ]
            rows = [row for row in rows if t0 <= row["t"] <= t1]
            capture = cv2.VideoCapture(str(root / "video.mp4"))
            capture.set(cv2.CAP_PROP_POS_FRAMES, rows[0]["i"])
            times, screens, strips, readings = [], [], [], {name: [] for name in readers}
            frame = np.zeros((720, 1280, 3), np.uint8)
            for row in rows:
                ok, bgr = capture.read()
                if not ok:
                    break
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                screen = hud.read(rgb).screen
                strip = rgb[ROWS[0] : ROWS[1], COLUMNS[0] : COLUMNS[1]].copy()
                frame[ROWS[0] : ROWS[1], COLUMNS[0] : COLUMNS[1]] = strip
                for name, module in readers.items():
                    bars = (None, None, None) if screen in NO_BARS else module._bars(frame)
                    readings[name].append(bars)
                times.append(row["t"])
                screens.append(screen)
                strips.append(strip)
            picked = ticks(times)
            result = {"recording": recording, "t0": t0, "t1": t1, "frames": len(times)}
            result["ticks"] = [times[j] for j in picked]
            for name in readers:
                hits, falls = signal(
                    [times[j] for j in picked],
                    [screens[j] for j in picked],
                    [readings[name][j] for j in picked],
                )
                for h in hits:
                    h["orange"] = max(
                        orange(strips[j]) for j in range(len(times)) if 0 <= times[j] - h["since"] <= 0.15
                    )
                health = [v[0] for v in readings[name]]
                result[name] = {
                    "hits": hits,
                    "falls": falls,
                    "read": sum(v is not None for v in health),
                    "under_0.1": sum(v is not None and v < 0.1 for v in health),
                }
            sink.write(json.dumps(result) + "\n")
            print(
                recording,
                f"{t0:.1f}-{t1:.1f}",
                len(times),
                "frames",
                len(result["new"]["hits"]),
                "hits",
                flush=True,
            )


def summary(paths):
    results = [json.loads(line) for path in paths for line in Path(path).read_text().splitlines() if line]
    labels = ["new"] + (["old"] if all("old" in r for r in results) else [])
    by_recording = {}
    for r in results:
        by_recording.setdefault(r["recording"], []).append(r)
    print("stretches", len(results), "frames", sum(r["frames"] for r in results))
    for label in labels:
        print(f"[{label}] health read on {sum(r[label]['read'] for r in results)} frames,", end=" ")
        print(f"under 0.1 on {sum(r[label]['under_0.1'] for r in results)}")

    def stretch(recording, t):
        return next(r for r in by_recording[recording] if r["t0"] <= t <= r["t1"])

    hits = [case for case in CASES["cases"] if case["kind"] == "hit"]
    for label in labels:
        matched, delays, rows = set(), [], []
        for case in hits:
            t = case["first"][1]
            r = stretch(case["recording"], t)
            first = next(k for k, tick in enumerate(r["ticks"]) if tick >= t - 0.003)
            found = next(
                (h for h in r[label]["hits"] if h["since"] >= t - 0.003 and h["time"] <= t + 1.0), None
            )
            if found is None:
                rows.append(f"  missed {case['name']} {case['shows']}")
                continue
            matched.add((case["recording"], found["time"]))
            delay = r["ticks"].index(found["time"]) - first
            delays.append(delay)
            if delay > 6:
                rows.append(f"  late by {delay} ticks {case['name']} {case['shows']}")
        within = sum(d <= 6 for d in delays)
        print(f"[{label}] real hits signalled within six ticks: {within} of {len(hits)};", end=" ")
        print(f"delays {sorted(delays)}")
        print("\n".join(rows))
        quiet, onsets, fall_quiet, fall_onsets = [], [], [], []
        for scene in SCENES:
            recording = scene["recording"].split("recordings/")[1]
            lo = scene["onset"] - 6
            hi = scene["onset"] + 4 if scene["kind"] == "calm" else scene["onset"]
            r = stretch(recording, scene["onset"] - 3)
            signals = [h for h in r[label]["hits"] if lo <= h["time"] < hi]
            falls = [f for f in r[label]["falls"] if lo <= f["time"] < hi]
            (quiet if scene["kind"] == "calm" else onsets).extend((scene["id"], h["time"]) for h in signals)
            (fall_quiet if scene["kind"] == "calm" else fall_onsets).extend(scene["id"] for _ in falls)
        print(f"[{label}] hit signals in the 29 calm scenes: {len(quiet)} {quiet}")
        print(f"[{label}] hit signals in the six seconds before the 26 onsets: {len(onsets)} {onsets}")
        print(f"[{label}] one-frame falls: calm {len(fall_quiet)} in {len(set(fall_quiet))} scenes,", end=" ")
        print(f"before onsets {len(fall_onsets)} in {len(set(fall_onsets))} scenes")
        for recording, t0, t1, name in CASES["more"]:
            r = stretch(recording, (t0 + t1) / 2)
            signals = [
                (round(h["since"], 3), round(h["before"], 3), round(h["after"], 3)) for h in r[label]["hits"]
            ]
            print(f"[{label}] {name}: {[s for s in signals if t0 <= s[0] <= t1]}")
        others = [
            (r["recording"], h)
            for r in results
            for h in r[label]["hits"]
            if (r["recording"], h["time"]) not in matched
            and any(rec == r["recording"] and t0 <= h["time"] <= t1 for rec, t0, t1 in CASES["fights"])
        ]
        painted = [h for _, h in others if h["orange"] >= 3]
        print(f"[{label}] signals in the fight stretches that match no labelled hit: {len(others)},", end=" ")
        print(f"{len(painted)} with the orange of a hit on the frames after; the others:")
        for recording, h in others:
            if h["orange"] < 3:
                print(f"    {recording} {h['since']:.3f} {h['before']:.3f} -> {h['after']:.3f}")


def timing(old_path, repeats):
    spec = importlib.util.spec_from_file_location("hud_old", old_path)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    paths = sorted((LAB / "hud/fixtures").glob("*.png")) + sorted(
        (LAB.parent / "pilot/tests/fixtures/screens").glob("*.png")
    )
    frames = [cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2RGB) for p in paths]
    frames = [f for f in frames if f.shape == (720, 1280, 3)]
    spent = {"old": [], "new": []}
    for f in frames:
        for _ in range(3):
            old.read(f)
            hud.read(f)
        for name, read in (("old", old.read), ("new", hud.read)):
            start = time.perf_counter_ns()
            for _ in range(repeats):
                read(f)
            spent[name].append((time.perf_counter_ns() - start) / repeats / 1e6)
    for name, values in spent.items():
        print(f"{name}: {len(values)} frames, mean {np.mean(values):.4f} ms, median {median(values):.4f} ms")
    print(f"new / old: mean {np.mean(spent['new']) / np.mean(spent['old']):.3f}")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    one = sub.add_parser("run")
    one.add_argument("out")
    one.add_argument("--part", default="1/1")
    one.add_argument("--old")
    two = sub.add_parser("summary")
    two.add_argument("paths", nargs="+")
    three = sub.add_parser("time")
    three.add_argument("--old", required=True)
    three.add_argument("--repeats", type=int, default=200)
    args = parser.parse_args()
    if args.mode == "run":
        run(args.out, args.part, args.old)
    elif args.mode == "summary":
        summary(args.paths)
    else:
        timing(args.old, args.repeats)


if __name__ == "__main__":
    main()
