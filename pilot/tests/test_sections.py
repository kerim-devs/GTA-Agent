import json

import pytest

from pilot.contract import Hud, Pad, Reading
from pilot.sections import (
    Judge,
    JudgeDownError,
    Sample,
    analyze,
    controller_events,
    decide,
    doubtful,
    frame_rows,
    human_share,
    judge_kind,
    judged_samples,
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


def no_map(duration=8):
    """A recording whose minimap is missing throughout: the readers leave all of it unknown."""
    return [Sample(i / 10, i, reading("none"), Hud(wanted=0)) for i in range(duration * 10 + 1)]


def judge_with(answers):
    """Answers by second, as the judge's questions would give them."""
    return lambda sample: answers.get(int(sample.time))


NEITHER = {"mode": "none", "overlay": False, "banner": False}
ON_FOOT = {"mode": "foot", "overlay": False, "banner": False}


def test_judge_names_a_cutscene_where_the_readers_know_nothing():
    samples = no_map()
    assert [part["kind"] for part in segment(samples)] == ["unknown"]
    answers = {second: NEITHER for second in range(9)}
    result = segment(judged_samples(samples, judge_with(answers)))
    assert [part["kind"] for part in result] == ["cutscene"]


def test_one_odd_answer_decides_nothing():
    answers = {second: NEITHER for second in range(9)}
    answers[4] = ON_FOOT
    samples = judged_samples(no_map(), judge_with(answers))
    assert all(sample.judge is None for sample in samples if int(sample.time) == 4)
    assert "foot" not in {part["kind"] for part in segment(samples)}


def test_two_answers_in_a_row_decide_and_answers_without_neighbours_do_not():
    answers = {2: ON_FOOT, 3: ON_FOOT, 6: NEITHER}
    samples = judged_samples(no_map(), judge_with(answers))
    assert {int(sample.time) for sample in samples if sample.judge} == {2, 3}


def test_unparsable_answers_are_skipped():
    answers = {second: None for second in range(9)}
    assert [part["kind"] for part in segment(judged_samples(no_map(), judge_with(answers)))] == ["unknown"]


def test_judge_asks_one_frame_a_second_and_only_near_what_the_readers_leave_open():
    samples = sequence(20)
    for i in range(80, 101):
        samples[i] = Sample(i / 10, i, reading("none"), Hud(wanted=0))
    asked = []
    judged_samples(samples, lambda sample: asked.append(sample.time) or NEITHER)
    seconds = [int(time) for time in asked]
    assert seconds == sorted(set(seconds))
    assert 8 in seconds and 9 in seconds and 10 in seconds
    assert 0 not in seconds and 19 not in seconds
    assert not any(doubtful(sequence(20)))


def test_doubt_surrounds_a_change_of_mind_and_stars_but_not_the_controller():
    samples = sequence(20)
    for i in range(100, 201):
        samples[i] = Sample(i / 10, i, reading("tilted"), Hud(wanted=0))
    flags = doubtful(samples)
    assert not flags[60] and not flags[150]
    assert flags[80] and flags[120]
    pad = Pad(left=(0.5, 0), r2=1)
    steered = [Sample(i / 10, i, reading("tilted"), Hud(wanted=3), pad) for i in range(60)]
    assert not any(doubtful(steered))
    starred = [Sample(i / 10, i, reading("tilted"), Hud(wanted=3)) for i in range(60)]
    assert starred[0].pad is None and decide(starred[0]) == "unknown"
    assert all(doubtful(starred))


def test_judge_kind():
    assert judge_kind({"mode": "vehicle", "overlay": False, "banner": False}) == "drive"
    assert judge_kind({"mode": "foot", "overlay": True, "banner": False}) == "menu"
    assert judge_kind({"mode": "foot", "overlay": True, "banner": True}) == "banner"
    assert judge_kind(None) is None


def choice(letter):
    return {"message": {"content": letter}}


def test_judge_caches_every_answer_and_a_rerun_asks_nothing(tmp_path):
    calls = []

    def transport(image, name):
        calls.append(name)
        return choice({"banner": "B", "overlay": "B", "mode": "C"}[name])

    judge = Judge("http://192.168.0.248:1234=qwen/qwen3-vl-8b", transport)
    assert judge.ask(7, lambda: "img") == {"banner": False, "overlay": False, "mode": "none", "p": None}
    judge.save(tmp_path / "judge.json")
    again = Judge("http://192.168.0.248:1234=qwen/qwen3-vl-8b", transport)
    again.load(tmp_path / "judge.json")
    calls.clear()
    assert again.ask(7, lambda: pytest.fail("decoded a cached frame"))["mode"] == "none"
    assert calls == []
    other = Judge("http://192.168.0.248:1234=another", transport)
    other.load(tmp_path / "judge.json")
    assert other.cache == {}


def test_judge_that_does_not_answer_stops_the_pass():
    def transport(image, name):
        raise ConnectionRefusedError("down")

    judge = Judge("http://192.168.0.248:1234=m", transport)
    with pytest.raises(JudgeDownError):
        judge.ask(1, lambda: "img")
    assert judge.down


def test_judge_endpoint_must_be_local():
    with pytest.raises(ValueError):
        Judge("http://example.com=m")


def plain_recording(folder, seconds=4, fps=10):
    import cv2
    import numpy as np

    writer = cv2.VideoWriter(str(folder / "video.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), fps, (320, 180))
    noise = np.random.default_rng(0)
    for _ in range(seconds * fps):
        writer.write(noise.integers(60, 200, (180, 320, 3), dtype=np.uint8))
    writer.release()
    (folder / "frames.jsonl").write_text(
        "".join(json.dumps({"i": i, "t": i / fps}) + "\n" for i in range(seconds * fps))
    )
    (folder / "meta.json").write_text(json.dumps({"seconds": seconds}))


def test_a_server_that_does_not_answer_leaves_the_readers_result(tmp_path, capsys):
    plain_recording(tmp_path)

    def down(image, name):
        raise ConnectionRefusedError("down")

    judge = Judge("http://192.168.0.248:1234=m", down)
    result = analyze(tmp_path, judge=judge, folder=tmp_path / "out")
    assert judge.down
    assert "did not answer" in capsys.readouterr().out
    assert result["sections"] == analyze(tmp_path)["sections"]


def test_second_pass_asks_the_server_for_the_frames_the_readers_leave_open(tmp_path):
    plain_recording(tmp_path)
    judge = Judge("http://192.168.0.248:1234=m", lambda image, name: choice({"mode": "C"}.get(name, "B")))
    result = analyze(tmp_path, judge=judge, folder=tmp_path / "out")
    assert [part["kind"] for part in result["sections"]] == ["cutscene"]
    assert len(judge.cache) == 4
    assert (tmp_path / "out" / "judge.json").exists()
