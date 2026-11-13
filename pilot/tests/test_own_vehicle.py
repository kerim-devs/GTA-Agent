"""Frozen console crops exercise a narrow symbol reader, not vehicle ownership."""

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from pilot.own_vehicle import find_own_vehicle

FIXTURES = Path(__file__).parent / "fixtures" / "own_vehicle"
SAMPLES = json.loads((FIXTURES / "manifest.json").read_text())["samples"]


def crop(name):
    return cv2.cvtColor(cv2.imread(str(FIXTURES / name)), cv2.COLOR_BGR2RGB)


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda row: row["file"])
def test_recorded_symbols_and_abstentions(sample):
    found = find_own_vehicle(crop(sample["file"]))
    if not sample["expected_detection"]:
        assert found is None
        return
    assert found is not None
    x, y = sample["visible_center"]
    assert (found.x + 123, 117 - found.y) == pytest.approx((x, y), abs=2)
    assert found.clipped == (x <= 38 or x >= 209 or y <= 33 or y >= 139)
    assert 0.76 <= found.confidence <= 1


def test_two_separate_car_glyphs_abstain():
    original = crop("201617-0002.png")
    image = np.full_like(original, 128)
    image[50:64, 50:68] = original[51:65, 203:221]
    image[90:104, 170:188] = original[51:65, 203:221]
    assert find_own_vehicle(image) is None


@pytest.mark.parametrize("image", [None, [], np.zeros((170, 260)), np.zeros((170, 260, 3))])
def test_wrong_crop_abstains(image):
    assert find_own_vehicle(image) is None
