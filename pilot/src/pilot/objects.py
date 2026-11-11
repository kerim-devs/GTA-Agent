"""Local YOLOX Tiny detections and a single-worker, latest-frame reader."""

import hashlib
from pathlib import Path
from threading import Condition, Thread

import cv2
import numpy as np
import onnxruntime as ort

from .contract import Detection

MODEL = Path(__file__).resolve().parents[2] / "models" / "yolox_tiny.onnx"
SHA256 = "427cc366d34e27ff7a03e2899b5e3671425c262ea2291f88bb942bc1cc70b0f7"
KINDS = {0: "person", 1: "bicycle", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


def _frame(frame):
    if not isinstance(frame, np.ndarray) or frame.shape != (720, 1280, 3) or frame.dtype != np.uint8:
        raise ValueError("expected a 1280x720 RGB uint8 frame")


def is_player(detection: Detection) -> bool:
    """Camera-relative exclusion; its collateral misses are measured in lab/objects."""
    x0, y0, x1, y1 = detection.box
    cx = (x0 + x1) / 2
    if detection.kind == "person":
        # Running/aiming keeps the player low and central; close shoulder views reach an edge.
        return (440 <= cx <= 710 and y1 >= 480 and y1 - y0 >= 150) or (y1 >= 680 and y1 - y0 >= 250)
    return 550 <= cx <= 750 and y1 >= 510 and x1 - x0 >= 100 and y0 >= 300


class Detector:
    def __init__(self, model: Path = MODEL, confidence: float = 0.25):
        if not 0 < confidence <= 1:
            raise ValueError("confidence must be between zero and one")
        model = Path(model)
        if not model.is_file() or hashlib.sha256(model.read_bytes()).hexdigest() != SHA256:
            raise RuntimeError(
                "YOLOX Tiny weights missing or corrupt; run: python tools/fetch_models.py (in pilot)"
            )
        ort.disable_telemetry_events()
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(model), options, providers=["CPUExecutionProvider"])
        self.confidence = confidence
        grids, strides = [], []
        for stride in (8, 16, 32):
            y, x = np.mgrid[: 416 // stride, : 416 // stride]
            grids.append(np.stack((x, y), axis=-1).reshape(-1, 2))
            strides.append(np.full((x.size, 1), stride))
        self.grid = np.concatenate(grids).astype(np.float32)
        self.strides = np.concatenate(strides).astype(np.float32)

    def detect(self, frame: np.ndarray, *, exclude_player: bool = True) -> tuple[Detection, ...]:
        _frame(frame)
        # The official export expects BGR bytes, top-left letterboxed, without normalization.
        resized = cv2.resize(frame[:, :, ::-1], (416, 234), interpolation=cv2.INTER_LINEAR)
        padded = np.full((416, 416, 3), 114, dtype=np.uint8)
        padded[:234] = resized
        tensor = np.ascontiguousarray(padded.transpose(2, 0, 1)[None], dtype=np.float32)
        output = self.session.run(None, {"images": tensor})[0][0]
        classes = output[:, 5:].argmax(axis=1)
        scores = output[:, 4] * output[np.arange(len(output)), classes + 5]
        keep = (scores >= self.confidence) & np.isin(classes, list(KINDS))
        centers = (output[keep, :2] + self.grid[keep]) * self.strides[keep]
        sizes = np.exp(output[keep, 2:4]) * self.strides[keep]
        boxes = np.concatenate((centers - sizes / 2, centers + sizes / 2), axis=1) / (416 / 1280)
        boxes[:, (0, 2)] = boxes[:, (0, 2)].clip(0, 1280)
        boxes[:, (1, 3)] = boxes[:, (1, 3)].clip(0, 720)
        scores, classes = scores[keep], classes[keep]
        results = []
        # Class-agnostic suppression prevents a single vehicle being both a car and a truck.
        order = scores.argsort()[::-1]
        while len(order):
            i = order[0]
            box = boxes[i]
            if box[2] > box[0] and box[3] > box[1]:
                detection = Detection(KINDS[int(classes[i])], tuple(map(float, box)), float(scores[i]))
                if not exclude_player or not is_player(detection):
                    results.append(detection)
            order = order[1:]
            others = boxes[order]
            intersection = np.maximum(
                0, np.minimum(box[2:], others[:, 2:]) - np.maximum(box[:2], others[:, :2])
            )
            intersection = intersection.prod(axis=1)
            area = (box[2] - box[0]) * (box[3] - box[1])
            other_area = (others[:, 2] - others[:, 0]) * (others[:, 3] - others[:, 1])
            overlap = intersection / np.maximum(area + other_area - intersection, 1e-6)
            order = order[overlap <= 0.45]
        return tuple(results)

    __call__ = detect


class Reader:
    def __init__(self, interval: float = 0.05, recognizer=None):
        if interval < 0:
            raise ValueError("interval must not be negative")
        self.interval = interval
        self.recognizer = Detector() if recognizer is None else recognizer
        self.error = None
        self._condition = Condition()
        self._job = None
        self._result = None
        self._busy = False
        self._closed = False
        self._started = None
        self._thread = Thread(target=self._work, name="object-detector", daemon=True)
        self._thread.start()

    def _work(self):
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._closed or self._job is not None)
                if self._closed:
                    return
                frame, t = self._job
                self._job = None
            try:
                result, error = tuple(self.recognizer(frame)), None
            except Exception as exc:
                result, error = (), str(exc)
            del frame
            with self._condition:
                self._busy = False
                if not self._closed:
                    self._result = (t, result)
                    self.error = error

    def poll(self, frame: np.ndarray, t: float):
        _frame(frame)
        with self._condition:
            if self._closed:
                return None
            result, self._result = self._result, None
            due = self._started is None or t < self._started or t - self._started >= self.interval
            if not self._busy and due:
                self._busy = True
                self._started = t
                self._job = (frame.copy(), t)
                self._condition.notify()
            return result

    def close(self):
        with self._condition:
            self._closed = True
            self._job = self._result = None
            self._condition.notify()
        self._thread.join()
