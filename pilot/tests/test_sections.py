import json

import pytest

from pilot.contract import Hud, Pad, Reading
from pilot.sections import (
    Sample,
    analyze,
    controller_events,
    decide,
    frame_rows,
    human_share,
    sample_indices,
    sections,
)


def reading(mode="flat", corrupt=False, route="none", speed=None):
    return Reading(mode, route, None, None, None, corrupt, 1.0, gps_speed=speed)


def sequence(duration=6):
    return [Sample(i / 10, i, reading(), Hud(wanted=0)) for i in range(duration * 10 + 1)]


def segment(samples, **kwargs):
    rows = [{"i": i, "t": sample.time} for i, sample in enumerate(samples)]
    return sections(samples, rows, [], **kwargs)


def test_short_flip_does_not_make_a_section():
    samples = sequence()
    for i in range(20, 29):
        samples[i] = Sample(i / 10, i, reading("tilted"), Hud(wanted=0))
    result = segment(samples)
    assert [(part["kind"], part["start"], part["end"]) for part in result] == [("foot", 0, 6)]


def test_corrupt_readings_cannot_change_kind_even_with_replacement():
    samples = sequence()
    for i in range(20, 41):
        samples[i] = Sample(i / 10, i, reading("tilted", True), Hud(screen="failed"))
    result = segment(samples, decision=lambda sample: "drive" if sample.reading.corrupt else "foot")
    assert len(result) == 1
    assert result[0]["kind"] == "foot"
    assert result[0]["damaged"] == pytest.approx(21 / 61)


def test_single_outlier_after_corruption_does_not_confirm_change():
    samples = sequence()
    for i in range(20, 36):
        samples[i] = Sample(i / 10, i, reading("tilted", i not in (20, 35)), Hud(wanted=0))
    assert [part["kind"] for part in segment(samples)] == ["foot"]


@pytest.mark.parametrize(
    "rows", [[], [{"t": 0, "src": "human"}], [{"t": 0, "src": "pilot"}, {"t": 1, "src": "pilot"}]]
)
def test_no_human_controller(tmp_path, rows):
    (tmp_path / "pad.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    assert controller_events(tmp_path) == []
    result = segment(sequence())
    assert result[0]["human"] is None
    assert decide(Sample(0, 0, reading("tilted"), Hud(wanted=0))) == "drive"


def test_frame_clock_sampling_handles_gaps(tmp_path):
    times = [2, 2.03, 2.1, 2.12, 5.31, 5.32, 5.41]
    (tmp_path / "frames.jsonl").write_text(
        "".join(json.dumps({"i": i, "t": t}) + "\n" for i, t in enumerate(times))
    )
    rows = frame_rows(tmp_path)
    assert sample_indices(rows) == [0, 2, 4, 6]
    samples = [Sample(t, i, reading(), Hud(wanted=0)) for i, t in enumerate(times)]
    result = sections(samples, rows, [], decision=lambda _: "foot")
    assert result[0]["start"] == 2
    assert result[-1]["end"] == 5.41
    assert [part["kind"] for part in result] == ["unknown"]


def test_neighbours_with_same_kind_merge_across_menu_screens():
    samples = [Sample(i / 10, i, reading(), Hud(screen="pause" if i < 30 else "map")) for i in range(61)]
    assert [part["kind"] for part in segment(samples)] == ["menu"]


def test_replaceable_decision_uses_source_time_and_confirmed_boundaries():
    result = segment(sequence(), decision=lambda sample: "drive" if 2 <= sample.time < 4 else "foot")
    assert [(part["kind"], part["start"], part["end"]) for part in result] == [
        ("foot", 0, 2),
        ("drive", 2, 4),
        ("foot", 4, 6),
    ]
    assert [(part["first_frame"], part["last_frame"]) for part in result] == [(0, 19), (20, 39), (40, 60)]
    assert all(part["end"] - part["start"] >= 1 for part in result)


def test_wanted_tilt_needs_controller_evidence():
    base = dict(time=0, frame=0, reading=reading("tilted"), hud=Hud(wanted=2))
    assert decide(Sample(**base)) == "unknown"
    assert decide(Sample(**base, pad=Pad(left=(0.5, 0), r2=1))) == "drive"
    assert decide(Sample(**base, pad=Pad(left=(0, -1), buttons=("cross",)))) == "foot"


def test_missing_map_is_not_assumed_to_be_a_cutscene():
    sample = Sample(0, 0, reading("none"), Hud())
    assert decide(sample) == "unknown"
    result = segment(sequence(), decision=lambda _: "cutscene")
    assert [part["kind"] for part in result] == ["cutscene"]


def test_human_share_integrates_events_not_event_counts():
    events = [(0, Pad()), (0.25, Pad(r2=1)), (1.75, Pad())]
    assert human_share(0, 2, events) == 0.75
    assert human_share(0.5, 1.5, events) == 1


def test_drive_statistics_exclude_damaged_readings():
    samples = [
        Sample(i / 10, i, reading("tilted", i == 10, "purple", 10 if i != 10 else 999), Hud(wanted=0))
        for i in range(31)
    ]
    result = segment(samples)[0]
    assert result["speed"] == 10
    assert result["route_share"] == 1
    assert result["route"] == ["purple"]
    assert set(result) == {
        "start",
        "end",
        "first_frame",
        "last_frame",
        "kind",
        "screen",
        "wanted",
        "route",
        "damaged",
        "human",
        "route_share",
        "speed",
    }


def test_unfinished_recording_is_left_alone(tmp_path):
    (tmp_path / "meta.json").write_text("{}")
    assert analyze(tmp_path) is None
    assert list(tmp_path.iterdir()) == [tmp_path / "meta.json"]
