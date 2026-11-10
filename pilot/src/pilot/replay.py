"""Offline interpretation of bridge recordings, with human steering comparison."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .contract import FRAME_SIZE, HUD_RECT
from .loop import Pipeline, log_row


def json_lines(path: Path) -> list[dict]:
    with path.open() as source:
        return [json.loads(line) for line in source if line.strip()]


def hud_crop(bgr: np.ndarray) -> np.ndarray:
    height, width = bgr.shape[:2]
    x, y, w, h = HUD_RECT
    sx, sy = width / FRAME_SIZE[0], height / FRAME_SIZE[1]
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    crop = rgb[round(y * sy) : round((y + h) * sy), round(x * sx) : round((x + w) * sx)]
    return cv2.resize(crop, (w, h))


@dataclass(frozen=True)
class Comparison:
    agreement: float | None
    ticks: int
    shift: float | None
    correlation: float | None
    shift_ticks: int


def compare(rows: list[dict], pad: list[dict]) -> Comparison:
    events = sorted((event for event in pad if event["src"] == "human"), key=lambda event: event["t"])
    if not events or not rows:
        return Comparison(None, 0, None, None, 0)
    times = np.array([row["time"] for row in rows])
    steering = np.array([row["command"]["steer"] for row in rows])
    eligible = np.array(
        [row["reading"]["minimap"] == "tilted" and row["reading"]["route"] != "none" for row in rows]
    )
    event_times = np.array([event["t"] for event in events])
    event_values = np.array([event["left"][0] for event in events])

    def aligned(shift):
        sample_times = times + shift
        indices = np.searchsorted(event_times, sample_times + 1e-9, side="right") - 1
        human = event_values[np.maximum(indices, 0)]
        valid = (
            eligible
            & (indices >= 0)
            & (sample_times >= times[0] - 1e-9)
            & (sample_times <= times[-1] + 1e-9)
            & (np.abs(human) > 0.4)
        )
        return steering[valid], human[valid]

    predicted, human = aligned(0)
    count = len(human)
    agreement = float(np.mean(np.sign(predicted) == np.sign(human))) if count else None
    differences = np.diff(times)
    differences = differences[differences > 0]
    if not differences.size:
        return Comparison(agreement, count, None, None, 0)
    step = float(np.median(differences))
    best_shift = best_correlation = None
    best_count = 0
    # Search at frame resolution, bounded to two seconds and at least half the samples.
    for offset in sorted(range(-int(2 / step), int(2 / step) + 1), key=abs):
        shift = offset * step
        predicted, human = aligned(shift)
        if len(human) < max(3, (count + 1) // 2) or np.std(predicted) < 1e-9 or np.std(human) < 1e-9:
            continue
        correlation = float(np.corrcoef(predicted, human)[0, 1])
        if best_correlation is None or correlation > best_correlation + 1e-9:
            best_shift, best_correlation, best_count = shift, correlation, len(human)
    return Comparison(agreement, count, best_shift, best_correlation, best_count)


def run_replay(recording: Path, *, out: Path | None = None, pipeline: Pipeline | None = None) -> Comparison:
    pipeline = Pipeline() if pipeline is None else pipeline
    out = recording / "pilot-replay.jsonl" if out is None else out
    metadata = json_lines(recording / "frames.jsonl")
    pad = json_lines(recording / "pad.jsonl")
    meta = json.loads((recording / "meta.json").read_text())
    if re.search(r"wi[\s\-\u2010-\u2015]?fi", str(meta.get("note", "")), re.IGNORECASE):
        print("Warning: Wi-Fi recording. Steering comparisons are meaningful only on wired recordings.")
    capture = cv2.VideoCapture(str(recording / "video.mp4"))
    rows = []
    try:
        if not capture.isOpened():
            raise ValueError("Cannot open recording video")
        first_time = metadata[0]["t"] if metadata else 0
        previous_time = None
        with out.open("w") as log:
            for index, item in enumerate(metadata):
                if item["i"] != index:
                    raise ValueError("Frame metadata must have contiguous video indices starting at zero")
                frame_time = float(item["t"])
                if previous_time is not None and frame_time <= previous_time:
                    raise ValueError("Frame timestamps must increase")
                previous_time = frame_time
                ok, bgr = capture.read()
                if not ok:
                    raise ValueError(f"Missing video frame {index}")
                reading, moving, command = pipeline.step(hud_crop(bgr), frame_time)
                row = log_row(
                    frame_time - first_time, item["frame_id"], 0.0, frame_time, reading, moving, command
                )
                log.write(json.dumps(row) + "\n")
                rows.append(row)
    finally:
        capture.release()
    result = compare(rows, pad)
    agreement = "unavailable" if result.agreement is None else f"{result.agreement:.3f}"
    shift = "unavailable" if result.shift is None else f"{result.shift:+.3f}s"
    correlation = "unavailable" if result.correlation is None else f"{result.correlation:.3f}"
    print(f"sign agreement={agreement} ticks={result.ticks}")
    print(
        f"best shift={shift} correlation={correlation} ticks={result.shift_ticks} "
        "(positive means human steering follows pilot; search +/-2s)"
    )
    return result
