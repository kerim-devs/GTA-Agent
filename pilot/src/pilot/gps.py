"""Optional HUD distance recognition and a causal, metre-based speed estimate."""

from collections import deque
from dataclasses import dataclass
from itertools import pairwise
from math import isfinite
from threading import Thread

import cv2
import numpy as np

from .apple import frameworks


@dataclass(frozen=True)
class Fix:
    distance: float
    arrow: str | None = None
    quantum: float = 1.0


def parse(texts) -> Fix | None:
    """Require a complete distance token; do not repair ambiguous OCR digits."""
    import re

    # Vision sometimes separates the unit or inserts spaces around the decimal.
    # Join only a number followed by its unit, never guessed/repaired digits.
    texts = list(texts)
    candidates = texts + [
        a + b
        for a, b in pairwise(texts)
        if re.fullmatch(r"\s*\d+(?:[.,]\s*\d{1,2})?\s*", a) and re.fullmatch(r"\s*(?:km|m)\s*", b, re.I)
    ]
    for text in candidates:
        text = re.sub(r"(?<=\d)\s*([.,])\s*(?=\d)", r"\1", text)
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
    foundation, objc, q, v = frameworks()

    # Keep the turn symbol and blips out of the number. On P104's light roads,
    # removing the broad background recovers glyphs that the RGB crop loses.
    raw = crop[119:141, 53:120]
    gray = cv2.cvtColor(raw, cv2.COLOR_RGB2GRAY)
    patches = [
        raw,
        cv2.cvtColor(cv2.createCLAHE(clipLimit=2, tileGridSize=(4, 2)).apply(gray), cv2.COLOR_GRAY2RGB),
    ]
    for size in (3, 5):
        foreground = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, np.ones((size, size), np.uint8))
        foreground = np.clip(foreground.astype(float) * 4, 0, 255).astype(np.uint8)
        patches.append(cv2.cvtColor(foreground, cv2.COLOR_GRAY2RGB))
    # One request, including on a miss; no retry can occupy another live slot.
    pixels = np.full((560, 335, 3), 100, np.uint8)
    for index, patch in enumerate(patches):
        pixels[index * 140 + 15 : index * 140 + 125] = cv2.resize(
            patch, None, fx=5, fy=5, interpolation=cv2.INTER_CUBIC
        )
    height, width = pixels.shape[:2]
    # Handing the pixels over as Python bytes, or without a pool, keeps every image alive:
    # 170 KB per call measured over 1000 calls, which is gigabytes over a stream. Under Python 3.12
    # the same happens (250 KB per call) unless the observations are still referenced when the pool
    # drains, so `results` is a local that lives to the end of the function on purpose.
    results = []
    texts = [[] for _ in patches]
    with objc.autorelease_pool():
        data = foundation.NSData.dataWithBytes_length_(pixels.tobytes(), pixels.nbytes)
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
        results = list(request.results() or ())
        for observation in results:
            candidates = observation.topCandidates_(1)
            if candidates:
                (_, y), (_, h) = observation.boundingBox()
                index = max(0, min(3, int((1 - y - h / 2) * 4)))
                texts[index].append(str(candidates[0].string()))
    # Background removal helps bright roads but can break closed digits on a
    # dark field (326 becomes 328 in the existing cable fixture). Measure only
    # the digit band, not the lighter map margin above it.
    bright = np.median(cv2.cvtColor(crop[125:137, 54:83], cv2.COLOR_RGB2GRAY)) >= 140
    fixes = [fix for band in texts[: 4 if bright else 2] if (fix := parse(band)) is not None]
    # Different preparations can drop a leading digit or turn 6 into 8. An
    # explicit disagreement is not resolved by choosing the more convenient one.
    if not fixes or len({fix.distance for fix in fixes}) != 1:
        return None
    fix = fixes[0]
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

    def __init__(self, window=3.0, stale=1.5, max_speed=50.0, tolerance=8.0, acceleration=8.0, fall=60.0):
        self.window, self.stale, self.max_speed, self.fall = window, stale, max_speed, fall
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
        self._distance_samples = deque(maxlen=3)
        self._speed_fix = self._speed_time = None

    def _distance(self, at, fix):
        """Three coherent captures can locate us before a speed fit is available."""
        self._distance_samples.append((at, fix))
        samples = self._distance_samples
        if len(samples) < 3 or not 0.5 <= at - samples[0][0] <= self.window:
            return
        if (self._speed_time is None or at - self._speed_time > self.stale) and all(
            abs(b.distance - a.distance) <= self.max_speed * (tb - ta) + max(a.quantum, b.quantum)
            for (ta, a), (tb, b) in zip(samples, list(samples)[1:], strict=False)
        ):
            self.time, self.fix = at, fix

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
            if (
                self.fix is not None
                and self.time is not None
                and at > self.time
                and self.fix.distance - fix.distance
                > self.max_speed * (at - self.time) + self.fall + max(fix.quantum, self.fix.quantum)
            ):
                # No car closes on its destination faster than it drives. Over a light road by day
                # "756m" was read as 56 for four seconds with the car standing (20261114-035459): a
                # trip takes that for the door. A route the game has made shorter is believed once
                # the time since the last distance allows the fall.
                return self.value(t)
            self._distance(at, fix)
            if self._speed_fix is not None and self._speed_time is not None and self._slope is not None:
                dt = at - self._speed_time
                predicted = self._speed_fix.distance + self._slope * dt
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
            span = at - self.samples[0][0]
            fine = all(sample.quantum <= 1 for _, sample in self.samples)
            if len(self.samples) >= 4 and span >= (0.75 if fine else 1.0):
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
                    # Four metre readings can start at 0.75 s only when all four
                    # fit within one printed metre. Coarse kilometres and a
                    # disputed startup still need the full second of consensus.
                    early = (
                        fine and inside.all() and np.max(np.abs(values - (intercept + slope * times))) <= 1
                    )
                    if times[good[-1]] - times[good[0]] >= (0.75 if early else 1.0):
                        # Refit only the consensus, retaining the HUD quantisation.
                        fit = np.polyfit(times[inside], values[inside], 1)
                        self._slope = float(fit[0])
                        self.speed = abs(self._slope)
                        self._speed_time, self._speed_fix = self.samples[int(good[-1])]
                        # Keep the established speed/approach pair while that fit is fresh.
                        self.time, self.fix = self._speed_time, self._speed_fix
        return self.value(t)

    def value(self, t):
        return (
            self.speed if self._speed_time is not None and 0 <= t - self._speed_time <= self.stale else None
        )

    def reset(self):
        self.samples.clear()
        self.pending.clear()
        self._distance_samples.clear()
        self._slope = None
        self.fix = self.time = self.speed = self.last_clock = self._last_input = None
        self._speed_fix = self._speed_time = None
