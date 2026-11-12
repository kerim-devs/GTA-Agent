import json

import cv2
import numpy as np
import pytest

from pilot.contract import HUD_RECT, Command, Reading
from pilot.loop import Pipeline
from pilot.replay import compare, run_replay


def write_lines(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def recording(tmp_path, count=18, note="wired"):
    writer = cv2.VideoWriter(str(tmp_path / "video.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 10, (1280, 720))
    assert writer.isOpened(), "The installed OpenCV must provide its mp4v writer"
    x, y, w, h = HUD_RECT
    try:
        for _ in range(count):
            bgr = np.zeros((720, 1280, 3), np.uint8)
            bgr[y : y + h, x : x + w] = (40, 80, 160)
            writer.write(bgr)
    finally:
        writer.release()
    write_lines(
        tmp_path / "frames.jsonl",
        [{"i": i, "frame_id": 700 + i, "t": 3 + i / 10} for i in range(count)],
    )
    write_lines(tmp_path / "pad.jsonl", [])
    (tmp_path / "meta.json").write_text(json.dumps({"note": note}))


def test_replay_known_agreement_shift_rgb_crop_and_frame_times(tmp_path, capsys):
    values = [
        0.6,
        0.7,
        -0.8,
        0.9,
        -0.6,
        -0.7,
        -0.9,
        0.8,
        0.6,
        -0.8,
        0.9,
        -0.7,
        0.7,
        0.8,
        0.9,
        -0.6,
        -0.8,
        0.6,
    ]
    recording(tmp_path, note="Wi-Fi test")
    human = [0, 0, *values[:-2]]
    write_lines(
        tmp_path / "pad.jsonl",
        [{"t": 3 + i / 10, "src": "human", "left": [value, 0]} for i, value in enumerate(human)]
        + [{"t": 3.01, "src": "agent", "left": [1, 0]}],
    )
    times = []
    motions = []

    def read(crop):
        assert crop.shape == (170, 260, 3)
        assert crop.dtype == np.uint8
        np.testing.assert_allclose(crop[80, 130], [160, 80, 40], atol=8)
        return Reading("tilted", "yellow", 0, 0, 0, False, 1)

    class Driver:
        def step(self, reading, t, moving, speed=None):
            times.append(t)
            return Command(values[len(times) - 1], 0.4, 0, "follow")

    def motion(a, b):
        motions.append((a.shape, b.shape))
        return 2

    result = run_replay(tmp_path, pipeline=Pipeline(reader=read, motion=motion, driver=Driver()))
    assert result.ticks == 16
    assert result.agreement == pytest.approx(7 / 16)
    assert result.shift == pytest.approx(0.2)
    assert result.correlation == pytest.approx(1)
    assert result.shift_ticks == 16
    assert times == [3 + i / 10 for i in range(18)]
    assert motions
    rows = [json.loads(line) for line in (tmp_path / "pilot-replay.jsonl").read_text().splitlines()]
    assert rows[0]["t"] == 0
    assert rows[0]["frame_id"] == 700
    assert rows[-1]["moving"] is True
    assert all(not row["sent"] and row["status"] is None for row in rows)
    output = capsys.readouterr().out
    assert "Wi-Fi" in output and "do not measure control latency" in output
    assert "sign agreement=0.438 ticks=16" in output
    assert "best shift=+0.200s correlation=1.000 ticks=16" in output


def test_comparison_excludes_flat_no_route_and_small_human_inputs():
    rows = [
        {"time": index, "reading": {"minimap": minimap, "route": route}, "command": {"steer": steer}}
        for index, (minimap, route, steer) in enumerate(
            [
                ("flat", "yellow", -1),
                ("tilted", "none", -1),
                ("tilted", "yellow", -1),
                ("tilted", "yellow", 1),
                ("tilted", "purple", -1),
            ]
        )
    ]
    pad = [{"t": index, "src": "human", "left": [steer, 0]} for index, steer in enumerate([1, 1, 0.4, 1, -1])]
    result = compare(rows, pad)
    assert result.ticks == 2
    assert result.agreement == 1
    assert result.shift is None


def test_comparison_holds_human_state_and_reports_undefined_correlation():
    rows = [
        {"time": i, "reading": {"minimap": "tilted", "route": "yellow"}, "command": {"steer": 0.6}}
        for i in range(5)
    ]
    result = compare(rows, [{"t": 1, "src": "human", "left": [0.7, 0]}])
    assert result.ticks == 4
    assert result.agreement == 1
    assert result.shift is None
    assert compare(rows, []).ticks == 0


def test_replay_rejects_missing_video_frames(tmp_path):
    recording(tmp_path, count=1)
    write_lines(
        tmp_path / "frames.jsonl",
        [{"i": 0, "frame_id": 1, "t": 0}, {"i": 1, "frame_id": 2, "t": 0.1}],
    )

    class Driver:
        def step(self, reading, t, moving, speed=None):
            return Command(0, 0, 0, "idle")

    pipeline = Pipeline(
        reader=lambda crop: Reading("none", "none", None, None, None, False, 0), driver=Driver()
    )
    with pytest.raises(ValueError, match="Missing video frame 1"):
        run_replay(tmp_path, out=tmp_path / "custom.jsonl", pipeline=pipeline)


def test_cli_rejects_invalid_duration_without_contacting_bridge(capsys):
    from pilot.cli import main

    with pytest.raises(SystemExit) as error:
        main(["drive", "--seconds", "nan"])
    assert error.value.code == 2
    assert "finite and positive" in capsys.readouterr().err


def test_truth_table_separates_zero_opposite_raw_error_and_state():
    from pilot.replay import truth_table

    def row(time, state, steer, near):
        return {
            "time": time,
            "command": {"state": state, "steer": steer},
            "reading": {"minimap": "tilted", "route": "yellow", "bearing": near, "arrow": 0},
        }

    rows = [
        row(0, "follow", 0, 20),
        row(1, "follow", -0.4, -30),
        row(2, "coast", 0.2, 3),
        row(3, "coast", 0, None),
    ]
    pad = [{"t": 0, "src": "human", "left": [0.8, 0]}, {"t": 1, "src": "agent", "left": [-1, 0]}]
    table = truth_table(rows, pad)
    assert table["follow"]["command"] == dict(zero=1, same=0, opposite=1, missing=0)
    assert table["follow"]["raw"] == dict(zero=0, same=1, opposite=1, missing=0)
    assert table["coast"]["command"] == dict(zero=1, same=1, opposite=0, missing=0)
    assert table["coast"]["raw"] == dict(zero=1, same=0, opposite=0, missing=1)
    assert truth_table(rows, pad, -1)["follow"]["command"]["opposite"] == 1
    assert truth_table(rows, []) == {}
