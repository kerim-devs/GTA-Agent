"""Recorded-label regression, including route paint and translucent backgrounds."""

import json
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

from pilot.contract import Reading
from pilot.minimap import read


def test_recorded_blip_quality_and_json_contract():
    root = Path(__file__).resolve().parents[2]
    with np.load(root / "lab/blips/crops.npz") as data:
        crops = dict(zip(data["ids"].tolist(), data["crops"], strict=True))
    labels = []
    for name in ("flat", "vehicle"):
        labels.extend(json.loads((root / f"lab/blips/{name}-labels.json").read_text()))
    assert len(labels) == 80 and len({row["id"] for row in labels}) == 80
    assert sum(bool(row["blips"]) for row in labels) == 40
    counts = {color: [0, 0, 0, []] for color in ("blue", "red", "yellow")}
    for row in labels:
        result = read(crops[row["id"]])
        json.dumps(asdict(result))  # numpy bools must not escape into the head request.
        remaining = list(result.blips)
        for color, x, y in row["blips"]:
            choices = [
                (float(np.hypot(b.x + 123 - x, 117 - b.y - y)), i)
                for i, b in enumerate(remaining)
                if b.color == color
            ]
            if choices and min(choices)[0] <= 5:
                error, index = min(choices)
                counts[color][0] += 1
                counts[color][3].append(error)
                remaining.pop(index)
            else:
                counts[color][1] += 1
        for extra in remaining:
            counts[extra.color][2] += 1
    for color, (found, missed, invented, errors) in counts.items():
        assert found / (found + missed) >= 0.9, (color, counts[color])
        assert invented / (found + invented) <= 0.05, (color, counts[color])
        assert np.median(errors) < 3, (color, errors)


def test_reading_positional_defaults_and_pinned_marker():
    assert Reading("none", "none", None, None, None, False, 0).blips == ()
    assert read(np.zeros((5, 5, 3), np.uint8)).blips == ()
    root = Path(__file__).resolve().parents[2]
    with np.load(root / "lab/blips/crops.npz") as data:
        crops = dict(zip(data["ids"].tolist(), data["crops"], strict=True))
    target = next(b for b in read(crops[843]).blips if b.color == "yellow")
    assert target.border and target.x < 0 and target.y > 0


def test_a_damaged_frame_reports_no_blips():
    fixture = Path(__file__).parent / "fixtures/crop_2099.png"
    result = read(cv2.cvtColor(cv2.imread(str(fixture)), cv2.COLOR_BGR2RGB))
    assert result.corrupt and result.blips == ()
