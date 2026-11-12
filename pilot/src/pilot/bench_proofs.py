"""What a session's own record says happened: the named pieces the bench builds its proofs from.

A proof reads the readings, the judge's answers and the pictures of a session, never the verdict the
skill returned. The catalogue in `bench.py` lists for each capability the pieces it needs; a piece
answers yes, no or not measurable, with the numbers it saw and the second where it went wrong. A new
piece is one function with the `@piece` decorator; an entry then names it.

Two readers of the pilot are used again here on the stored video, offline and at other moments than the
skill read them: the HUD reader (which screen the game shows) and the object detector (where the
figure stands). The minimap class is never taken alone for "on foot" or "seated": it was seen to read a
flat map as tilted for seconds over bright ground, so the mode needs a majority over a stretch, agreed
by the judge's answers where there are any, and a mixed stretch is not measurable.

Nothing here writes into a session folder.
"""

from __future__ import annotations

import bisect
import json
import math
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cached_property
from itertools import pairwise
from pathlib import Path
from typing import Any

AGREE = 0.8  # the share of a stretch that has to name the same mode
START_STRETCH = 1.5  # seconds from the first tick that say how a try began
END_STRETCH = 2.0  # seconds before the end that say how it ended
MIN_MINIMAP = 8  # readings of the minimap that make a vote
MIN_JUDGED = 3  # judgments that make a vote
HUD_RECT = (30, 530, 260, 170)  # x, y, w, h of the minimap crop in a 1280x720 frame, as contract.HUD_RECT
ARROW_XY = (123, 117)  # the player's arrow in that crop
SAME_PX = 3.0  # a waypoint blip that moved less than this stands where it stood
FPS_FALLBACK = 60.0


def read_jsonl(path: Path) -> list[dict]:
    """The rows of a log. A last line that is cut off (a session still being recorded) is left out."""
    if not path.exists():
        return []
    lines = [line for line in path.read_text().splitlines() if line.strip()]
    rows = []
    for number, line in enumerate(lines, 1):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            if number == len(lines):
                break
            raise ValueError(f"{path}:{number}: invalid JSON") from exc
    return rows


@dataclass(frozen=True)
class Evidence:
    """What one piece found. `ok` is True, False, or None for "not measurable", then `missing` says why
    and where the missing field would be written. `moment` is (second of the session, how it was found)."""

    ok: bool | None
    numbers: dict = field(default_factory=dict)
    missing: str = ""
    moment: tuple[float, str] | None = None
    parts: tuple[tuple[str, bool | None], ...] = ()  # what each piece of a combination said


@dataclass(frozen=True)
class Mode:
    mode: str | None  # foot, vehicle or None when the stretch does not say
    why: str  # agree, minimap, judge, conflict, mixed, too-few
    minimap: dict
    judge: dict


@dataclass(frozen=True)
class Window:
    t0: float
    t1: float


class Session:
    """One session folder, read-only. `frames` (seconds -> RGB frame or None) and `detect` (RGB frame ->
    (kept, figure, vehicle)) replace the video and the detector, for tests."""

    def __init__(self, folder: Path, *, frames: Callable | None = None, detect: Callable | None = None):
        self.folder = Path(folder)
        self.play = read_jsonl(self.folder / "play.jsonl")
        self.head = read_jsonl(self.folder / "head.jsonl")
        self.judge = read_jsonl(self.folder / "judge.jsonl")
        self.frame_log = read_jsonl(self.folder / "frames.jsonl")
        self.pad = read_jsonl(self.folder / "pad.jsonl")
        self._frames, self._detect = frames, detect
        self._cache: dict = {}
        self._capture = None

    # ---- times
    @property
    def start(self) -> float:
        return self.play[0]["t"] if self.play else 0.0

    @property
    def end(self) -> float:
        return self.play[-1]["t"] if self.play else 0.0

    @cached_property
    def requests(self) -> list[dict]:
        """The head's requests with `t` in session seconds. Head rows carry the monotonic clock and the
        play rows the session's own; the first request was made on the first tick, so the difference of
        the two is the offset (it matches an opening_failed row and a skill's failure to the microsecond)."""
        rows, seen = [], set()
        for row in self.head:
            if row.get("type") != "request" or "request" not in row:
                continue
            if row.get("id") in seen:
                continue
            seen.add(row.get("id"))
            rows.append(row)
        if not rows or not self.play:
            return []
        self._offset = rows[0]["t"] - self.play[0]["t"]
        return [dict(row["request"], t=row["t"] - self._offset, id=row.get("id")) for row in rows]

    @property
    def offset(self) -> float | None:
        self.requests  # noqa: B018
        return getattr(self, "_offset", None)

    @cached_property
    def opening_failures(self) -> list[dict]:
        """Opening skills that failed: logged by the conductor in head.jsonl, not in play.jsonl."""
        found = []
        for row in self.head:
            if row.get("type") == "opening_failed":
                t = row["t"] - self.offset if self.offset is not None else None
                found.append({"t": t, "name": row.get("name"), "reason": row.get("reason", "")})
        return found

    @cached_property
    def judgments(self) -> list[tuple[float, dict]]:
        """(capture second, answers) of every judgment, in session seconds."""
        if self.offset is None:
            return []
        rows = []
        for row in self.judge:
            if "answers" in row and isinstance(row.get("capture"), (int, float)):
                rows.append((row["capture"] - self.offset, row["answers"]))
        return sorted(rows, key=lambda item: item[0])

    def ticks(self, t0: float, t1: float) -> list[dict]:
        return [row for row in self.play if t0 <= row["t"] <= t1]

    def reading(self, t: float) -> dict:
        """The minimap reading of the tick at or before `t`."""
        times = [row["t"] for row in self.play]
        index = bisect.bisect_right(times, t) - 1
        return (self.play[max(index, 0)].get("reading") or {}) if self.play else {}

    # ---- the figure's mode
    def mode_over(self, t0: float, t1: float) -> Mode:
        """foot or vehicle over a stretch: the minimap class of its ticks and the judge's answers each
        vote by majority; where both vote they have to agree, and a stretch that is mixed or thin is
        None."""
        counts = Counter()
        for row in self.ticks(t0, t1):
            reading = row.get("reading") or {}
            if reading.get("corrupt"):
                continue
            name = {"flat": "foot", "tilted": "vehicle"}.get(reading.get("minimap"))
            if name:
                counts[name] += 1
        judged = Counter()
        for t, answers in self.judgments:
            if t0 <= t <= t1:
                value = (answers.get("mode") or {}).get("value")
                if value in ("foot", "vehicle"):
                    judged[value] += 1
        minimap = _vote(counts, MIN_MINIMAP)
        judge = _vote(judged, MIN_JUDGED)
        info = {"minimap": minimap, "judge": judge}
        if minimap["mode"] and judge["mode"]:
            if minimap["mode"] == judge["mode"]:
                return Mode(minimap["mode"], "agree", **info)
            return Mode(None, "conflict", **info)
        if minimap["mode"]:
            if judge["n"] >= MIN_JUDGED:
                return Mode(None, "mixed", **info)  # the judge was asked a lot and is not sure
            return Mode(minimap["mode"], "minimap", **info)
        if judge["mode"]:
            if minimap["n"] >= MIN_MINIMAP:
                return Mode(None, "mixed", **info)
            return Mode(judge["mode"], "judge", **info)
        thin = minimap["n"] < MIN_MINIMAP and judge["n"] < MIN_JUDGED
        return Mode(None, "too-few" if thin else "mixed", **info)

    # ---- the pictures
    @cached_property
    def _frame_times(self) -> list[tuple[float, int]]:
        return sorted((row["t"], row["i"]) for row in self.frame_log if "t" in row and "i" in row)

    def frame(self, t: float):
        """The RGB 1280x720 frame nearest to second `t`, or None where there is no video or frame."""
        if self._frames is not None:
            return self._frames(t)
        key = ("frame", round(t, 3))
        if key in self._cache:
            return self._cache[key]
        frame = self._decode(t)
        self._cache[key] = frame
        if len(self._cache) > 64:
            self._cache.pop(next(iter(self._cache)))
        return frame

    def _decode(self, t: float):
        import cv2

        video = self.folder / "video.mp4"
        if not video.exists():
            return None
        if self._capture is None:
            self._capture = cv2.VideoCapture(str(video))
        capture = self._capture
        if not capture.isOpened():
            return None
        count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        times = self._frame_times
        if times:
            at = bisect.bisect_left([item[0] for item in times], t)
            at = min(max(at, 0), len(times) - 1)
            index = times[at][1]
        else:
            index = round(t * (capture.get(cv2.CAP_PROP_FPS) or FPS_FALLBACK))
        index = min(max(index, 0), max(count - 1, 0))
        capture.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, bgr = capture.read()
        if not ok:
            return None
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        if rgb.shape[:2] != (720, 1280):
            rgb = cv2.resize(rgb, (1280, 720), interpolation=cv2.INTER_AREA)
        return rgb

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None

    @property
    def has_pictures(self) -> bool:
        return self._frames is not None or (self.folder / "video.mp4").exists()

    def hud_at(self, t: float):
        """The HUD reader on the stored frame at `t`: the pilot's own reader, at another moment than the
        skill read it. None without a picture."""
        key = ("hud", round(t, 3))
        if key not in self._cache:
            frame = self.frame(t)
            if frame is None:
                self._cache[key] = None
            else:
                from . import hud

                self._cache[key] = hud.read(frame)
        return self._cache[key]

    def screens(self, t0: float, t1: float, step: float = 0.25) -> list[tuple[float, str]]:
        """(second, screen) over a stretch: from the pictures where there are some, else from the head's
        requests, which are sparse."""
        found = []
        if self.has_pictures:
            t = t0
            while t <= t1 + 1e-9:
                hud = self.hud_at(t)
                if hud is not None:
                    found.append((round(t, 3), hud.screen))
                t += step
            return found
        for request in self.requests:
            screen = (request.get("hud") or {}).get("screen")
            if screen and t0 <= request["t"] <= t1:
                found.append((request["t"], screen))
        return found

    def purple_at(self, t: float) -> list[tuple[float, float]]:
        key = ("purple", round(t, 3))
        if key not in self._cache:
            frame = self.frame(t)
            self._cache[key] = None if frame is None else purple_blips(frame)
        return self._cache[key]

    def view_at(self, t: float):
        """The camera's view the detector gives at `t`: a camera.ViewReading, or None without a picture
        or a detector."""
        key = ("view", round(t, 3))
        if key not in self._cache:
            frame = self.frame(t)
            reading = None
            if frame is not None:
                reading = read_figure_view(frame, self._detect)
            self._cache[key] = reading
        return self._cache[key]


def _vote(counts: Counter, minimum: int) -> dict:
    n = sum(counts.values())
    if n < minimum:
        return {"mode": None, "n": n, "share": None}
    name, top = counts.most_common(1)[0]
    share = top / n
    return {"mode": name if share >= AGREE else None, "n": n, "share": round(share, 3)}


# ---- readers run on the stored pictures
def purple_blips(frame) -> list[tuple[float, float]]:
    """The purple waypoint blips in the minimap of an RGB 1280x720 frame, as (x right, y up) from the
    player's arrow in crop pixels, the way the reader's blips are given.

    The minimap reader knows yellow, blue and red discs and no purple one, so a waypoint on foot (the
    game draws the route line only while the figure sits in a vehicle) is in no log. It shows as a small
    purple four-lobed mark, inside the map or pinned to its rim, where it can also lie over the end of the
    three bars under the map. A route line is long and thin and is left out by its size."""
    import cv2
    import numpy as np

    x, y, w, h = HUD_RECT
    crop = frame[y : y + h, x : x + w]
    hue, sat, value = cv2.split(cv2.cvtColor(crop, cv2.COLOR_RGB2HSV))
    mask = ((hue >= 128) & (hue <= 156) & (sat >= 75) & (value >= 95)).astype(np.uint8)
    mask[:, :30] = 0
    mask[:, 232:] = 0
    mask[:22] = 0
    mask[158:] = 0
    # The compass marker (a black disc with an N) can sit over a blip and cut it in two, so what lies
    # within two pixels is one blip.
    merged = cv2.dilate(mask, np.ones((5, 5), np.uint8))
    count, labels, stats, _centres = cv2.connectedComponentsWithStats(merged, 8)
    found = []
    for i in range(1, count):
        left, top, width, height, _ = stats[i]
        area = int(
            mask[top : top + height, left : left + width][
                labels[top : top + height, left : left + width] == i
            ].sum()
        )
        if 8 <= width <= 24 and 8 <= height <= 24 and area >= 14:
            ys, xs = np.nonzero((labels == i) & (mask > 0))
            found.append((round(float(xs.mean()) - ARROW_XY[0], 1), round(ARROW_XY[1] - float(ys.mean()), 1)))
    return found


_DETECTOR = None


def read_figure_view(frame, detect: Callable | None = None):
    """camera.read_view on the detector's figure in `frame`. The detector is the pilot's own."""
    from .camera import VEHICLES, read_view

    if detect is None:
        global _DETECTOR
        if _DETECTOR is None:
            try:
                from .objects import Detector

                _DETECTOR = Detector().detect_split
            except (RuntimeError, OSError, ImportError):
                _DETECTOR = False
        if _DETECTOR is False:
            return None
        detect = _DETECTOR
    kept, figure, vehicle = detect(frame)
    vehicles = tuple(d for d in kept if d.kind in VEHICLES) + ((vehicle,) if vehicle else ())
    others = tuple(d for d in kept if d.kind == "person")
    return read_view(figure, frame.shape, vehicles=vehicles, others=others)


# ---- what a try is
@dataclass(frozen=True)
class Try:
    """A session seen as the try of one capability: whose verdicts count and when they ran."""

    session: Session
    skills: tuple[str, ...]
    plan: tuple[str, ...]

    @cached_property
    def segments(self) -> list[tuple[str, float, float]]:
        """(skill, first tick, first tick of the next skill) in the order they ran."""
        rows = [
            (row["t"], (row.get("skill") or {}).get("name"))
            for row in self.session.play
            if (row.get("skill") or {}).get("name")
        ]
        out: list[list] = []
        for t, name in rows:
            if not out or out[-1][0] != name:
                out.append([name, t, t])
            out[-1][2] = t
        for current, following in pairwise(out):
            current[2] = following[1]
        return [(name, t0, t1) for name, t0, t1 in out]

    def window(self, step: int | None) -> Window:
        """The whole session, or the stretch of the plan's `step`-th skill."""
        session = self.session
        if step is None:
            return Window(session.start, session.end)
        names = list(self.plan)
        wanted = names[step]
        nth = names[: step + 1].count(wanted)
        seen = 0
        for name, t0, t1 in self.segments:
            if name == wanted:
                seen += 1
                if seen == nth:
                    return Window(t0, t1)
        return Window(session.end, session.end)

    @property
    def t0(self) -> float:
        return next((t0 for name, t0, _ in self.segments if name in self.skills), self.session.start)


# ---- the pieces
PIECES: dict[str, Callable[..., Evidence]] = {}


def piece(function: Callable[..., Evidence]) -> Callable[..., Evidence]:
    PIECES[function.__name__] = function
    return function


def combine(parts: list[tuple[str, Evidence]]) -> Evidence:
    """All yes is yes, any no is no, and what is left is not measurable. The numbers of every piece are
    kept under the piece's name; the moment is the first failing piece's."""
    numbers = {name: ev.numbers for name, ev in parts}
    missing = "; ".join(ev.missing for _, ev in parts if ev.ok is None and ev.missing)
    failing = next((ev for _, ev in parts if ev.ok is False), None)
    moment = failing.moment if failing else next((ev.moment for _, ev in parts if ev.moment), None)
    said = tuple((name, ev.ok) for name, ev in parts)
    if failing:
        return Evidence(False, numbers, "", moment, said)
    if all(ev.ok for _, ev in parts):
        return Evidence(True, numbers, "", moment, said)
    return Evidence(None, numbers, missing, moment, said)


def _mode_numbers(mode: Mode, prefix: str) -> dict:
    return {
        f"{prefix}_mode": mode.mode,
        f"{prefix}_basis": mode.why,
        f"{prefix}_minimap": mode.minimap,
        f"{prefix}_judge": mode.judge,
    }


def _unclear_mode(mode: Mode, where: str) -> str:
    if mode.why == "conflict":
        return (
            f"the minimap class and the judge name different modes {where}; the stretch is not clear "
            "enough to say on foot or seated"
        )
    return f"the figure's mode {where} is not clear over the stretch ({mode.why})"


def _at_end(run: Try, want: str, step: int | None, seconds: float) -> Evidence:
    window = run.window(step)
    mode = run.session.mode_over(max(run.session.start, window.t1 - seconds), window.t1)
    numbers = _mode_numbers(mode, "end")
    if mode.mode is None:
        return Evidence(None, numbers, _unclear_mode(mode, "at the end"))
    ok = mode.mode == want
    moment = (
        None
        if ok
        else (max(window.t1 - 0.5, 0.0), f"the end of the stretch, where the figure was still {mode.mode}")
    )
    return Evidence(ok, numbers, "", moment)


@piece
def on_foot_at_end(run: Try, step: int | None = None, seconds: float = END_STRETCH) -> Evidence:
    """The figure is on foot over the last `seconds`: majority of the minimap class agreed by the judge."""
    return _at_end(run, "foot", step, seconds)


@piece
def seated_at_end(run: Try, step: int | None = None, seconds: float = END_STRETCH) -> Evidence:
    """The figure sits in a vehicle over the last `seconds`."""
    return _at_end(run, "vehicle", step, seconds)


@piece
def seated_within(run: Try, seconds: float = 20.0, step: int | None = None) -> Evidence:
    """A stretch of 1.5 s in which the figure sits in a vehicle begins within `seconds` of the skill's
    first tick (not of the session's: the opening takes its own time before the plan). Read from the
    minimap class and the judge as `on_foot_at_end` does, never from one tick."""
    session = run.session
    window = run.window(step) if step is not None else Window(run.t0, session.end)
    t = max(window.t0, session.start)
    first, undecided = None, 0
    while t + START_STRETCH <= window.t1 + 1e-9:
        mode = session.mode_over(t, t + START_STRETCH)
        if mode.mode == "vehicle":
            first = t
            break
        undecided += mode.mode is None
        t += 0.5
    numbers = {"seated_from": None if first is None else round(first - window.t0, 2), "limit": seconds}
    if first is not None:
        ok = first - window.t0 <= seconds
        moment = (
            None if ok else (window.t0 + seconds, f"{seconds:g} s after the skill began, still not seated")
        )
        return Evidence(ok, numbers, "", moment)
    if undecided:
        numbers["unclear_stretches"] = undecided
        return Evidence(
            None, numbers, "the figure's mode is not clear over the stretches after the skill began"
        )
    return Evidence(
        False,
        numbers,
        "",
        (min(window.t0 + seconds, window.t1), f"{seconds:g} s after the skill began, still on foot"),
    )


@piece
def game_back(run: Try, step: int | None = None, seconds: float = 1.5) -> Evidence:
    """The game's screen shows again over the last `seconds`, nothing left open: the HUD reader on the
    stored pictures (the head's last request where there is no video)."""
    window = run.window(step)
    screens = run.session.screens(max(window.t0, window.t1 - seconds), window.t1)
    if not screens:
        return Evidence(
            None, {}, "no picture and no head request at the end: the HUD screen is missing from the log"
        )
    shown = Counter(screen for _, screen in screens)
    numbers = {"end_screens": dict(shown)}
    ok = shown["game"] / len(screens) >= 0.75
    other = next((t for t, screen in screens if screen != "game"), None)
    return Evidence(
        ok,
        numbers,
        "",
        None
        if ok
        else (other if other is not None else window.t1, f"the game's screen is not back: {dict(shown)}"),
    )


@piece
def map_opened(run: Try, step: int | None = None) -> Evidence:
    """The pause menu or the map showed at some moment of the stretch: the HUD reader on the stored
    pictures, and the judge's "a menu is drawn on top" as a second witness."""
    session = run.session
    window = run.window(step)
    screens = session.screens(window.t0, window.t1)
    shown = Counter(screen for _, screen in screens)
    overlay = [
        (answers.get("overlay") or {}).get("value")
        for t, answers in session.judgments
        if window.t0 <= t <= window.t1
    ]
    numbers = {"screens": dict(shown), "judged_overlay": overlay.count(True), "judged": len(overlay)}
    if not screens and not overlay:
        return Evidence(None, numbers, "no HUD screen and no judgment in the log: the screen is not recorded")
    opened = bool(shown["map"] or shown["pause"]) or any(a and b for a, b in pairwise(overlay))
    moment = (
        None if opened else (window.t0 + 1.0, "one second after the try began: no menu or map on the screen")
    )
    return Evidence(opened, numbers, "", moment)


def _blips_around(session: Session, times: list[float]) -> tuple[list, int]:
    seen = [(t, session.purple_at(t)) for t in times]
    seen = [(t, found) for t, found in seen if found is not None]
    return [found for _, found in seen], len(seen)


def _stand(frames: list[list]) -> tuple[float, tuple[float, float] | None]:
    """How often a blip showed and where: the share of the frames with one, and the median place."""
    if not frames:
        return 0.0, None
    shown = [found[0] for found in frames if found]
    if not shown:
        return 0.0, None
    xs, ys = sorted(p[0] for p in shown), sorted(p[1] for p in shown)
    return len(shown) / len(frames), (xs[len(xs) // 2], ys[len(ys) // 2])


@piece
def waypoint_changed(run: Try, step: int | None = None, same_px: float = SAME_PX) -> Evidence:
    """A waypoint stands after the try that was not there before or stands elsewhere.

    On foot the game draws no route line, so the waypoint is its purple blip in the minimap, inside it or
    on its rim: the picture before the map opened against the picture at the end. Seated, a purple route
    is the sign, and a new distance when one stood already. The class of the minimap tells which of the
    two applies and is taken over a stretch, a mixed stretch being not measurable. A blip that stands
    where it stood before is not measurable either: a waypoint removed and set again on the same place, as
    the legend skill does on purpose, looks like a try that changed nothing."""
    session = run.session
    window = run.window(step)
    mode = session.mode_over(max(session.start, window.t1 - END_STRETCH), window.t1)
    numbers = _mode_numbers(mode, "end")
    if mode.mode is None:
        return Evidence(None, numbers, _unclear_mode(mode, "at the end"))
    if mode.mode == "vehicle":
        return _route_changed(session, window, numbers)
    if not session.has_pictures:
        return Evidence(None, numbers, "no video: the waypoint blip is in no log, only in the picture")
    return _blip_changed(session, window, numbers, same_px)


def minimap_read(row: dict) -> dict | None:
    """The reading of a tick when the minimap was there to read: not damaged, not hidden by the map or a
    menu."""
    reading = row.get("reading") or {}
    return None if reading.get("corrupt") or reading.get("minimap") not in ("flat", "tilted") else reading


def _route_changed(session: Session, window: Window, numbers: dict) -> Evidence:
    def share(t0: float, t1: float) -> tuple[float | None, float | None]:
        rows = [read for read in map(minimap_read, session.ticks(t0, t1)) if read]
        if len(rows) < MIN_MINIMAP:
            return None, None
        routed = sum(r.get("route") in ("purple", "yellow") for r in rows) / len(rows)
        distances = [r["gps_distance"] for r in rows if isinstance(r.get("gps_distance"), (int, float))]
        return routed, (distances[-1] if distances else None)

    before, before_distance = share(window.t0, window.t0 + 1.0)
    after, after_distance = share(max(window.t0, window.t1 - 2.0), window.t1)
    numbers.update(
        route_before=before, route_after=after, distance_before=before_distance, distance_after=after_distance
    )
    if after is None:
        return Evidence(None, numbers, "the minimap was not readable in the last two seconds")
    if after <= 0.2:
        return Evidence(
            False, numbers, "", (max(window.t1 - 1.0, 0.0), "no route on the minimap at the end, seated")
        )
    if after < 0.6:
        return Evidence(None, numbers, "the route comes and goes in the last two seconds")
    if before is None:
        return Evidence(
            None, numbers, "the minimap was not readable in the first second: nothing says if a route stood"
        )
    if not before:
        return Evidence(True, numbers)
    if (
        before_distance is not None
        and after_distance is not None
        and abs(before_distance - after_distance) > 20
    ):
        return Evidence(True, numbers)
    return Evidence(
        None,
        numbers,
        "a route stood before and at the end at the same distance: a changed waypoint cannot be told "
        "from none",
    )


def _map_hidden_runs(session: Session, window: Window) -> list[tuple[float, float]]:
    """The stretches in which the minimap reader sees no map for at least five ticks: the map or a menu
    covers it."""
    runs, start, count, last = [], None, 0, 0.0
    for row in session.ticks(window.t0, window.t1):
        hidden = (row.get("reading") or {}).get("minimap") == "none"
        if hidden:
            start = row["t"] if start is None else start
            count += 1
            last = row["t"]
        else:
            if start is not None and count >= 5:
                runs.append((start, last))
            start, count = None, 0
    if start is not None and count >= 5:
        runs.append((start, last))
    return runs


def _camera_turn(session: Session, t_before: float, t_after: float) -> tuple[float, float] | None:
    """How far the camera turned between two pictures of a figure that stands still: the minimap's roads
    rotate about the arrow, so the angle that lays the first picture on the second is the turn. (angle in
    degrees, correlation), or None where the map shows too little to say."""
    import cv2
    import numpy as np

    before, after = session.frame(t_before), session.frame(t_after)
    if before is None or after is None:
        return None
    x, y, w, h = HUD_RECT
    grey = [
        cv2.cvtColor(f[y : y + h, x : x + w], cv2.COLOR_RGB2GRAY).astype(np.float32) for f in (before, after)
    ]
    rows, cols = np.mgrid[0:h, 0:w]
    radius = np.hypot(cols - ARROW_XY[0], rows - ARROW_XY[1])
    mask = (radius > 12) & (radius < 60) & (cols > 40) & (cols < 210) & (rows > 32) & (rows < 138)
    target = grey[1][mask] - grey[1][mask].mean()
    scores = []
    for angle in np.arange(-20.0, 20.01, 0.5):
        matrix = cv2.getRotationMatrix2D((float(ARROW_XY[0]), float(ARROW_XY[1])), float(angle), 1.0)
        turned = cv2.warpAffine(
            grey[0], matrix, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE
        )
        values = turned[mask] - turned[mask].mean()
        norm = float(np.linalg.norm(values) * np.linalg.norm(target))
        scores.append((float(values @ target) / norm if norm else 0.0, float(angle)))
    best = max(scores)
    # A map with few roads in it matches at every angle: the peak has to stand clear of the rest.
    rest = max(score for score, angle in scores if abs(angle - best[1]) > 4)
    if best[0] < 0.9 or best[0] - rest < 0.03:
        return None
    return best[1], best[0]


def _blip_changed(session: Session, window: Window, numbers: dict, same_px: float) -> Evidence:
    # The first picture of a session can belong to the game's idle camera, a few frames of another view
    # that snap back after the first input, and the minimap hides a moment before the HUD reader knows
    # the pause menu. So the pictures before are those from 0.3 s on in which the minimap reader still
    # sees the map, up to the tick at which it loses it for good.
    hidden = _map_hidden_runs(session, Window(window.t0 + 0.2, window.t1))
    menu: list[float] = []
    if not hidden:
        screens = session.screens(window.t0, min(window.t1, window.t0 + 12.0), 0.5)
        if not screens:
            return Evidence(
                None, numbers, "no HUD screens: the picture is needed to tell when the map was open"
            )
        menu = [t for t, screen in screens if screen != "game"]
        if not menu:
            numbers["map_opened"] = False
            return Evidence(
                False, numbers, "", (window.t0 + 1.0, "no map or menu opened, so no waypoint could be set")
            )
    stop = (hidden[0][0] if hidden else min(menu)) - 0.05
    count = int(max(stop - (window.t0 + 0.3), 0) / 0.05) + 1
    before_times = [round(window.t0 + 0.3 + 0.05 * i, 3) for i in range(count)]
    before_times = [t for t in before_times if t <= stop][-6:]
    # The camera turns now and then by itself (the conductor touches it after 15 quiet seconds), which
    # moves a blip on the rim: the pictures after are those just after the map closed.
    closed = (hidden[-1][1] if hidden else menu[-1] + 0.25) + 0.2
    after_times = [round(closed + 0.75 + 0.25 * i, 3) for i in range(6)]
    after_times = [t for t in after_times if t <= window.t1] or [
        round(max(window.t0, window.t1 - 1.5) + 0.25 * i, 3) for i in range(6)
    ]
    after_screens = session.screens(after_times[0], after_times[-1], 0.25)
    back = bool(after_screens) and sum(s == "game" for _, s in after_screens) / len(after_screens) >= 0.75
    before, nb = _blips_around(session, before_times)
    after, na = _blips_around(session, after_times)
    seen_before, place_before = _stand(before)
    seen_after, place_after = _stand(after)
    numbers.update(
        map_opened=True,
        blip_before=place_before,
        blip_before_share=round(seen_before, 2),
        blip_after=place_after,
        blip_after_share=round(seen_after, 2),
        frames_before=nb,
        frames_after=na,
    )
    if not back:
        return Evidence(None, numbers, "the game's screen is not back after the map, the minimap is hidden")
    if nb < 2 or na < 2:
        return Evidence(None, numbers, "too few steady pictures before the map opened or after it closed")
    if seen_after < 0.5:
        if seen_after > 0.0:
            return Evidence(
                None, numbers, "the waypoint blip shows on some pictures after the map and not on others"
            )
        return Evidence(
            False,
            numbers,
            "",
            (after_times[-1], "no waypoint blip in the minimap after the map closed"),
        )
    if 0.0 < seen_before < 0.5:
        return Evidence(
            None, numbers, "the waypoint blip shows on some pictures before the map opened and not on others"
        )
    if seen_before < 0.5:
        return Evidence(True, numbers)
    shift = math.dist(place_before, place_after)
    numbers["shift_px"] = round(shift, 1)
    if shift <= same_px:
        return Evidence(
            None,
            numbers,
            "the waypoint blip stands where it stood before the try: a waypoint set again on the same place "
            "looks like a try that changed nothing; name another place each try",
        )
    turn = _camera_turn(session, before_times[-1], after_times[0])
    numbers["camera_turn"] = None if turn is None else {"degrees": turn[0], "correlation": round(turn[1], 3)}
    if turn is not None and abs(turn[0]) <= 1.5:
        return Evidence(True, numbers)  # the camera stood and the blip moved: another place
    # The camera turned, or no one can tell: a degree of turn moves a rim blip by up to 1.7 px.
    allowance = (abs(turn[0]) if turn is not None else 12.0) * 1.7 + same_px
    if shift > allowance + 6.0:
        return Evidence(True, numbers)
    return Evidence(
        None,
        numbers,
        f"the waypoint blip moved {shift:.0f} px, which a turn of the camera explains: it may be the "
        "same place",
    )


@piece
def view_far_at_end(run: Try, seconds: float = 3.0, samples: int = 8) -> Evidence:
    """The figure stands in the far view over the last `seconds`: the pilot's detector and the skill's
    bands on the stored pictures. Independent of the skill's moment and of its three-detection window,
    not of the detector or of the bands, which are the same."""
    session = run.session
    if not session.has_pictures:
        return Evidence(None, {}, "no video: the figure's box is in no log, only in the picture")
    step = seconds / max(samples - 1, 1)
    times = [round(max(session.start, session.end - seconds) + step * i, 3) for i in range(samples)]
    readings = [(t, session.view_at(t)) for t in times]
    readings = [(t, r) for t, r in readings if r is not None]
    if not readings:
        return Evidence(None, {}, "the detector gave no reading: the model or CoreML is not available")
    views = Counter(r.view for _, r in readings)
    heights = [round(r.height, 3) for _, r in readings if r.height is not None]
    numbers = {"views": dict(views), "heights": heights}
    n = len(readings)
    if views["far"] / n >= 0.75:
        return Evidence(True, numbers)
    named = [v for v in ("middle", "near", "none") if views[v] / n >= 0.75]
    if named:
        return Evidence(
            False, numbers, "", (session.end - 0.5, f"the view at the end is {named[0]}, not far")
        )
    return Evidence(None, numbers, f"the readings at the end do not agree on a view ({dict(views)})")


SINCE: dict[str, Callable[..., tuple[float, str] | None]] = {}


def since(name: str):
    """Registers, for a piece, how to find the second from which what it proves held. A failure where the
    proof says the thing happened and the skill said it did not points there."""

    def register(function):
        SINCE[name] = function
        return function

    return register


@since("view_far_at_end")
def view_far_since(run: Try, step: float = 0.5) -> tuple[float, str] | None:
    session = run.session
    t, first, missed = session.end - 0.1, None, 0
    while t >= session.start:
        reading = session.view_at(round(t, 3))
        if reading is not None and reading.view == "far":
            first, missed = t, 0
        else:
            missed += 1
            if missed >= 2:  # a figure at the band's edge reads between two bands now and then
                break
        t -= step
    if first is None:
        return None
    return first, "the far view stood from here to the end by the detector, before the skill ended"


def _distances(run: Try, t0: float, t1: float) -> list[tuple[float, float]]:
    return [
        (row["t"], row["reading"]["gps_distance"])
        for row in run.session.ticks(t0, t1)
        if isinstance((row.get("reading") or {}).get("gps_distance"), (int, float))
    ]


GPS_MISSING = "the route distance in metres is read only on a vehicle's map: nothing was read in the stretch"


@piece
def distance_fell(run: Try, metres: float = 100.0, within: float = 30.0, step: int | None = None) -> Evidence:
    """The distance to the destination, as the game prints it on the vehicle map, fell by `metres`
    within `within` seconds of the first reading after the skill began."""
    window = run.window(step) if step is not None else Window(run.t0, run.session.end)
    readings = _distances(run, window.t0, window.t1)
    if len(readings) < 2:
        return Evidence(None, {"readings": len(readings)}, GPS_MISSING)
    first_t, first = readings[0]
    reach = [d for t, d in readings if t <= first_t + within]
    fell = first - min(reach)
    numbers = {"first_metres": first, "nearest_metres": min(reach), "fell_metres": fell, "within": within}
    ok = fell >= metres
    moment = (
        None
        if ok
        else (
            min(first_t + within, window.t1),
            f"{within:g} s after the first distance reading: {fell:g} m nearer, not {metres:g}",
        )
    )
    return Evidence(ok, numbers, "", moment)


@piece
def never_held(run: Try, seconds: float = 5.0, within: float = 30.0, step: int | None = None) -> Evidence:
    """The distance to the destination never stood still (within 3 m) for `seconds` in the first
    `within` seconds of the readings. Needs a reading at least every 3 s."""
    window = run.window(step) if step is not None else Window(run.t0, run.session.end)
    readings = _distances(run, window.t0, window.t1)
    if len(readings) < 2:
        return Evidence(None, {"readings": len(readings)}, GPS_MISSING)
    begin = readings[0][0]
    readings = [(t, d) for t, d in readings if t <= begin + within]
    gap = max(b[0] - a[0] for a, b in pairwise(readings)) if len(readings) > 1 else float("inf")
    longest, at = 0.0, begin
    for i, (t, d) in enumerate(readings):
        last = t
        for later_t, later_d in readings[i + 1 :]:
            if abs(later_d - d) > 3.0:
                break
            last = later_t
        if last - t > longest:
            longest, at = last - t, t
    numbers = {"longest_hold": round(longest, 2), "max_reading_gap": round(gap, 2), "limit": seconds}
    if gap > 3.0:
        return Evidence(None, numbers, "the distance was read less often than every 3 s")
    ok = longest < seconds
    return Evidence(
        ok,
        numbers,
        "",
        None if ok else (at + seconds, f"the distance stood still from {at:.1f} s for {longest:.1f} s"),
    )


@piece
def arrived(run: Try, metres: float = 30.0, step: int | None = None) -> Evidence:
    """The last distance read is within `metres` and the vehicle was stopped: the distance did not change
    by more than 3 m over the last 2 s of the readings."""
    window = run.window(step) if step is not None else Window(run.t0, run.session.end)
    readings = _distances(run, window.t0, window.t1)
    if not readings:
        return Evidence(None, {"readings": 0}, GPS_MISSING)
    last_t, last = readings[-1]
    recent = [d for t, d in readings if t >= last_t - 2.0]
    still = max(recent) - min(recent) <= 3.0
    numbers = {"last_metres": last, "last_read_at": round(last_t, 2), "stopped": still}
    ok = last <= metres and still
    why = f"the last distance is {last:g} m" + ("" if still else " and the vehicle was moving")
    return Evidence(ok, numbers, "", None if ok else (last_t, why))


@piece
def moving_on_most_ticks(run: Try, seconds: float = 20.0, share: float = 0.5, hold: float = 3.0) -> Evidence:
    """A movement field of the log: more than `share` of the stretch moving and never held for `hold`.
    The log has no such field that the skill does not read itself ("motion=going" in a skill's reason is
    the skill's own reading), so this is not measurable until `cli play` writes a `moving` bool per tick."""
    samples = [(r["t"], r["moving"]) for r in run.session.play if isinstance(r.get("moving"), bool)]
    samples = [(t, m) for t, m in samples if t <= run.t0 + seconds + 0.5]
    if len(samples) < 2 or samples[-1][0] - samples[0][0] < seconds - 1:
        return Evidence(
            None,
            {},
            "no independent movement field in play.jsonl: a bool `moving` per tick from the flow reader, "
            "written by cli play, at less than 3 s apart for the stretch",
        )
    span = samples[-1][0] - samples[0][0]
    fraction = sum(b[0] - a[0] for a, b in pairwise(samples) if a[1]) / span
    longest, start = 0.0, None
    for t, moving in samples:
        if not moving and start is None:
            start = t
        if moving and start is not None:
            longest, start = max(longest, t - start), None
    if start is not None:
        longest = max(longest, samples[-1][0] - start)
    gap = max(b[0] - a[0] for a, b in pairwise(samples))
    numbers = {
        "moving_fraction": round(fraction, 3),
        "longest_hold": round(longest, 2),
        "max_sample_gap": round(gap, 2),
    }
    if gap >= 3:
        return Evidence(None, numbers, "the movement field has gaps of 3 s or more")
    ok = fraction > share and longest < hold
    return Evidence(
        ok, numbers, "", None if ok else (samples[0][0] + hold, "held or still for most of the stretch")
    )


@piece
def within_metres_of_blip(run: Try, metres: float = 10.0) -> Evidence:
    """The distance to the blip the skill walked to, in metres, at the end: a field the log does not hold
    (the reader gives blips in minimap pixels, not metres, and the skill does not log which one it chose)."""
    last = (run.session.play[-1].get("reading") or {}) if run.session.play else {}
    distance = last.get("target_distance_metres")
    if isinstance(distance, (int, float)) and last.get("target_color") == "yellow":
        return Evidence(distance <= metres, {"target_metres": distance}, "", None)
    return Evidence(
        None,
        {},
        "distance in metres to the selected blip is not logged: the minimap reader gives pixels and "
        "cli play does not write the chosen blip",
    )


@piece
def unmeasured(run: Try, what: str = "", missing: str = "") -> Evidence:
    """A part of the card's "done when" that no record can show. It keeps the card's wording in the entry
    and makes every success of the capability not measurable, while a failure of another piece still
    counts. `missing` names the field and where it would be written."""
    return Evidence(None, {"unmeasured": what}, missing or f"not measurable from any log: {what}")


def run_pieces(run: Try, pieces: tuple[tuple[str, dict], ...]) -> Evidence:
    parts: list[tuple[str, Evidence]] = []
    for name, params in pieces:
        if name not in PIECES:
            raise KeyError(f"no proof piece named {name!r}; known: {sorted(PIECES)}")
        label = name if sum(n == name for n, _ in pieces) == 1 else f"{name}[{len(parts)}]"
        parts.append((label, PIECES[name](run, **params)))
    return combine(parts)


def describe(pieces: tuple[tuple[str, dict], ...]) -> str:
    """One line for a catalogue entry's proof: the pieces and their first docstring lines."""
    lines = []
    for name, params in pieces:
        doc = (PIECES[name].__doc__ or "").strip().splitlines()[0] if name in PIECES else "unknown piece"
        arguments = ", ".join(f"{k}={v!r}" for k, v in params.items())
        lines.append(f"{name}({arguments}): {doc}")
    return " | ".join(lines)


def piece_names() -> list[str]:
    return sorted(PIECES)


def as_numbers(value: Any) -> Any:
    """A value for the ledger: numpy scalars to numbers, tuples to lists."""
    if isinstance(value, dict):
        return {str(k): as_numbers(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [as_numbers(v) for v in value]
    if hasattr(value, "item"):
        return value.item()
    return value
