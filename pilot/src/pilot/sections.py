"""Offline, conservative sections on the recording's frame clock."""

import json
import math
from bisect import bisect_left, bisect_right
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from pilot.contract import Hud, Pad, Reading
from pilot.hud import read as read_hud
from pilot.minimap import read as read_minimap
from pilot.replay import hud_crop

SAMPLE_HZ = 10
KINDS = {"drive", "foot", "cutscene", "menu", "banner", "loading", "unknown"}
MENUS = {"pause", "map", "interaction_menu", "phone", "weapon_wheel"}
BANNERS = {"passed", "failed", "wasted", "busted"}


@dataclass(frozen=True)
class Sample:
    time: float
    frame: int
    reading: Reading
    hud: Hud
    pad: Pad | None = None


def decide(sample: Sample) -> str:
    """Replace this function with judge answers without changing segmentation."""
    reading, hud, pad = sample.reading, sample.hud, sample.pad
    if reading.corrupt:
        return "unknown"
    if hud.screen in MENUS:
        return "menu"
    if hud.screen in BANNERS:
        return "banner"
    if hud.screen == "loading":
        return "loading"
    if hud.screen != "game":
        return "unknown"
    if reading.minimap == "none":
        return "unknown"
    if pad is not None:
        running = "cross" in {button.lower() for button in pad.buttons}
        moving = math.hypot(*pad.left) > 0.2
        steering = abs(pad.left[0]) > 0.2
        trigger = max(pad.r2, pad.l2) > 0.2
        if running and moving and not trigger:
            return "foot"
        if reading.minimap == "tilted" and trigger and steering and not running:
            return "drive"
    if reading.minimap == "flat":
        return "foot"
    if reading.minimap == "tilted" and hud.wanted == 0:
        return "drive"
    return "unknown"


def frame_rows(recording: Path) -> list[dict]:
    rows = [
        json.loads(line) for line in (recording / "frames.jsonl").read_text().splitlines() if line.strip()
    ]
    previous = -math.inf
    for index, row in enumerate(rows):
        if row["i"] != index or not math.isfinite(row["t"]) or row["t"] <= previous:
            raise ValueError("frames.jsonl must have contiguous indices and increasing finite times")
        previous = row["t"]
    return rows


def sample_indices(rows: Iterable[dict]) -> list[int]:
    """Choose at most one source frame per 100 ms, without assuming video FPS."""
    selected = []
    deadline = None
    for row in rows:
        timestamp = row["t"]
        if deadline is None:
            deadline = timestamp
        if timestamp + 1e-9 >= deadline:
            selected.append(row["i"])
            deadline += (math.floor((timestamp - deadline + 1e-9) * SAMPLE_HZ) + 1) / SAMPLE_HZ
    return selected


def controller_events(recording: Path) -> list[tuple[float, Pad]]:
    path = recording / "pad.jsonl"
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    rows = [row for row in rows if row.get("src") == "human"]
    if len(rows) <= 1:
        return []
    return sorted(
        (
            (
                float(row["t"]),
                Pad(
                    buttons=tuple(row.get("buttons", [])),
                    left=tuple(row.get("left", [0, 0])),
                    right=tuple(row.get("right", [0, 0])),
                    l2=row.get("l2", 0),
                    r2=row.get("r2", 0),
                ),
            )
            for row in rows
        ),
        key=lambda event: event[0],
    )


def active(pad: Pad) -> bool:
    return bool(pad.buttons or any(pad.left) or any(pad.right) or pad.l2 or pad.r2)


def human_share(start: float, end: float, events: list[tuple[float, Pad]]) -> float | None:
    if not events:
        return None
    times = [event[0] for event in events]
    index = bisect_right(times, start) - 1
    pad = events[index][1] if index >= 0 else Pad()
    cursor, held = start, 0.0
    for timestamp, next_pad in events[index + 1 :]:
        if timestamp >= end:
            break
        if active(pad):
            held += timestamp - cursor
        cursor, pad = timestamp, next_pad
    if active(pad):
        held += end - cursor
    return held / (end - start)


def sections(
    samples: list[Sample],
    rows: list[dict],
    events: list[tuple[float, Pad]],
    decision: Callable[[Sample], str] = decide,
) -> list[dict]:
    if not samples or not rows or rows[-1]["t"] - rows[0]["t"] < 1:
        return []
    start, end = rows[0]["t"], rows[-1]["t"]
    boundaries = [(start, "unknown")]
    candidate, since, previous_valid = None, start, -math.inf
    for sample in samples:
        if sample.reading.corrupt:
            continue
        kind = decision(sample)
        if kind not in KINDS:
            raise ValueError(f"Invalid section kind: {kind}")
        if kind == boundaries[-1][1]:
            candidate = None
        else:
            if kind != candidate or sample.time - previous_valid > 0.35:
                candidate, since = kind, sample.time
            if sample.time - since >= 1 - 1e-8:
                if since - boundaries[-1][0] < 1:
                    boundaries[-1] = (boundaries[-1][0], kind)
                else:
                    boundaries.append((since, kind))
                candidate = None
        previous_valid = sample.time
    if len(boundaries) > 1 and end - boundaries[-1][0] < 1:
        boundaries.pop()
    merged = []
    for boundary in boundaries:
        if not merged or boundary[1] != merged[-1][1]:
            merged.append(boundary)
    frame_times = [row["t"] for row in rows]
    sample_times = [sample.time for sample in samples]
    output = []
    for index, (start, kind) in enumerate(merged):
        stop = merged[index + 1][0] if index + 1 < len(merged) else end
        group = samples[
            bisect_left(sample_times, start) : bisect_left(sample_times, stop)
            if stop != end
            else len(samples)
        ]
        valid = [sample for sample in group if not sample.reading.corrupt]
        screens = {}
        for sample in valid:
            screens[sample.hud.screen] = screens.get(sample.hud.screen, 0) + 1
        wanted = [sample.hud.wanted for sample in valid if sample.hud.wanted is not None]
        routes = sorted({sample.reading.route for sample in valid} - {"none"})
        speeds = [
            sample.reading.gps_speed
            for sample in valid
            if sample.reading.gps_speed is not None and math.isfinite(sample.reading.gps_speed)
        ]
        output.append(
            {
                "start": start,
                "end": stop,
                "first_frame": rows[bisect_left(frame_times, start)]["i"],
                "last_frame": rows[(bisect_left(frame_times, stop) - 1) if stop != end else -1]["i"],
                "kind": kind,
                "screen": max(screens, key=screens.get) if screens else "game",
                "wanted": max(wanted) if wanted else None,
                "route": routes,
                "damaged": sum(sample.reading.corrupt for sample in group) / len(group) if group else 0,
                "human": human_share(start, stop, events),
                "route_share": sum(sample.reading.route != "none" for sample in valid) / len(valid)
                if kind == "drive" and valid
                else None,
                "speed": sum(speeds) / len(speeds) if kind == "drive" and speeds else None,
            }
        )
    return output


def analyze(recording: Path, decision: Callable[[Sample], str] = decide) -> dict | None:
    meta = json.loads((recording / "meta.json").read_text())
    if "seconds" not in meta:
        return None
    rows = frame_rows(recording)
    selected = set(sample_indices(rows))
    events = controller_events(recording)
    event_times = [event[0] for event in events]
    samples = []
    cap = cv2.VideoCapture(str(recording / "video.mp4"))
    try:
        for row in rows:
            if not cap.grab():
                raise ValueError(f"Video ends before frame {row['i']}")
            if row["i"] not in selected:
                continue
            ok, bgr = cap.retrieve()
            if not ok:
                raise ValueError(f"Cannot decode frame {row['i']}")
            event_index = bisect_right(event_times, row["t"]) - 1
            pad = (events[event_index][1] if event_index >= 0 else Pad()) if events else None
            rgb = cv2.cvtColor(cv2.resize(bgr, (1280, 720)), cv2.COLOR_BGR2RGB)
            samples.append(Sample(row["t"], row["i"], read_minimap(hud_crop(bgr)), read_hud(rgb), pad))
    finally:
        cap.release()
    return {
        "recording": str(recording.resolve()),
        "seconds": meta["seconds"],
        "sample_hz": SAMPLE_HZ,
        "has_pad": bool(events),
        "sections": sections(samples, rows, events, decision),
    }


def contact_sheet(recording: Path, result: dict, path: Path) -> None:
    rows = frame_rows(recording)
    times = [row["t"] for row in rows]
    targets = {}
    for index, section in enumerate(result["sections"]):
        target = bisect_left(times, (section["start"] + section["end"]) / 2)
        targets[target] = (index, section)
    width, height, columns = 320, 206, 4
    canvas = np.zeros(
        (max(1, math.ceil(len(targets) / columns)) * height, columns * width, 3), dtype=np.uint8
    )
    cap = cv2.VideoCapture(str(recording / "video.mp4"))
    try:
        for target, (index, section) in targets.items():
            cap.set(cv2.CAP_PROP_POS_FRAMES, target)
            ok, bgr = cap.read()
            if not ok:
                raise ValueError(f"Cannot decode contact frame {target}")
            x, y = index % columns * width, index // columns * height
            canvas[y : y + 180, x : x + width] = cv2.resize(bgr, (width, 180))
            label = f"{section['kind']} {section['start']:.1f}-{section['end']:.1f}s"
            cv2.putText(canvas, label, (x + 5, y + 198), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    finally:
        cap.release()
    if not cv2.imwrite(str(path), canvas):
        raise OSError(f"Cannot write {path}")
