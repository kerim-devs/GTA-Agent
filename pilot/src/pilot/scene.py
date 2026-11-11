"""Offline screen text and conservative, timestamp-based scene transitions.

Call the text reader at a few Hz, not at video frame rate. HUD transitions are
visual hypotheses: an absent map does not prove a cutscene, and its projection
does not prove vehicle occupancy. No network or controller access is used here.
"""

import math
import re
import time
from dataclasses import dataclass, field, replace
from difflib import SequenceMatcher

import numpy as np

from pilot.contract import Reading

REGIONS = {
    "help": (25, 20, 630, 180),
    "bottom": (280, 585, 740, 120),
    "banner": (190, 80, 900, 410),
    "phone": (910, 140, 360, 560),
    "menu": (25, 180, 650, 365),
}


@dataclass(frozen=True)
class TextLine:
    text: str
    confidence: float
    box: tuple[int, int, int, int]
    region: str


@dataclass(frozen=True)
class SceneText:
    lines: tuple[TextLine, ...] = ()
    help: str = ""
    objective: str = ""
    subtitle: str = ""
    banner: str = ""
    phone_menu: str = ""
    elapsed_ms: float = 0.0


class VisionUnavailableError(RuntimeError):
    """The optional macOS OCR runtime is unavailable."""


def _frame(frame: np.ndarray) -> None:
    if not isinstance(frame, np.ndarray) or frame.shape != (720, 1280, 3) or frame.dtype != np.uint8:
        raise ValueError("expected a 1280x720 RGB uint8 frame")


def _inside(box: tuple[int, int, int, int], rect: tuple[int, int, int, int]) -> bool:
    x, y, w, h = box
    a, b, c, d = rect
    return a <= x + w / 2 <= a + c and b <= y + h / 2 <= b + d


def _objective(frame: np.ndarray, box: tuple[int, int, int, int], text: str) -> bool:
    """Conservative instruction cue plus coloured target; never colour alone.

    This is a bounded German/English heuristic, not semantic mission parsing.
    Other bottom text is still retained as subtitle context for the head.
    """
    if not re.match(
        r"^(begib|folge|sammle|schalte|fahre?|geh|gehe|erreiche|steig|steige|verlasse|bring|bringe|"
        r"töte|beschaffe|kehre|rette|verliere|finde|hole|warte|halte|triff|go|follow|collect|"
        r"take|kill|drive|find|reach|enter|leave|return|lose|meet|wait|steal)\b",
        text.casefold(),
    ):
        return False
    x, y, w, h = box
    pixels = frame[max(y, 0) : y + h, max(x, 0) : x + w].astype(np.int16)
    if not pixels.size:
        return False
    r, g, b = pixels[..., 0], pixels[..., 1], pixels[..., 2]
    yellow = (r > 160) & (g > 130) & (b < 130) & (r - b > 65)
    cyan = (g > 140) & (b > 140) & (r < 120)
    red = (r > 140) & (g < 120) & (b < 120)
    green = (g > 120) & (g - r > 30) & (g - b > 30)
    return float(np.mean(yellow | cyan | red | green)) > 0.012


def _banner(text: str) -> bool:
    normalized = _normal(text)
    labels = (
        "mission fehlgeschlagen",
        "bestanden",
        "mission bestanden",
        "gescheitert",
        "tot",
        "verhaftet",
        "mission passed",
        "mission failed",
        "wasted",
        "busted",
    )
    return any(SequenceMatcher(None, normalized, label).ratio() >= 0.72 for label in labels)


class TextReader:
    """Apple Vision OCR, German then English, loaded only when instantiated.

    ``read(frame)`` scans the full frame once. ``read(frame, region='help')``
    scans one crop. Boxes always use full-frame, top-left pixel coordinates.
    Keep a separate reader/detector per stream; instances are not thread-safe.
    """

    def __init__(self, level: str = "accurate") -> None:
        if level not in {"fast", "accurate"}:
            raise ValueError("level must be fast or accurate")
        try:
            import Foundation
            import objc
            import Quartz
            import Vision
        except ImportError as exc:
            raise VisionUnavailableError("install the macOS Vision/Quartz dependencies to use OCR") from exc
        self._foundation = Foundation
        self._objc = objc
        self._quartz = Quartz
        self._vision = Vision
        self.level = level

    def read(self, frame: np.ndarray, region: str | None = None) -> SceneText:
        _frame(frame)
        if region is not None and region not in REGIONS:
            raise ValueError(f"unknown region: {region}")
        started = time.perf_counter()
        x, y, w, h = REGIONS[region] if region else (0, 0, 1280, 720)
        pixels = np.ascontiguousarray(frame[y : y + h, x : x + w])
        q, v = self._quartz, self._vision
        found = []
        # Handing the pixels over as Python bytes, or without a pool, keeps every image alive:
        # 2.8 MB per full frame, measured as 170 KB per call on a 420x120 patch.
        with self._objc.autorelease_pool():
            data = self._foundation.NSData.dataWithBytes_length_(pixels.tobytes(), pixels.nbytes)
            provider = q.CGDataProviderCreateWithCFData(data)
            image = q.CGImageCreate(
                w, h, 8, 24, w * 3, q.CGColorSpaceCreateDeviceRGB(), 0, provider, None, False, 0
            )
            request = v.VNRecognizeTextRequest.alloc().init()
            request.setRecognitionLevel_(
                v.VNRequestTextRecognitionLevelFast
                if self.level == "fast"
                else v.VNRequestTextRecognitionLevelAccurate
            )
            request.setRecognitionLanguages_(["de-DE", "en-US"])
            request.setUsesLanguageCorrection_(True)
            handler = v.VNImageRequestHandler.alloc().initWithCGImage_options_(image, {})
            success, error = handler.performRequests_error_([request], None)
            if not success:
                raise RuntimeError(f"Vision text recognition failed: {error}")
            for observation in request.results() or ():
                candidates = observation.topCandidates_(1)
                if not candidates:
                    continue
                bounds = observation.boundingBox()
                found.append(
                    (
                        str(candidates[0].string()),
                        float(candidates[0].confidence()),
                        (bounds.origin.x, bounds.origin.y, bounds.size.width, bounds.size.height),
                    )
                )
        lines = []
        for words, confidence, (left, bottom, width, height) in found:
            box = (
                x + round(left * w),
                y + round((1 - bottom - height) * h),
                round(width * w),
                round(height * h),
            )
            label = next(
                (name for name, rect in REGIONS.items() if name != "banner" and _inside(box, rect)), "other"
            )
            if _inside(box, REGIONS["banner"]) and box[3] >= 25 and _banner(words):
                label = "banner"
            if label == "bottom":
                label = "objective" if _objective(frame, box, words) else "subtitle"
            if label == "help" and (box[0] > 115 or sum(char.isalpha() for char in words) < 4):
                label = "other"
            lines.append(TextLine(words, confidence, box, label))
        lines.sort(key=lambda line: (line.box[1], line.box[0]))

        def joined(*labels: str) -> str:
            return " ".join(line.text for line in lines if line.region in labels and line.confidence >= 0.3)

        return SceneText(
            tuple(lines),
            joined("help"),
            joined("objective"),
            joined("subtitle"),
            joined("banner"),
            joined("phone", "menu"),
            (time.perf_counter() - started) * 1000,
        )


@dataclass(frozen=True)
class SceneEvent:
    kind: str
    timestamp: float
    previous: str
    current: str
    evidence: str
    text: SceneText | None = None


def _normal(text: str) -> str:
    return re.sub(r"[\W_]+", " ", text.casefold()).strip()


def _similar(a: str, b: str) -> bool:
    a, b = _normal(a), _normal(b)
    return a == b or bool(a and b and SequenceMatcher(None, a, b).ratio() >= 0.86)


@dataclass
class _Stable:
    value: str | None = None
    candidate: str | None = None
    since: float = 0.0
    count: int = 0


@dataclass
class EventDetector:
    """Debounce evidence using monotonic seconds, never frame counts alone.

    First stable observations establish baselines without triggering the head.
    HUD absence takes 2 seconds; other map changes take 1 second. Text must
    settle for 1.5 seconds. Corrupt/low-confidence readings reset pending map
    transitions. Missing OCR is unknown, not empty. Dialogue is payload only.
    """

    map_seconds: float = 1.0
    absent_seconds: float = 2.0
    text_seconds: float = 1.5
    max_gap: float = 2.0
    _states: dict[str, _Stable] = field(default_factory=dict, init=False, repr=False)
    _last_time: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        for value in (self.map_seconds, self.absent_seconds, self.text_seconds, self.max_gap):
            if not math.isfinite(value) or value <= 0:
                raise ValueError("debounce intervals must be finite and positive")

    def _update(self, key: str, value: str, now: float, delay: float, text: bool = False):
        state = self._states.setdefault(key, _Stable())
        equal = _similar if text else lambda a, b: a == b
        if state.value is not None and equal(value, state.value):
            state.candidate, state.count = None, 0
            return None
        if state.candidate is None or not equal(value, state.candidate):
            state.candidate, state.since, state.count = value, now, 1
            return None
        state.count += 1
        if now - state.since < delay or state.count < 3:
            return None
        previous = state.value
        state.value, state.candidate, state.count = value, None, 0
        if previous is None:
            return None
        return previous, value

    def update(
        self,
        reading: Reading,
        timestamp: float,
        *,
        mode: str | None = None,
        text: SceneText | None = None,
        frame: np.ndarray | None = None,
        reader: TextReader | None = None,
    ) -> tuple[SceneEvent, ...]:
        if not math.isfinite(timestamp) or (self._last_time is not None and timestamp <= self._last_time):
            raise ValueError("timestamps must be finite and strictly increasing")
        if frame is not None:
            _frame(frame)
            if reader is not None:
                text = reader.read(frame)
        if self._last_time is not None and timestamp - self._last_time > self.max_gap:
            for state in self._states.values():
                state.candidate, state.count = None, 0
        self._last_time = timestamp
        events = []
        if mode is not None:
            vehicle = self._states.setdefault("vehicle", _Stable())
            vehicle.candidate, vehicle.count = None, 0
            if mode in {"foot", "vehicle"}:
                # Preserve the existing event vocabulary. Accepted judge modes
                # have already been filtered and need no map debounce.
                value = "flat" if mode == "foot" else "tilted"
                previous, vehicle.value = vehicle.value, value
                if previous is not None and previous != value:
                    kind = "vehicle_enter" if mode == "vehicle" else "vehicle_exit"
                    events.append(
                        SceneEvent(kind, timestamp, previous, value, "judge mode; occupancy hypothesis")
                    )
        valid = (
            not reading.corrupt
            and (reading.minimap == "none" or reading.confidence >= 0.45)
            and reading.minimap in {"none", "flat", "tilted"}
        )
        if valid:
            hud = "absent" if reading.minimap == "none" else "present"
            change = self._update(
                "hud", hud, timestamp, self.absent_seconds if hud == "absent" else self.map_seconds
            )
            if change:
                events.append(
                    SceneEvent(
                        "hud_" + hud, timestamp, *change, "minimap visibility; cutscene/menu hypothesis"
                    )
                )
            if hud == "present":
                # Silence starts a fresh map candidate from the judge's last state.
                change = (
                    self._update("vehicle", reading.minimap, timestamp, self.map_seconds)
                    if mode is None
                    else None
                )
                if change:
                    kind = "vehicle_enter" if reading.minimap == "tilted" else "vehicle_exit"
                    events.append(
                        SceneEvent(kind, timestamp, *change, "minimap projection; occupancy hypothesis")
                    )
                if reading.route in {"none", "yellow", "purple"}:
                    change = self._update("route", reading.route, timestamp, self.map_seconds)
                    if change:
                        kind = (
                            "route_appeared"
                            if change[0] == "none"
                            else "route_vanished"
                            if change[1] == "none"
                            else "route_colour_changed"
                        )
                        events.append(SceneEvent(kind, timestamp, *change, "minimap route colour"))
            else:
                # A hidden HUD is not evidence of leaving a vehicle/losing a route.
                for key in ("vehicle", "route"):
                    if key in self._states:
                        self._states[key].candidate, self._states[key].count = None, 0
        else:
            for key in ("hud", "vehicle", "route"):
                if key in self._states:
                    self._states[key].candidate, self._states[key].count = None, 0
        for key in ("help", "objective", "banner"):
            if text is None:
                if key in self._states:
                    self._states[key].candidate, self._states[key].count = None, 0
                continue
            change = self._update(key, getattr(text, key), timestamp, self.text_seconds, text=True)
            if change and (key != "banner" or change[1]):
                kind = "banner_appeared" if key == "banner" else key + "_changed"
                events.append(SceneEvent(kind, timestamp, *change, "stable local OCR"))
        return tuple(replace(event, text=text) for event in events)
