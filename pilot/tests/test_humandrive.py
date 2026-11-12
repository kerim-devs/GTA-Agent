from dataclasses import asdict

import numpy as np
import pytest

from pilot.contract import Reading
from pilot.drive import DriveConfig
from pilot.gps import Fix, Speedometer
from pilot.humandrive import (
    analyze,
    controller_lines,
    estimate_lead,
    gps_reading,
    json_lines,
    replay_readings,
    sample_frames,
)


def reading(bearing=25):
    return asdict(Reading("tilted", "purple", bearing, bearing, 0, False, 1))


def pad(t, stick=0.6, source="human"):
    return {"t": t, "src": source, "left": [stick, 0], "r2": 0.8, "l2": 0}


def test_lead_from_visual_response_with_independent_driver_commands():
    rng = np.random.default_rng(40)
    sticks = rng.choice([-0.8, -0.4, 0.4, 0.8], 120)
    pads = [pad(i * 0.2, stick) for i, stick in enumerate(sticks)]
    lead = 0.6
    rows = []
    heading = 0
    # Integrate a known delayed vehicle response; driver output is deliberately absent.
    for i in range(720):
        t = i / 30
        input_t = t - lead - 1 / 60
        stick = sticks[min(int(input_t / 0.2), len(sticks) - 1)] if input_t >= 0 else 0
        heading -= stick * 20 / 30
        rows.append({"t": t, "reading": reading(heading)})
    estimate = estimate_lead(rows, pads)
    assert estimate["resolved"]
    assert estimate["seconds"] == pytest.approx(lead, abs=1 / 30)


@pytest.mark.parametrize("pads", [[], [{"t": 0, "src": "human", "left": [0, 0], "r2": 0, "l2": 0}]])
def test_no_hand_has_no_metrics(pads):
    result = analyze([{"t": 0, "reading": reading()}], pads, DriveConfig())
    assert result["status"] == "skipped"
    assert result["metrics"] is None
    assert result["route_seconds"] == 0


def test_only_sustained_clear_moments_count():
    rows = [{"t": i / 30, "reading": reading()} for i in range(60)]
    pads = [pad(0, 0.2), pad(0.4, -0.8), pad(0.6, 0.2), pad(1.0, 0.8), pad(1.5, 0.2)]
    result = analyze(rows, pads, DriveConfig(), lead=0)
    assert result["metrics"]["route_seconds"] == pytest.approx(2)
    assert result["metrics"]["clear_seconds"] == pytest.approx(0.5)
    assert result["metrics"]["clear_moments"] == 1
    assert result["metrics"]["direction_seconds_share"] == 1
    assert result["metrics"]["moment_direction_share"] == 1


def test_capture_clock_sampling_and_gaps(tmp_path):
    frames = tmp_path / "frames.jsonl"
    frames.write_text(
        "\n".join(
            f'{{"i": {i}, "frame_id": {100 + i}, "t": {t}}}'
            for i, t in enumerate([0, 0.01, 0.034, 0.067, 2, 2.034, 2.067])
        )
    )
    sampled = list(sample_frames(json_lines(frames)))
    assert [f["i"] for f in sampled] == [0, 2, 3, 4, 5, 6]
    assert [f["t"] for f in sampled] == [0, 0.034, 0.067, 2, 2.034, 2.067]
    result = analyze([{**f, "reading": reading()} for f in sampled], [pad(-1)], DriveConfig(), lead=0)
    assert result["route_seconds"] == pytest.approx(0.067 * 2 + 2 / 30)
    assert result["metrics"]["clear_moments"] == 0
    assert len(result["route_stretches"]) == 2


def test_sections_and_agent_source():
    pads = controller_lines([pad(0, source="human"), pad(0, source="agent")], "agent")
    assert len(pads) == 1
    assert pads[0]["src"] == "agent"
    rows = [{"t": i / 30, "reading": reading()} for i in range(30)]
    result = analyze(
        rows, pads, DriveConfig(), lead=0, sections=[{"start": 0.3, "end": 0.8, "kind": "drive"}]
    )
    assert result["route_seconds"] == pytest.approx(0.5)


def test_unobservable_lag_preserves_route_free_footage():
    rd = {**reading(), "route": "none", "bearing": None, "far_bearing": None}
    rows = [{"t": i / 30, "reading": rd} for i in range(30)]
    result = analyze(rows, [pad(-1)], DriveConfig())
    assert not result["alignment"]["resolved"]
    assert result["alignment"]["seconds"] is None
    assert result["route_seconds"] == 0
    assert result["no_route_stretches"] == [{"start": 0, "end": 1, "seconds": 1}]


def test_wifi_frame_gaps_preserve_speed_measurement_until_real_discontinuity():
    speedometer = Speedometer()
    rd = Reading(**reading())
    for t in (0, 0.25, 0.5, 0.75, 1.0, 1.25):
        result = gps_reading(rd, speedometer, t, Fix(100 - 10 * t, None, 1))
    assert result.gps_speed == pytest.approx(10)
    assert result.gps_distance == pytest.approx(87.5)
    assert gps_reading(rd, speedometer, 5, Fix(50, None, 1)).gps_speed is None


def test_short_capture_gap_does_not_restart_steering():
    rows = [
        {"t": t, "reading": reading(bearing)}
        for t, bearing in ((0, 25), (0.033, 25), (0.067, 25), (0.25, -25))
    ]
    rows = replay_readings(rows, DriveConfig(steer_smoothing=1))
    # A real controller cannot instantly reverse its smoothed steering across a lost frame.
    assert 0 < rows[-1]["command"]["steer"] < rows[-2]["command"]["steer"]
