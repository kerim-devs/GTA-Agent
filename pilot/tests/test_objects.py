import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from threading import Event
from time import perf_counter, sleep

import cv2
import numpy as np
import pytest

from pilot.contract import Detection
from pilot.objects import Detector, Reader, split_player, without_player

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


@pytest.mark.skipif(
    os.environ.get("PILOT_OBJECTS_MEMORY") != "1", reason="opt-in 3000-inference hardware soak"
)
def test_native_memory_is_bounded_over_3000_real_detections():
    result = subprocess.run(
        [sys.executable, "tools/evaluate_objects.py", "--memory-only"],
        cwd=ROOT / "pilot",
        capture_output=True,
        text=True,
        check=True,
        timeout=900,
    )
    memory = json.loads(result.stdout)
    print(json.dumps(memory))
    assert memory["detections"] == 3000
    assert memory["passed"], memory


def evaluator():
    spec = importlib.util.spec_from_file_location(
        "evaluate_objects", ROOT / "pilot/tools/evaluate_objects.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_vehicle_kind_does_not_hide_a_found_vehicle_at_iou_point_four():
    match = evaluator().match
    truth = {"kind": "truck", "box": (60, 0, 200, 100), "player": False}
    detection = Detection("car", (0, 0, 140, 100), 0.9)
    hits, missed, invented = match([detection], [truth])
    assert hits == [(detection, truth)]
    assert not missed and not invented
    truth["box"] = (61, 0, 201, 100)
    hits, missed, invented = match([detection], [truth])
    assert not hits and missed == [truth] and invented == [detection]


def test_invented_requires_a_label_sized_box_with_nothing_under_it():
    match = evaluator().match
    truth = {"kind": "car", "box": (0, 0, 140, 100), "player": False}
    duplicate = Detection("car", truth["box"], 0.8)
    distant = Detection("truck", (300, 0, 440, 100), 0.9)
    small = Detection("person", (500, 0, 510, 40), 0.9)
    hits, missed, invented = match(
        [Detection("truck", truth["box"], 0.9), duplicate, distant, small], [truth]
    )
    assert len(hits) == 1 and not missed
    assert invented == [distant]


def test_invented_fraction_counts_only_label_sized_reports():
    class Predictions:
        def detect(self, frame, *, exclude_player=False):
            return (
                Detection("car", (0, 0, 55, 100), 0.9),
                Detection("car", (200, 0, 300, 100), 0.8),
            )

    records = [{"id": "one", "labels": [{"kind": "car", "box": (0, 0, 100, 100), "player": False}]}]
    result = evaluator().evaluate(Predictions(), records, [None])
    assert result["eligible_reports"] == 1
    assert result["invented_fraction"] == 1


def test_only_the_largest_candidate_is_taken_for_the_player():
    # Frame 040 of the second set: an enemy stands where the player usually is,
    # and the player crouches beside him.
    enemy = Detection("person", (557.0, 342.0, 607.0, 502.0), 0.8)
    player = Detection("person", (700.0, 425.0, 1015.0, 720.0), 0.9)
    passer_by = Detection("person", (100.0, 300.0, 140.0, 400.0), 0.7)
    own_car = Detection("car", (500.0, 420.0, 800.0, 700.0), 0.9)
    car_ahead = Detection("car", (590.0, 380.0, 710.0, 520.0), 0.8)
    kept = without_player((enemy, player, passer_by, car_ahead, own_car))
    assert kept == (enemy, passer_by, car_ahead)
    # Alone in that part of the picture, either of them is taken for the player.
    assert without_player((enemy, passer_by)) == (passer_by,)
    assert without_player(()) == ()


def test_reports_below_the_confidence_floor_are_left_out(detector):
    assert all(d.confidence >= 0.4 for d in detector.detect(frame(6), exclude_player=False))


def test_a_frame_offered_while_the_detector_works_does_not_reach_its_pixels():
    entered, release = Event(), Event()
    seen = []

    def recognize(pixels):
        entered.set()
        assert release.wait(2)
        seen.append(int(pixels[0, 0, 0]))
        return ()

    reader = Reader(interval=0, recognizer=recognize)
    try:
        assert reader.poll(np.zeros((720, 1280, 3), np.uint8), 1) is None
        assert entered.wait(1)
        later = np.full((720, 1280, 3), 255, np.uint8)
        for tick in range(5):
            assert reader.poll(later, 2 + tick) is None
        release.set()
        deadline = perf_counter() + 2
        while not seen and perf_counter() < deadline:
            sleep(0.001)
        assert seen[0] == 0
    finally:
        release.set()
        reader.close()


def test_the_person_and_the_vehicle_cut_out_come_back_beside_what_is_left():
    figure = Detection("person", (540, 330, 640, 600), 0.9)
    onlooker = Detection("person", (600, 340, 650, 520), 0.8)  # stands in the figure's place, smaller
    bystander = Detection("person", (20, 400, 60, 520), 0.8)
    rider_bike = Detection("motorcycle", (560, 450, 700, 640), 0.8)
    parked = Detection("car", (900, 380, 1100, 520), 0.9)
    everything = (onlooker, parked, figure, bystander, rider_bike)
    kept, person, vehicle = split_player(everything)
    assert person is figure and vehicle is rider_bike
    assert kept == (onlooker, parked, bystander)
    assert without_player(everything) == kept  # what the avoider sees is as it was
    assert split_player((parked, bystander)) == ((parked, bystander), None, None)


def test_the_real_detector_gives_the_cut_out_figure_beside_the_filtered_list(detector):
    for number, player in [(40, (505, 330, 625, 655)), (60, (542, 322, 642, 520))]:
        kept, figure, _ = detector.detect_split(frame(number))
        assert kept == detector(frame(number))
        assert figure is not None and iou(figure.box, player) > 0.5 and figure.kind == "person"
        assert all(d is not figure for d in kept)


def test_the_reader_keeps_the_figure_with_the_detections_it_belongs_to():
    first = Detection("person", (540, 330, 640, 600), 0.9)
    results = iter([((), first, None), ((), None, Detection("car", (560, 450, 700, 640), 0.8))])

    class Recognizer:
        def detect_split(self, frame):
            return next(results)

    pixels = np.zeros((720, 1280, 3), np.uint8)
    reader = Reader(interval=0, recognizer=Recognizer())
    try:
        assert reader.figure is None and reader.figure_vehicle is None
        got = []
        deadline = perf_counter() + 2
        while len(got) < 2 and perf_counter() < deadline:
            result = reader.poll(pixels, perf_counter())
            if result is not None:
                got.append((result, reader.figure, reader.figure_vehicle))
            sleep(0.001)
        assert [g[0][1] for g in got] == [(), ()]
        assert got[0][1:] == (first, None)
        assert got[1][1] is None and got[1][2].kind == "car"
    finally:
        reader.close()


def test_a_recognizer_that_does_not_split_leaves_the_figure_unknown():
    pixels = np.zeros((720, 1280, 3), np.uint8)
    reader = Reader(interval=0, recognizer=lambda frame: (Detection("car", (0, 0, 9, 9), 0.9),))
    try:
        deadline = perf_counter() + 2
        result = None
        while result is None and perf_counter() < deadline:
            result = reader.poll(pixels, perf_counter())
            sleep(0.001)
        assert result[1][0].kind == "car" and reader.figure is None and reader.figure_vehicle is None
    finally:
        reader.close()
