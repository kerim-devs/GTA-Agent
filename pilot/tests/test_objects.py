import json
import subprocess
import sys
from pathlib import Path
from threading import Event
from time import perf_counter, sleep

import cv2
import numpy as np
import pytest

from pilot.contract import Detection
from pilot.objects import Detector, Reader

ROOT = Path(__file__).resolve().parents[2]


def frame(number):
    path = ROOT / "lab" / "objects" / "frames" / f"{number:03}.jpg"
    return cv2.cvtColor(cv2.imread(str(path)), cv2.COLOR_BGR2RGB)


@pytest.fixture(scope="module")
def detector():
    return Detector()


def iou(a, b):
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    return intersection / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection)


def test_real_traffic_and_player_exclusion(detector):
    traffic = frame(6)
    original = traffic.copy()
    detections = detector(traffic)
    assert any(d.kind == "car" and iou(d.box, (441, 295, 620, 401)) > 0.5 for d in detections)
    assert any(d.kind == "truck" and iou(d.box, (0, 29, 239, 402)) > 0.5 for d in detections)
    assert np.array_equal(traffic, original)
    for number, player in [
        (40, (505, 330, 625, 655)),
        (49, (84, 35, 543, 720)),
        (60, (542, 322, 642, 520)),
    ]:
        assert any(iou(d.box, player) > 0.5 for d in detector.detect(frame(number), exclude_player=False))
        assert all(iou(d.box, player) < 0.5 for d in detector(frame(number)))
    assert all(isinstance(d, Detection) and 0 < d.confidence <= 1 for d in detections)


def test_missing_or_corrupt_model_names_fetch_command(tmp_path):
    model = tmp_path / "model.onnx"
    with pytest.raises(RuntimeError, match=r"python tools/fetch_models\.py"):
        Detector(model)
    model.write_bytes(b"not a model")
    with pytest.raises(RuntimeError, match=r"python tools/fetch_models\.py"):
        Detector(model)


@pytest.mark.parametrize("bad", [None, np.zeros((72, 128, 3), np.uint8), np.zeros((720, 1280, 3))])
def test_bad_frames_are_rejected(detector, bad):
    with pytest.raises(ValueError, match="1280x720 RGB uint8"):
        detector(bad)


def test_reader_drops_busy_frames_and_owns_pixels():
    entered, release = Event(), Event()
    calls = []

    def recognize(pixels):
        entered.set()
        assert release.wait(2)
        calls.append(int(pixels[0, 0, 0]))
        return (Detection("car", (20, 30, 140, 100), 0.9),)

    reader = Reader(interval=100, recognizer=recognize)
    pixels = np.zeros((720, 1280, 3), np.uint8)
    try:
        assert reader.poll(pixels, 1) is None
        assert entered.wait(1)
        pixels[:] = 255
        started = perf_counter()
        for tick in range(30):
            assert reader.poll(pixels, 2 + tick / 30) is None
        assert perf_counter() - started < 0.1
        assert calls == []
        release.set()
        deadline = perf_counter() + 2
        result = None
        while result is None and perf_counter() < deadline:
            sleep(0.001)
            result = reader.poll(pixels, 3)
        assert result is not None and result[0] == 1
        assert result[1][0].kind == "car"
        assert calls == [0]
        assert reader.poll(pixels, 4) is None
    finally:
        release.set()
        reader.close()
    assert not reader._thread.is_alive()
    assert reader.poll(pixels, 200) is None


def test_reader_surfaces_failure_and_recovers_after_clock_reset():
    calls = []

    def recognize(pixels):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("bad capture")
        return ()

    pixels = np.zeros((720, 1280, 3), np.uint8)
    reader = Reader(interval=100, recognizer=recognize)
    try:
        reader.poll(pixels, 10)
        deadline = perf_counter() + 2
        while reader.error is None and perf_counter() < deadline:
            sleep(0.001)
        assert reader.poll(pixels, 11) == (10, ())
        assert reader.error == "bad capture"
        reader.poll(pixels, 0)
        while reader.error is not None and perf_counter() < deadline:
            sleep(0.001)
        assert reader.poll(pixels, 1) == (0, ())
        assert reader.error is None
    finally:
        reader.close()


def test_native_memory_is_bounded_over_3000_real_detections():
    result = subprocess.run(
        [sys.executable, "tools/evaluate_objects.py", "--memory-only"],
        cwd=ROOT / "pilot",
        capture_output=True,
        text=True,
        check=True,
        timeout=85,
    )
    memory = json.loads(result.stdout)
    assert memory["detections"] == 3000
    assert memory["passed"], memory
