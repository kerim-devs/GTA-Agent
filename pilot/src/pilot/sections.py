"""Offline, conservative sections on the recording's frame clock."""

import json
import math
import time
from bisect import bisect_left, bisect_right
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from pathlib import Path

import cv2
import numpy as np

from pilot.contract import Hud, Pad, Reading
from pilot.hud import read as read_hud
from pilot.judge import QUESTIONS, encode, endpoint, letters, post, probability
from pilot.minimap import read as read_minimap
from pilot.replay import hud_crop

SAMPLE_HZ = 10
KINDS = {"drive", "foot", "cutscene", "menu", "banner", "loading", "unknown"}
MENUS = {"pause", "map", "interaction_menu", "phone", "weapon_wheel"}
BANNERS = {"passed", "failed", "wasted", "busted"}
# The judge is asked about one frame in every second of a stretch the readers leave open, and a
# reader's foot or vehicle that rests on the minimap alone is open within this many seconds of a
# change of the reader's mind (a car is entered or left there) or while stars tilt the map.
DOUBT_SECONDS = 3.0
NEIGHBOUR_SECONDS = 1.5
JUDGE_WIDTH = 640
# Asked one by one: in one request the model answered the overlay question right on 55 percent of the
# frames, alone on 96 (lab/judge/results). The wanted level is the readers' business.
SCORED = ("banner", "overlay", "mode")


@dataclass(frozen=True)
class Sample:
    time: float
    frame: int
    reading: Reading
    hud: Hud
    pad: Pad | None = None
    # What the judge said about this frame's second, once a neighbouring second said the same:
    # the answers of QUESTIONS as values, e.g. {"mode": "none", "overlay": False, "banner": False}.
    judge: dict | None = None


def pad_verdict(pad: Pad | None, minimap: str) -> str | None:
    """What the controller alone settles: a pushed stick with Cross is a run, a held trigger with
    steering on a tilted map is a car."""
    if pad is None:
        return None
    running = "cross" in {button.lower() for button in pad.buttons}
    moving = math.hypot(*pad.left) > 0.2
    steering = abs(pad.left[0]) > 0.2
    trigger = max(pad.r2, pad.l2) > 0.2
    if running and moving and not trigger:
        return "foot"
    if minimap == "tilted" and trigger and steering and not running:
        return "drive"
    return None


def judge_kind(answer: dict | None) -> str | None:
    """The section kind a judge's answers name; None where they name nothing."""
    if not answer:
        return None
    if answer.get("banner"):
        return "banner"
    if answer.get("overlay"):
        return "menu"
    return {"foot": "foot", "vehicle": "drive", "none": "cutscene"}.get(answer.get("mode"))


def decide(sample: Sample) -> str:
    """Replace this function with judge answers without changing segmentation."""
    reading, hud, pad = sample.reading, sample.hud, sample.pad
    if reading.corrupt:
        return "unknown"
    if hud.screen in MENUS:
        return "menu"
    if hud.screen in BANNERS:
        return "banner"
    if hud.screen == "loading":
        return "loading"
    # Neither foot nor vehicle without a HUD is a cutscene: the readers cannot say so, the judge can.
    judged = judge_kind(sample.judge)
    if judged is not None:
        return judged
    if hud.screen != "game":
        return "unknown"
    if reading.minimap == "none":
        return "unknown"
    verdict = pad_verdict(pad, reading.minimap)
    if verdict is not None:
        return verdict
    if reading.minimap == "flat":
        return "foot"
    if reading.minimap == "tilted" and hud.wanted == 0:
        return "drive"
    return "unknown"


def frame_rows(recording: Path) -> list[dict]:
    rows = [
        json.loads(line) for line in (recording / "frames.jsonl").read_text().splitlines() if line.strip()
    ]
    previous = -math.inf
    for index, row in enumerate(rows):
        if row["i"] != index or not math.isfinite(row["t"]) or row["t"] <= previous:
            raise ValueError("frames.jsonl must have contiguous indices and increasing finite times")
        previous = row["t"]
    return rows


def sample_indices(rows: Iterable[dict]) -> list[int]:
    """Choose at most one source frame per 100 ms, without assuming video FPS."""
    selected = []
    deadline = None
    for row in rows:
        timestamp = row["t"]
        if deadline is None:
            deadline = timestamp
        if timestamp + 1e-9 >= deadline:
            selected.append(row["i"])
            deadline += (math.floor((timestamp - deadline + 1e-9) * SAMPLE_HZ) + 1) / SAMPLE_HZ
    return selected


def controller_events(recording: Path) -> list[tuple[float, Pad]]:
    path = recording / "pad.jsonl"
    if not path.exists():
        return []
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    rows = [row for row in rows if row.get("src") == "human"]
    if len(rows) <= 1:
        return []
    return sorted(
        (
            (
                float(row["t"]),
                Pad(
                    buttons=tuple(row.get("buttons", [])),
                    left=tuple(row.get("left", [0, 0])),
                    right=tuple(row.get("right", [0, 0])),
                    l2=row.get("l2", 0),
                    r2=row.get("r2", 0),
                ),
            )
            for row in rows
        ),
        key=lambda event: event[0],
    )


def active(pad: Pad) -> bool:
    return bool(pad.buttons or any(pad.left) or any(pad.right) or pad.l2 or pad.r2)


def human_share(start: float, end: float, events: list[tuple[float, Pad]]) -> float | None:
    if not events:
        return None
    times = [event[0] for event in events]
    index = bisect_right(times, start) - 1
    pad = events[index][1] if index >= 0 else Pad()
    cursor, held = start, 0.0
    for timestamp, next_pad in events[index + 1 :]:
        if timestamp >= end:
            break
        if active(pad):
            held += timestamp - cursor
        cursor, pad = timestamp, next_pad
    if active(pad):
        held += end - cursor
    return held / (end - start)


def sections(
    samples: list[Sample],
    rows: list[dict],
    events: list[tuple[float, Pad]],
    decision: Callable[[Sample], str] = decide,
) -> list[dict]:
    """A missing stretch of the recording clock is not observed play."""
    from .trimming import frame_runs

    output = []
    for first, stop in frame_runs(rows):
        chunk = rows[first:stop]
        start, end = chunk[0]["t"], chunk[-1]["t"]
        run_samples = [sample for sample in samples if start <= sample.time <= end]
        run_events = events if first == 0 else [(t, pad) for t, pad in events if start <= t <= end]
        output.extend(_sections(run_samples, chunk, run_events, decision))
    return output


def _sections(
    samples: list[Sample],
    rows: list[dict],
    events: list[tuple[float, Pad]],
    decision: Callable[[Sample], str] = decide,
) -> list[dict]:
    if not samples or not rows or rows[-1]["t"] - rows[0]["t"] < 1:
        return []
    start, end = rows[0]["t"], rows[-1]["t"]
    boundaries = [(start, "unknown")]
    candidate, since, previous_valid = None, start, -math.inf
    for sample in samples:
        if sample.reading.corrupt:
            continue
        kind = decision(sample)
        if kind not in KINDS:
            raise ValueError(f"Invalid section kind: {kind}")
        if kind == boundaries[-1][1]:
            candidate = None
        else:
            if kind != candidate or sample.time - previous_valid > 0.35:
                candidate, since = kind, sample.time
            if sample.time - since >= 1 - 1e-8:
                if since - boundaries[-1][0] < 1:
                    boundaries[-1] = (boundaries[-1][0], kind)
                else:
                    boundaries.append((since, kind))
                candidate = None
        previous_valid = sample.time
    if len(boundaries) > 1 and end - boundaries[-1][0] < 1:
        boundaries.pop()
    merged = []
    for boundary in boundaries:
        if not merged or boundary[1] != merged[-1][1]:
            merged.append(boundary)
    frame_times = [row["t"] for row in rows]
    sample_times = [sample.time for sample in samples]
    output = []
    for index, (start, kind) in enumerate(merged):
        stop = merged[index + 1][0] if index + 1 < len(merged) else end
        group = samples[
            bisect_left(sample_times, start) : bisect_left(sample_times, stop)
            if stop != end
            else len(samples)
        ]
        valid = [sample for sample in group if not sample.reading.corrupt]
        screens = {}
        for sample in valid:
            screens[sample.hud.screen] = screens.get(sample.hud.screen, 0) + 1
        wanted = [sample.hud.wanted for sample in valid if sample.hud.wanted is not None]
        routes = sorted({sample.reading.route for sample in valid} - {"none"})
        speeds = [
            sample.reading.gps_speed
            for sample in valid
            if sample.reading.gps_speed is not None and math.isfinite(sample.reading.gps_speed)
        ]
        output.append(
            {
                "start": start,
                "end": stop,
                "first_frame": rows[bisect_left(frame_times, start)]["i"],
                "last_frame": rows[(bisect_left(frame_times, stop) - 1) if stop != end else -1]["i"],
                "kind": kind,
                "screen": max(screens, key=screens.get) if screens else "game",
                "wanted": max(wanted) if wanted else None,
                "route": routes,
                "damaged": sum(sample.reading.corrupt for sample in group) / len(group) if group else 0,
                "human": human_share(start, stop, events),
                "route_share": sum(sample.reading.route != "none" for sample in valid) / len(valid)
                if kind == "drive" and valid
                else None,
                "speed": sum(speeds) / len(speeds) if kind == "drive" and speeds else None,
            }
        )
    return output


class JudgeDownError(Exception):
    """The judge's server did not answer; the second pass ends and the readers' result stands."""


class Judge:
    """The judge's answers about frames, cached in the output folder so that no frame is asked twice.

    An answer is None when the reply was not one the questions allow: such a frame counts as asked
    but decides nothing.
    """

    def __init__(self, server: str, transport: Callable[[str, str], dict] | None = None):
        self.url, self.model = endpoint(server)
        self.transport = transport or (
            lambda image, name: post(self.url, self.model, image, QUESTIONS[name][0], 2, timeout=10)[0]
        )
        self.cache: dict[str, dict | None] = {}
        self.seconds: list[float] = []
        self.odd = 0
        self.down: str | None = None

    def load(self, path: Path) -> None:
        self.cache = {}
        if path.exists():
            data = json.loads(path.read_text())
            if data.get("model") == self.model:
                self.cache = data["frames"]

    def save(self, path: Path) -> None:
        path.write_text(json.dumps({"model": self.model, "frames": self.cache}, separators=(",", ":")) + "\n")

    def ask(self, frame: int, image: Callable[[], str]) -> dict | None:
        key = str(frame)
        if key in self.cache:
            return self.cache[key]
        encoded, answer = image(), {}
        for name in SCORED:
            for attempt in range(2):
                started = time.perf_counter()
                try:
                    choice = self.transport(encoded, name)
                    break
                except (OSError, TimeoutError) as exc:
                    if attempt:
                        self.down = f"{type(exc).__name__}: {exc}"
                        raise JudgeDownError(self.down) from exc
                except ValueError:
                    choice = None
                    break
            self.seconds.append(time.perf_counter() - started)
            letter, top = (letters(choice) or [("", {})])[0] if choice else ("", {})
            meaning = QUESTIONS[name][1]
            if letter not in meaning:
                self.odd += 1
                self.cache[key] = None
                return None
            answer[name] = meaning[letter]
            if name == "mode":
                answer["p"] = probability(letter, top, meaning)
        self.cache[key] = answer
        return answer


def doubtful(samples: list[Sample], decision: Callable[[Sample], str] = decide) -> list[bool]:
    """The samples the judge is asked about: those the readers leave unknown, and a foot or vehicle
    that only the minimap names, near a change of the readers' mind or under stars."""
    kinds = [decision(replace(sample, judge=None)) for sample in samples]
    times = [sample.time for sample in samples]
    result = []
    for index, sample in enumerate(samples):
        if sample.reading.corrupt or kinds[index] in {"menu", "banner", "loading"}:
            result.append(False)
        elif kinds[index] == "unknown":
            result.append(True)
        elif pad_verdict(sample.pad, sample.reading.minimap) is not None:
            result.append(False)
        else:
            low = bisect_left(times, sample.time - DOUBT_SECONDS)
            high = bisect_right(times, sample.time + DOUBT_SECONDS)
            changed = any(
                kinds[other] != kinds[index]
                for other in range(low, high)
                if not samples[other].reading.corrupt
            )
            result.append(changed or (sample.hud.wanted or 0) > 0)
    return result


def judged_samples(
    samples: list[Sample], ask: Callable[[Sample], dict | None], decision: Callable[[Sample], str] = decide
) -> list[Sample]:
    """Ask `ask` about one frame in every second that holds a doubtful sample, and hand the answer
    to the doubtful samples of that second if a neighbouring second named the same kind: one odd
    answer decides nothing, as one odd reading does not."""
    chosen: dict[int, int] = {}
    for index, flag in enumerate(doubtful(samples, decision)):
        if flag:
            bucket = math.floor(samples[index].time)
            best = chosen.get(bucket)
            if best is None or abs(samples[index].time - bucket - 0.5) < abs(
                samples[best].time - bucket - 0.5
            ):
                chosen[bucket] = index
    asked = []
    for bucket in sorted(chosen):
        sample = samples[chosen[bucket]]
        answer = ask(sample)
        asked.append((bucket, sample.time, answer, judge_kind(answer)))
    accepted = {}
    for i, (bucket, moment, answer, kind) in enumerate(asked):
        near = [
            other
            for other in (asked[i - 1] if i else None, asked[i + 1] if i + 1 < len(asked) else None)
            if other is not None and abs(other[1] - moment) <= NEIGHBOUR_SECONDS
        ]
        if kind is not None and any(other[3] == kind for other in near):
            accepted[bucket] = answer
    flags = doubtful(samples, decision)
    return [
        replace(sample, judge=accepted.get(math.floor(sample.time)))
        if flag and math.floor(sample.time) in accepted
        else sample
        for sample, flag in zip(samples, flags, strict=True)
    ]


class FrameReader:
    """Decodes a recording forward to the frames asked for, in increasing order."""

    def __init__(self, recording: Path):
        self.cap = cv2.VideoCapture(str(recording / "video.mp4"))
        self.position = 0

    def at(self, index: int):
        while self.position < index:
            if not self.cap.grab():
                raise ValueError(f"Video ends before frame {index}")
            self.position += 1
        ok, bgr = self.cap.read()
        self.position += 1
        if not ok:
            raise ValueError(f"Cannot decode frame {index}")
        return bgr

    def close(self) -> None:
        self.cap.release()


def analyze(
    recording: Path,
    decision: Callable[[Sample], str] = decide,
    judge: Judge | None = None,
    folder: Path | None = None,
) -> dict | None:
    meta = json.loads((recording / "meta.json").read_text())
    if "seconds" not in meta:
        return None
    rows = frame_rows(recording)
    selected = set(sample_indices(rows))
    events = controller_events(recording)
    event_times = [event[0] for event in events]
    samples = []
    cap = cv2.VideoCapture(str(recording / "video.mp4"))
    try:
        for row in rows:
            if not cap.grab():
                raise ValueError(f"Video ends before frame {row['i']}")
            if row["i"] not in selected:
                continue
            ok, bgr = cap.retrieve()
            if not ok:
                raise ValueError(f"Cannot decode frame {row['i']}")
            event_index = bisect_right(event_times, row["t"]) - 1
            pad = (events[event_index][1] if event_index >= 0 else Pad()) if events else None
            rgb = cv2.cvtColor(cv2.resize(bgr, (1280, 720)), cv2.COLOR_BGR2RGB)
            samples.append(Sample(row["t"], row["i"], read_minimap(hud_crop(bgr)), read_hud(rgb), pad))
    finally:
        cap.release()
    if judge is not None and judge.down is None:
        samples = second_pass(recording, samples, decision, judge, folder)
    return {
        "recording": str(recording.resolve()),
        "seconds": meta["seconds"],
        "sample_hz": SAMPLE_HZ,
        "has_pad": bool(events),
        "sections": sections(samples, rows, events, decision),
    }


def second_pass(
    recording: Path,
    samples: list[Sample],
    decision: Callable[[Sample], str],
    judge: Judge,
    folder: Path | None,
) -> list[Sample]:
    """The samples with the judge's answers, or as they were if the server does not answer."""
    cache = folder / "judge.json" if folder is not None else None
    if cache is not None:
        judge.load(cache)
    frames = FrameReader(recording)
    try:
        return judged_samples(
            samples,
            lambda sample: judge.ask(sample.frame, lambda: encode(frames.at(sample.frame), JUDGE_WIDTH)),
            decision,
        )
    except JudgeDownError as exc:
        print(f"judge {judge.url} did not answer ({exc}); second pass stopped, readers only", flush=True)
        return samples
    finally:
        frames.close()
        if cache is not None:
            cache.parent.mkdir(parents=True, exist_ok=True)
            judge.save(cache)


def contact_sheet(recording: Path, result: dict, path: Path) -> None:
    rows = frame_rows(recording)
    times = [row["t"] for row in rows]
    targets = {}
    for index, section in enumerate(result["sections"]):
        target = bisect_left(times, (section["start"] + section["end"]) / 2)
        targets[target] = (index, section)
    width, height, columns = 320, 206, 4
    canvas = np.zeros(
        (max(1, math.ceil(len(targets) / columns)) * height, columns * width, 3), dtype=np.uint8
    )
    cap = cv2.VideoCapture(str(recording / "video.mp4"))
    try:
        for target, (index, section) in targets.items():
            cap.set(cv2.CAP_PROP_POS_FRAMES, target)
            ok, bgr = cap.read()
            if not ok:
                raise ValueError(f"Cannot decode contact frame {target}")
            x, y = index % columns * width, index // columns * height
            canvas[y : y + 180, x : x + width] = cv2.resize(bgr, (width, 180))
            label = f"{section['kind']} {section['start']:.1f}-{section['end']:.1f}s"
            cv2.putText(canvas, label, (x + 5, y + 198), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    finally:
        cap.release()
    if not cv2.imwrite(str(path), canvas):
        raise OSError(f"Cannot write {path}")
