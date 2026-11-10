"""Real pair calibration and rejection of unusable motion observations."""

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from pilot.motion import MOVING_PX, map_motion

FIXTURES = Path(__file__).parent / "fixtures"
CASES = json.loads((FIXTURES / "expectations.json").read_text())["motion"]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_real_motion_pair(case):
    prev = cv2.cvtColor(cv2.imread(str(FIXTURES / case["prev"])), cv2.COLOR_BGR2RGB)
    cur = cv2.cvtColor(cv2.imread(str(FIXTURES / case["cur"])), cv2.COLOR_BGR2RGB)
    before = prev.copy(), cur.copy()
    motion = map_motion(prev, cur)
    if case["moving"] is None:
        assert motion is None
        # Missing either endpoint cannot be interpreted as a stopped vehicle.
        assert map_motion(cur, prev) is None
    else:
        assert motion is not None and np.isfinite(motion)
        assert (motion > MOVING_PX) is case["moving"]
        if case["moving"]:
            assert 2 < motion < 8
        else:
            assert motion < 0.5
        assert map_motion(prev, prev) == pytest.approx(0, abs=0.05)
    np.testing.assert_array_equal(prev, before[0])
    np.testing.assert_array_equal(cur, before[1])


@pytest.mark.parametrize("value", [0, 255])
def test_featureless_pairs_are_unknown(value):
    crop = np.full((170, 260, 3), value, np.uint8)
    assert map_motion(crop, crop) is None


@pytest.mark.parametrize("seed", range(5))
def test_noise_pair_never_raises(seed):
    rng = np.random.default_rng(seed)
    a, b = rng.integers(0, 256, (2, 170, 260, 3), dtype=np.uint8)
    result = map_motion(a, b)
    assert result is None or (np.isfinite(result) and result >= 0)


@pytest.mark.parametrize("invalid", [None, np.zeros((1, 2, 3), np.uint8), np.zeros((170, 260, 3))])
def test_invalid_endpoint_is_unknown(invalid):
    good = cv2.cvtColor(cv2.imread(str(FIXTURES / "crop_0858.png")), cv2.COLOR_BGR2RGB)
    assert map_motion(good, invalid) is None
    assert map_motion(invalid, good) is None
