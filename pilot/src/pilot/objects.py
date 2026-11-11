"""Local hardware-accelerated detections and a single-worker, latest-frame reader."""

import hashlib
from pathlib import Path
from threading import Condition, Thread

import cv2
import numpy as np
import onnxruntime as ort

from .contract import Detection

MODEL = Path(__file__).resolve().parents[2] / "models" / "yolox_l.onnx"
SHA256 = "7860ae79de6c89a3c1eb72ae9a2756c0ccfbe04b7791bb5880afabd97855a411"
WEIGHTS = {
    "yolox_tiny.onnx": "427cc366d34e27ff7a03e2899b5e3671425c262ea2291f88bb942bc1cc70b0f7",
    "yolox_s.onnx": "c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063",
    "yolox_m.onnx": "21ff6cfdeb53b013bac2249599e55f00bff3cfdfdab37ed7a4620818c1d15b3f",
    "yolox_l.onnx": "7860ae79de6c89a3c1eb72ae9a2756c0ccfbe04b7791bb5880afabd97855a411",
    "rtdetr_v2_r18vd.onnx": "583a236ac21c95a7fd94f284fc21485e42355bfef82c27011ba78fbc09ee87e2",
}
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


def without_player(detections) -> tuple[Detection, ...]:
    """Drop the one person and the one vehicle that look most like the player's own.

    The camera sits behind the character, so of several boxes where the player usually is,
    the largest is the player; an enemy standing in the same part of the picture stays.
    """
    dropped = []
    for people in (True, False):
        candidates = [d for d in detections if (d.kind == "person") == people and is_player(d)]
        if candidates:
            dropped.append(max(candidates, key=lambda d: (d.box[2] - d.box[0]) * (d.box[3] - d.box[1])))
    return tuple(d for d in detections if not any(d is other for other in dropped))


class Detector:
    def __init__(self, model: Path = MODEL, confidence: float = 0.4):
        if not 0 < confidence <= 1:
            raise ValueError("confidence must be between zero and one")
        model = Path(model)
        digest = None
        if model.is_file():
            with model.open("rb") as weights:
                digest = hashlib.file_digest(weights, "sha256").hexdigest()
        if digest != WEIGHTS.get(model.name, SHA256):
            raise RuntimeError(
                "YOLOX weights missing or corrupt; run: python tools/fetch_models.py (in pilot)"
            )
        ort.disable_telemetry_events()
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        for name, value in (("batch_size", 1), ("height", 640), ("width", 640)):
            options.add_free_dimension_override_by_name(name, value)
        if "CoreMLExecutionProvider" not in ort.get_available_providers():
            raise RuntimeError("The object detector requires the CoreML execution provider")
        self.session = ort.InferenceSession(
            str(model),
            options,
            providers=[
                ("CoreMLExecutionProvider", {"MLComputeUnits": "ALL", "ModelFormat": "MLProgram"}),
                "CPUExecutionProvider",
            ],
        )
        self.size = self.session.get_inputs()[0].shape[2]
        self.transformer = model.name.startswith("rtdetr")
        self.input_name = self.session.get_inputs()[0].name
        self.tiled = False
        self.confidence = confidence
        grids, strides = [], []
        for stride in (8, 16, 32):
            y, x = np.mgrid[: self.size // stride, : self.size // stride]
            grids.append(np.stack((x, y), axis=-1).reshape(-1, 2))
            strides.append(np.full((x.size, 1), stride))
        self.grid = np.concatenate(grids).astype(np.float32)
        self.strides = np.concatenate(strides).astype(np.float32)

    def detect(self, frame: np.ndarray, *, exclude_player: bool = True) -> tuple[Detection, ...]:
        _frame(frame)
        views = ((0, frame),) if not self.tiled else ((0, frame[:, :720]), (560, frame[:, 560:]))
        batches = []
        for offset, view in views:
            if self.transformer:
                resized = cv2.resize(view, (self.size, self.size), interpolation=cv2.INTER_LINEAR)
                tensor = np.ascontiguousarray(resized.transpose(2, 0, 1)[None], dtype=np.float32) / 255
                logits, boxes = self.session.run(None, {self.input_name: tensor})
                classes = logits[0].argmax(axis=1)
                scores = 1 / (1 + np.exp(-np.clip(logits[0, np.arange(len(classes)), classes], -80, 80)))
                keep = (scores >= self.confidence) & np.isin(classes, list(KINDS))
                centers, sizes = boxes[0, keep, :2], boxes[0, keep, 2:]
                boxes = np.concatenate((centers - sizes / 2, centers + sizes / 2), axis=1)
                boxes *= np.array([view.shape[1], view.shape[0], view.shape[1], view.shape[0]])
                boxes[:, (0, 2)] += offset
                batches.append((boxes, scores[keep], classes[keep]))
                continue
            # The export expects BGR bytes, top-left letterboxed, without normalization.
            scale = min(self.size / view.shape[1], self.size / view.shape[0], 1.0)
            width, height = int(view.shape[1] * scale), int(view.shape[0] * scale)
            resized = cv2.resize(view[:, :, ::-1], (width, height), interpolation=cv2.INTER_LINEAR)
            padded = np.full((self.size, self.size, 3), 114, dtype=np.uint8)
            padded[:height, :width] = resized
            tensor = np.ascontiguousarray(padded.transpose(2, 0, 1)[None], dtype=np.float32)
            output = self.session.run(None, {"images": tensor})[0][0]
            classes = output[:, 5:].argmax(axis=1)
            scores = output[:, 4] * output[np.arange(len(output)), classes + 5]
            keep = (scores >= self.confidence) & np.isin(classes, list(KINDS))
            centers = (output[keep, :2] + self.grid[keep]) * self.strides[keep]
            sizes = np.exp(output[keep, 2:4]) * self.strides[keep]
            boxes = np.concatenate((centers - sizes / 2, centers + sizes / 2), axis=1) / scale
            boxes[:, (0, 2)] += offset
            batches.append((boxes, scores[keep], classes[keep]))
        boxes, scores, classes = (np.concatenate(items) for items in zip(*batches, strict=True))
        boxes[:, (0, 2)] = boxes[:, (0, 2)].clip(0, 1280)
        boxes[:, (1, 3)] = boxes[:, (1, 3)].clip(0, 720)
        results = []
        # Class-agnostic suppression prevents a single vehicle being both a car and a truck.
        order = scores.argsort()[::-1]
        while len(order):
            i = order[0]
            box = boxes[i]
            if box[2] > box[0] and box[3] > box[1]:
                results.append(Detection(KINDS[int(classes[i])], tuple(map(float, box)), float(scores[i])))
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
        return without_player(results) if exclude_player else tuple(results)

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
        self._pixels = np.empty((720, 1280, 3), dtype=np.uint8)
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
                np.copyto(self._pixels, frame)
                self._job = (self._pixels, t)
                self._condition.notify()
            return result

    def close(self):
        with self._condition:
            self._closed = True
            self._job = self._result = None
            self._condition.notify()
        self._thread.join()
