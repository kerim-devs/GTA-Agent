"""Measurement regressions, not an acceptance claim for the unchanged driver."""

import gzip
import json
from math import cos, radians, sin
from pathlib import Path

import pytest
from steady import geometry, measure


def row(t, heading, *, course=0):
    return {
        "t": t,
        "reading": {
            "path": [
                (r * sin(radians(course)), r * cos(radians(course)))
                for r in (12, 18, 24, 30, 36, 42, 48, 54, 60)
            ],
            "arrow": course - heading,
        },
        "pad": {"left": [0, 0]},
    }


def test_heading_is_relative_to_road_not_camera():
    assert geometry(row(0, 12, course=45)["reading"])[0] == pytest.approx(12)
    assert geometry(row(0, 12, course=-80)["reading"])[0] == pytest.approx(12)


def test_turn_is_not_measured_as_straight():
    rows = [row(i / 30, 0) for i in range(60)]
    for value in rows:
        value["reading"]["path"] = [(0, 12), (0, 32), (20, 32), (40, 32)]
    assert measure(rows, 0, 2)["samples"] == 0


def test_gap_does_not_turn_two_constant_headings_into_a_swing():
    rows = [row(i / 30, -30) for i in range(60)]
    rows += [row(3 + i / 30, 30) for i in range(60)]
    result = measure(rows, 0, 6)
    assert result["runs"] == 2
    assert result["heading_sd_deg"] == pytest.approx(0)
    assert result["heading_rms_deg"] == pytest.approx(30)


def test_angle_wrap_is_not_a_full_circle_swing():
    rows = [row(i / 30, 179 if i % 2 else -179) for i in range(60)]
    assert measure(rows, 0, 2)["heading_sd_deg"] == pytest.approx(1)


def test_repeated_frames_and_short_fragments_do_not_add_evidence():
    rows = [row(i / 30, 10) for i in range(60)]
    for i, value in enumerate(rows):
        value["frame_id"] = i // 60
    assert measure(rows, 0, 2)["samples"] == 0
    assert measure([row(i / 30, 10) for i in range(15)], 0, 2)["samples"] == 0


def test_recorded_spatial_measure_separates_selected_straights():
    sources = json.loads(
        gzip.decompress(Path(__file__).with_name("p87-recordings.json.gz").read_bytes())
    )
    for source in sources[1:]:
        result = measure(source["rows"], source["start"], source["end"])
        assert result["straight_seconds"] > 4
        assert result["heading_sd_deg"] < 10
    for start in (150, 180):
        result = measure(sources[0]["rows"], start, start + 15)
        assert result["straight_seconds"] > 7
        assert result["heading_sd_deg"] > 20
