"""Closed-loop held, second-release and unescapable-obstacle recovery contracts."""

import runpy
from itertools import pairwise
from pathlib import Path

import pytest

trial = runpy.run_path(str(Path(__file__).parents[2] / "lab/drive/recovery.py"))["trial"]


@pytest.mark.parametrize(
    "kind,ending,attempts",
    [
        ("held", "dead-or-held", 1),
        ("second-try", "freed", 2),
        ("never-free", "failed-recovery", 3),
    ],
)
def test_recovery_in_delayed_bicycle_simulator(kind, ending, attempts):
    result = trial(kind)
    assert result["ending"] == ending
    assert result["attempts"] == attempts
    reverses = [p for p in result["phases"] if p["state"] == "recovery-reverse"]
    assert all(a["steer"] * b["steer"] < 0 for a, b in pairwise(reverses))
    if kind == "held":
        assert result["seconds"] < 8
        assert result["position"] == [0, 0]
    elif kind == "second-try":
        assert result["position"][1] >= 8
    else:
        assert result["seconds"] < 25
    if ending != "freed":
        last = result["phases"][-1]
        assert last["steer"] == last["throttle"] == last["brake"] == 0
