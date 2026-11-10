"""Optional HUD distance recognition and a causal, metre-based speed estimate."""

from collections import deque
from dataclasses import dataclass
from math import isfinite
from threading import Thread

import cv2
import numpy as np


@dataclass(frozen=True)
class Fix:
    distance: float
    arrow: str | None = None
    quantum: float = 1.0


def parse(texts) -> Fix | None:
    """Require a complete distance token; do not repair ambiguous OCR digits."""
    import re

    for text in texts:
        match = re.fullmatch(
            r"\s*([↑↓←→↰↱tT+•\u203a*I|\-]{1,3}\s*|1\s+)?(\d+(?:[.,]\d{1,2})?)\s*(km|m)[.)\-]*\s*", text, re.I
        )
        if not match:
            continue
        prefix, number, unit = match.groups()
        value = float(number.replace(",", "."))
        if unit.lower() == "km":
            # The HUD uses a decimal kilometre value, never a bare '4km'.
            if not 1 <= value < 100 or not any(c in number for c in ".,"):
                continue
            value, quantum = round(value * 1000), 10.0
        else:
            if not value.is_integer() or not 0 <= value < 1000:
                continue
            quantum = 1.0
        arrow = {"↑": "straight", "←": "left", "→": "right", "↓": "back", "↰": "left", "↱": "right"}.get(
            (prefix or "").strip()
        )
        return Fix(value, arrow, quantum)
    return None


def turn_arrow(crop: np.ndarray) -> str | None:
    """Match the small white HUD symbol; ambiguous or damaged shapes abstain."""
    patch = crop[118:142, 36:55]
    mask = ((patch.min(axis=2) > 170) & (np.ptp(patch.astype(float), axis=2) < 65)).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    best = None
    score = 0.0
    for index in range(1, count):
        x, y, w, h, area = stats[index]
        if area < 12 or w < 5 or h < 5 or w > 17 or h > 22:
            continue
        shape = cv2.resize((labels[y : y + h, x : x + w] == index).astype(np.uint8), (21, 21))
        for name, end in (("straight", (10, 1)), ("left", (1, 10)), ("right", (19, 10)), ("back", (10, 19))):
            start = (20 - end[0], 20 - end[1])
            template = np.zeros((21, 21), np.uint8)
            cv2.arrowedLine(template, start, end, 1, 4, tipLength=0.45)
            overlap = np.count_nonzero(shape & template) / max(1, np.count_nonzero(shape | template))
            if overlap > max(0.55, score):
                score, best = overlap, name
    return best


def recognize(crop: np.ndarray) -> Fix | None:
    """Accurate Apple Vision OCR; imports and framework errors are optional."""
    import Foundation
    import objc
    import Quartz
    import Vision

    q, v = Quartz, Vision

    patch = cv2.resize(crop[118:142, 36:120], None, fx=5, fy=5, interpolation=cv2.INTER_CUBIC)
    pixels = np.ascontiguousarray(patch)
    height, width = pixels.shape[:2]
    # Handing the pixels over as Python bytes, or without a pool, keeps every image alive:
    # 170 KB per call measured over 1000 calls, which is gigabytes over a stream.
    with objc.autorelease_pool():
        data = Foundation.NSData.dataWithBytes_length_(pixels.tobytes(), pixels.nbytes)
        provider = q.CGDataProviderCreateWithCFData(data)
        image = q.CGImageCreate(
            width, height, 8, 24, width * 3, q.CGColorSpaceCreateDeviceRGB(), 0, provider, None, False, 0
        )
        request = v.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(v.VNRequestTextRecognitionLevelAccurate)
        request.setUsesLanguageCorrection_(False)
        handler = v.VNImageRequestHandler.alloc().initWithCGImage_options_(image, {})
        ok, error = handler.performRequests_error_([request], None)
        if not ok:
            raise RuntimeError(f"GPS recognition failed: {error}")
        texts = [
            str(o.topCandidates_(1)[0].string()) for o in (request.results() or ()) if o.topCandidates_(1)
        ]
    fix = parse(texts)
    if fix is None:
        return None
    return Fix(fix.distance, fix.arrow or turn_arrow(crop), fix.quantum)


class Reader:
    """One in-flight OCR job, no queue and no wait in the 30 Hz caller.

    Results retain capture time, not completion time. A hung optional framework
    cannot hold the controller or prevent process exit.
    """

    def __init__(self, interval=0.25, recognizer=None):
        self.interval = interval
        self.recognizer = recognize if recognizer is None else recognizer
        self._thread = None
        self._started = None
        self._result = None
        self.error = None

    def close(self):
        if self._thread is not None:
            self._thread.join(timeout=0.5)

    def poll(self, crop, t):
        result = None
        if self._thread is not None and not self._thread.is_alive():
            result, self._result = self._result, None
            self._thread = None
        if self._thread is None and (
            self._started is None or t < self._started or t - self._started >= self.interval
        ):
            self._started = t
            pixels = crop.copy()

            def work():
                try:
                    self._result = (t, self.recognizer(pixels))
                    self.error = None
                except Exception as exc:
                    self.error = str(exc)
                    self._result = (t, None)

            self._thread = Thread(target=work, name="gps-ocr", daemon=True)
            self._thread.start()
        return result


class Speedometer:
    """Repeated-median regression tolerates minority OCR outliers without repairs.

    A new distance must agree with a timed consensus before renewing freshness.
    Increasing distance measures rolling speed, not forward route progress.
    """

    def __init__(self, window=3.0, stale=1.5, max_speed=50.0, tolerance=8.0, acceleration=8.0):
        self.window, self.stale, self.max_speed = window, stale, max_speed
        self.tolerance, self.acceleration = tolerance, acceleration
        self.pending = deque()
        self._slope = None
        self.samples = deque()
        self.fix = None
        self.time = None
        self.last_clock = None
        self.speed = None
        self.segment = 0
        self._last_input = None

    def update(self, t: float, fix: Fix | None = None, *, sampled_at=None):
        if not isfinite(t):
            return None
        if self.last_clock is not None and t < self.last_clock:
            self.reset()
        self.last_clock = t
        at = t if sampled_at is None else sampled_at
        if (
            fix is not None
            and isfinite(at)
            and 0 <= t - at <= self.stale
            and (self._last_input is None or at - self._last_input >= 0.1)
        ):
            self._last_input = at
            if self.fix is not None and self.time is not None and self._slope is not None:
                dt = at - self.time
                predicted = self.fix.distance + self._slope * dt
                allowance = max(2 * fix.quantum, self.tolerance + self.acceleration * dt * dt / 2)
                if abs(fix.distance - predicted) > allowance:
                    self.pending.append((at, fix))
                    while self.pending and at - self.pending[0][0] > 2:
                        self.pending.popleft()
                    coherent = len(self.pending) >= 5 and at - self.pending[0][0] >= 1
                    coherent = coherent and all(
                        abs(b[1].distance - a[1].distance)
                        <= self.max_speed * (b[0] - a[0]) + max(a[1].quantum, b[1].quantum)
                        for a, b in zip(self.pending, list(self.pending)[1:], strict=False)
                    )
                    if not coherent:
                        return self.value(t)
                    self.samples = self.pending.copy()
                    self.pending.clear()
                    self.speed = self._slope = None
                    self.segment += 1
                else:
                    self.pending.clear()
            self.samples.append((at, fix))
            while self.samples and at - self.samples[0][0] > self.window:
                self.samples.popleft()
            if len(self.samples) >= 4 and at - self.samples[0][0] >= 1.0:
                times = np.array([p[0] - at for p in self.samples])
                values = np.array([p[1].distance for p in self.samples])
                dt = times[None, :] - times[:, None]
                dv = values[None, :] - values[:, None]
                valid = np.abs(dt) >= 0.5
                slopes = np.full(dt.shape, np.nan)
                np.divide(dv, dt, out=slopes, where=valid)
                slopes = slopes[valid.any(axis=1)]
                slope = float(np.nanmedian(np.nanmedian(slopes, axis=1)))
                intercept = float(np.median(values - slope * times))
                tolerance = np.array([max(self.tolerance, p[1].quantum) for p in self.samples])
                inside = np.abs(values - (intercept + slope * times)) <= tolerance
                if abs(slope) <= self.max_speed and inside.sum() >= 3 and inside.mean() >= 0.55:
                    good = np.flatnonzero(inside)
                    if times[good[-1]] - times[good[0]] >= 1.0:
                        # Refit only the consensus, retaining the HUD quantisation.
                        fit = np.polyfit(times[inside], values[inside], 1)
                        self._slope = float(fit[0])
                        self.speed = abs(self._slope)
                        self.time, self.fix = self.samples[int(good[-1])]
        return self.value(t)

    def value(self, t):
        return self.speed if self.time is not None and 0 <= t - self.time <= self.stale else None

    def reset(self):
        self.samples.clear()
        self.pending.clear()
        self._slope = None
        self.fix = self.time = self.speed = self.last_clock = self._last_input = None
