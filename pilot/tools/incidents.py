"""What went wrong in a recording: deaths, failures, crashes, standstills and the rest, one line each.

    incidents.py <recording>... --out DIR [--texts-root DIR] [--sections-root DIR ...]
    incidents.py --summary DIR

For each recording the HUD reader, the minimap reader and the printed distance are run once over the
video at ten frames a second (cached as DIR/<name>/hud.jsonl), and joined with the texts, the raw
readings and the sections that the earlier tools wrote, and with the controller in pad.jsonl.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from pilot import gps, hud
from pilot.conductor import minimap_crop
from pilot.incidents import attach_to_missions, find_incidents, write_summary
from pilot.minimap import _bars, _blocks
from pilot.minimap import read as read_minimap
from pilot.motion import _BASE, _X0, _X1, _Y0, _Y1
from pilot.notes import read_sections

SAMPLE_SECONDS = 0.1
GPS_SECONDS = 0.5


def jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def car_signature(rgb):
    """Colours under the chase camera, where the player's own vehicle sits: eight hue bins of the
    saturated pixels and the shares of dark and bright ones. Only compared between two drives."""
    patch = cv2.cvtColor(np.ascontiguousarray(rgb[440:640:4, 460:820:4]), cv2.COLOR_RGB2HSV)
    hue, sat, val = patch[..., 0].ravel(), patch[..., 1].ravel(), patch[..., 2].ravel()
    coloured = (sat > 70) & (val > 50)
    bins = np.bincount((hue[coloured].astype(int) * 8) // 180, minlength=8)[:8] / max(hue.size, 1)
    return [round(float(v), 3) for v in (*bins, (val < 40).mean(), (val > 200).mean())]


# The player arrow inside the inset map rectangle of motion.py. The minimap turns about the arrow
# with the camera and zooms about it with speed, so only how far the arrow's point moves is travel.
ARROW = np.array([123.0 - _X0, 117.0 - _Y0])


def map_shift(prev, cur):
    """How far the map moved under the player arrow between two HUD crops, in crop pixels, with the
    turn of the map taken out. motion.map_motion measures every feature's displacement, so a car
    that turns reads as fast as one that drives. None for damaged crops or too little structure."""
    try:
        for crop in (prev, cur):
            if _bars(crop) < 2 or _blocks(crop)[0] >= 2:
                return None
        a = cv2.cvtColor(prev[_Y0:_Y1, _X0:_X1], cv2.COLOR_RGB2GRAY)
        b = cv2.cvtColor(cur[_Y0:_Y1, _X0:_X1], cv2.COLOR_RGB2GRAY)
        points = cv2.goodFeaturesToTrack(
            a, maxCorners=64, qualityLevel=0.015, minDistance=5, mask=_BASE, blockSize=5
        )
        if points is None:
            return None
        forward, status, _ = cv2.calcOpticalFlowPyrLK(a, b, points, None, winSize=(21, 21), maxLevel=3)
        back, back_status, _ = cv2.calcOpticalFlowPyrLK(b, a, forward, None, winSize=(21, 21), maxLevel=3)
        valid = (status.ravel() > 0) & (back_status.ravel() > 0)
        valid &= np.linalg.norm(points - back, axis=2).ravel() < 0.8
        if valid.sum() < 8:
            return None
        matrix, inliers = cv2.estimateAffinePartial2D(
            points[valid], forward[valid], method=cv2.RANSAC, ransacReprojThreshold=1.5
        )
        if matrix is None or inliers.sum() < 6:
            return None
        return float(np.linalg.norm(matrix[:, :2] @ ARROW + matrix[:, 2] - ARROW))
    except cv2.error:
        return None


def trace(recording, destination):
    """One sequential decode at ten samples a second by the times of frames.jsonl."""
    frames = jsonl(recording / "frames.jsonl")
    selected = {}
    target = frames[0]["t"]
    for frame in frames:
        if frame["t"] >= target:
            selected[frame["i"]] = frame["t"]
            while target <= frame["t"]:
                target += SAMPLE_SECONDS
    capture = cv2.VideoCapture(str(recording / "video.mp4"))
    before = None  # (t, crop) of the previous sample
    last_gps = -1e9
    previous = None
    started = time.monotonic()
    path = destination / "hud.jsonl"
    partial = path.with_suffix(".partial")
    try:
        with partial.open("w") as stream:
            for index in range(max(selected) + 1):
                if not capture.grab():
                    break
                if index not in selected:
                    continue
                ok, image = capture.retrieve()
                if not ok:
                    continue
                t = selected[index]
                rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                reading = hud.read(rgb)
                crop = minimap_crop(rgb)
                minimap = read_minimap(crop)
                move = None
                if before is not None and 0.04 <= t - before[0] <= 0.25:
                    value = map_shift(before[1], crop)
                    if value is not None:
                        move = round(value / (t - before[0]), 1)
                before = (t, crop)
                small = rgb[::16, ::16].mean(axis=2)
                change = (
                    None
                    if previous is None or t - previous[0] > 1
                    else round(float(np.abs(small - previous[1]).mean()), 2)
                )
                previous = (t, small)
                row = {
                    "t": round(t, 4),
                    "i": index,
                    "screen": reading.screen,
                    "wanted": reading.wanted,
                    "health": None if reading.health is None else round(reading.health, 3),
                    "map": minimap.minimap,
                    "route": minimap.route,
                    "corrupt": minimap.corrupt,
                    # map travel under the arrow since the previous sample, crop pixels a second
                    "move": move,
                    "red": sum(blip.color == "red" for blip in minimap.blips),
                    "lum": round(float(small.mean()), 1),
                    # mean change of the whole picture since the previous sample; a frozen stream is 0
                    "change": change,
                }
                if minimap.minimap == "tilted":
                    row["car"] = car_signature(rgb)
                    if t - last_gps >= GPS_SECONDS:
                        last_gps = t
                        try:
                            fix = gps.recognize(crop)
                        except Exception:
                            fix = None
                        row["gps"] = None if fix is None else fix.distance
                stream.write(json.dumps(row) + "\n")
                if len(selected) and index % 6000 == 0:
                    print(f"{recording.name}: {t:.0f}s", flush=True)
    finally:
        capture.release()
    partial.rename(path)
    print(f"{recording.name}: hud trace in {time.monotonic() - started:.0f}s", flush=True)


def find_sections(name, roots):
    for root in roots:
        path = Path(root) / name / "sections.json"
        if path.is_file():
            return path
    raise FileNotFoundError(f"Missing sections.json for {name} under {', '.join(map(str, roots))}")


def run(recording, out, texts_root, sections_roots):
    destination = out / recording.name
    destination.mkdir(parents=True, exist_ok=True)
    texts_dir = texts_root / recording.name
    sections = read_sections(find_sections(recording.name, sections_roots))
    texts = jsonl(texts_dir / "texts.jsonl")
    readings = jsonl(texts_dir / "readings.jsonl")
    if not (destination / "hud.jsonl").is_file():
        trace(recording, destination)
    samples = jsonl(destination / "hud.jsonl")
    pad_path = recording / "pad.jsonl"
    pads = jsonl(pad_path) if pad_path.is_file() else []
    missions_path = texts_dir / "missions.json"
    missions = json.loads(missions_path.read_text()) if missions_path.is_file() else {"missions": []}
    incidents = find_incidents(
        samples=samples,
        texts=texts,
        readings=readings,
        sections=sections,
        pads=pads if sections["has_pad"] else [],
        missions=missions,
        seconds=float(json.loads((recording / "meta.json").read_text())["seconds"]),
    )
    (destination / "incidents.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in incidents)
    )
    if missions_path.is_file():
        missions_path.write_text(
            json.dumps(attach_to_missions(missions, incidents), ensure_ascii=False, indent=2) + "\n"
        )
    play = sum(s["end"] - s["start"] for s in sections["sections"] if s["kind"] in ("foot", "drive"))
    (destination / "incidents-meta.json").write_text(
        json.dumps({"seconds": sections["seconds"], "play_seconds": round(play, 1)}, indent=2) + "\n"
    )
    counts = {}
    for row in incidents:
        counts[row["class"]] = counts.get(row["class"], 0) + 1
    print(f"{recording.name}: {len(incidents)} incidents {counts}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recordings", nargs="*", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--texts-root",
        type=Path,
        help="Where <name>/texts.jsonl, readings.jsonl and missions.json lie; --out",
    )
    parser.add_argument(
        "--sections-root",
        type=Path,
        action="append",
        help="Where <name>/sections.json lies; repeatable, the first that has it wins; default --out",
    )
    parser.add_argument("--summary", type=Path, help="Write DIR/incidents.md over every DIR/<name>/")
    args = parser.parse_args()
    if args.summary:
        write_summary(args.summary)
        return
    if not (args.recordings and args.out):
        parser.error("recordings and --out are required")
    failed = False
    for recording in args.recordings:
        try:
            run(recording, args.out, args.texts_root or args.out, args.sections_root or [args.out])
        except (FileNotFoundError, ValueError, KeyError) as error:
            print(f"{recording.name}: incidents failed: {error}", file=sys.stderr, flush=True)
            failed = True
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
