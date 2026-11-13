"""P84's unmet acceptance check, run explicitly from the repository root.

Both the unchanged controller and the lab-only proposal exceed the limit.
This deliberately failing experiment is outside pilot's production test gate.
"""

import gzip
import json
from pathlib import Path

import pytest
from analyze import drive, flips, replay
from proposed_target import fitted_target


@pytest.fixture(scope="module")
def recordings():
    fixture = json.loads(
        gzip.decompress(
            Path(__file__).with_name("recorded-straights.json.gz").read_bytes()
        )
    )
    rows = fixture["rows"]
    return rows, {
        name: replay(rows, target)
        for name, target in [("current", drive._target), ("proposal", fitted_target)]
    }


@pytest.mark.parametrize("start", [150, 180])
@pytest.mark.parametrize("variant", ["current", "proposal"])
def test_no_more_than_two_side_changes(recordings, start, variant):
    rows, commands = recordings
    window = []
    for row, steer in zip(rows, commands[variant], strict=True):
        reading = row["reading"]
        if (
            start <= row["t"] < start + 15
            and not reading["corrupt"]
            and len(reading["path"]) >= 2
            and reading["arrow"] is not None
            and reading["bearing"] is not None
        ):
            window.append((row["t"], steer))
    assert len(window) >= 350, "The recorded straight stretch must remain represented"
    times, steering = zip(*window, strict=True)
    count = len(flips(times, steering))
    assert count <= 2, (
        f"{variant}, {start}-{start + 15}s: {count} side changes; target <=2"
    )
