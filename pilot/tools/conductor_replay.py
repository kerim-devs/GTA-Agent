"""Replay video and metadata through the conductor without constructing a Bridge."""

import argparse
import json
import math
from concurrent.futures import Future
from dataclasses import asdict
from itertools import pairwise
from pathlib import Path
from statistics import median

import cv2

from pilot import hud
from pilot.conductor import Conductor, background, minimap_crop
from pilot.contract import NEUTRAL_PAD
from pilot.flow import Flow
from pilot.head import parse_response
from pilot.loop import Pipeline
from pilot.scene import SceneText, TextReader
from pilot.skills import Observation


class NoGPS:
    def poll(self, crop, timestamp):
        return None


def immediate(function, *args):
    """Deterministic scripted-head completion at the next recording tick."""
    future = Future()
    try:
        future.set_result(function(*args))
    except Exception as exc:
        future.set_exception(exc)
    return future


class DelayedHead:
    """Complete a deterministic four-step answer after recording-clock latency."""

    def __init__(self, delay):
        if not math.isfinite(delay) or delay < 0:
            raise ValueError("head delay must be finite and nonnegative")
        self.delay = delay
        self.time = 0.0
        self.jobs = []

    def submit(self, function, *args):
        future = Future()
        self.jobs.append((self.time + self.delay, future))
        return future

    def advance(self, t):
        self.time = t
        for due, future in self.jobs:
            if due <= t and not future.done():
                future.set_result(
                    parse_response(
                        {
                            "plan": [
                                {"name": "walk", "args": {"y": -0.65, "duration": 10}},
                                {"name": "look", "args": {"angle": 30, "duration": 1}},
                                {"name": "walk", "args": {"y": -0.65, "duration": 10}},
                                {"name": "look", "args": {"angle": -30, "duration": 1}},
                            ],
                            "sentence": "Ich erkunde die Umgebung.",
                        }
                    )
                )
        self.jobs = [(due, future) for due, future in self.jobs if not future.done()]


def run_offline(
    recording: Path,
    out: Path,
    *,
    ocr=False,
    quiet_seconds=60,
    head_delay=None,
    hud_flow=False,
    text_reader=None,
):
    if ocr and head_delay is not None and not hud_flow:
        raise ValueError("delayed replay uses recorded time without wall-clock OCR")
    delayed = None if head_delay is None else DelayedHead(head_delay)
    judged = neutral = 0
    first_plan = False
    scene = SceneText()
    scene_time = None
    next_text = float("-inf")
    reader = (TextReader() if text_reader is None else text_reader) if hud_flow else None
    text_log = None
    video = recording / "video.mp4"
    with video.open("rb") as source:
        if source.read(80).startswith(b"version https://git-lfs.github.com/spec/"):
            raise ValueError(f"{video} is a Git LFS pointer; supply the original local recording")
    if out.resolve() == recording.resolve() or recording.resolve() in out.resolve().parents:
        raise ValueError("offline output must be outside the source recording")
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        capture.release()
        raise ValueError(f"cannot decode {video}")
    pipeline = Pipeline(gps_reader=None if ocr and not hud_flow else NoGPS())
    conductor = None
    log = None
    count = 0
    first = last = None
    try:
        conductor = Conductor(
            out,
            notebook=out / "notebook.txt",
            quiet_seconds=quiet_seconds,
            ocr=ocr and not hud_flow,
            flow=Flow() if hud_flow else None,
            submit=delayed.submit if delayed else immediate if not ocr or hud_flow else background,
            **({"clock": lambda: delayed.time} if delayed else {}),
        )
        log = (out / "play.jsonl").open("x")
        if hud_flow:
            text_log = (out / "text.jsonl").open("x")
        with (recording / "frames.jsonl").open() as metadata:
            for line in metadata:
                item = json.loads(line)
                t = float(item["t"])
                if item["i"] != count or not math.isfinite(t) or (last is not None and t <= last):
                    raise ValueError("non-contiguous frame indices or non-increasing timestamps")
                ok, bgr = capture.read()
                if not ok:
                    raise ValueError(f"video ended before metadata frame {count}")
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                reading, _moving, _ = pipeline.step(minimap_crop(rgb), t, feedback=False)
                if delayed:
                    delayed.advance(t)
                fresh_text = None
                if reader is not None and t >= next_text:
                    scene = fresh_text = reader.read(rgb)
                    scene_time = t
                    next_text = t + 0.5
                    text_log.write(json.dumps({"t": t, "text": asdict(scene)}) + "\n")
                    text_log.flush()
                reading_hud = hud.read(rgb, text=scene) if hud_flow else None
                result = conductor.tick(
                    Observation(reading, None, t, hud=reading_hud), rgb, text=fresh_text, text_time=scene_time
                )

                first_plan = first_plan or conductor.runner.has_plan
                if first_plan:
                    judged += 1
                    neutral += result.pad == NEUTRAL_PAD
                first = t if first is None else first

                log.write(
                    json.dumps(
                        {
                            "t": t - first,
                            "frame_id": item["frame_id"],
                            "fresh": True,
                            "reading": asdict(reading),
                            "capture_t": t,
                            "hud": None if reading_hud is None else asdict(reading_hud),
                            "text_time": scene_time,
                            "skill": conductor.describe(result),
                            "result": asdict(result),
                            "sent": False,
                            "status": None,
                        }
                    )
                    + "\n"
                )
                last = t
                count += 1
        if capture.read()[0]:
            raise ValueError("video has frames beyond metadata")
        if count == 0:
            raise ValueError("empty recording")
        elapsed = last - first
        times = conductor.request_times
        intervals = [b - a for a, b in pairwise(times)]
        rate = len(times) * 60 / elapsed if elapsed else 0
        responses = [
            json.loads(line)
            for line in (out / "head.jsonl").read_text().splitlines()
            if json.loads(line).get("type") == "response"
        ]
        report = {
            "head_delay": head_delay,
            "neutral_ticks_after_first_plan": neutral,
            "ticks_after_first_plan": judged,
            "neutral_share_after_first_plan": neutral / judged if judged else None,
            "answers": {
                kind: sum(row.get("disposition") == kind for row in responses)
                for kind in ("appended", "replaced", "discarded")
            },
            "recording": str(recording.resolve()),
            "frames": count,
            "elapsed": elapsed,
            "ocr": ocr or hud_flow,
            "hud_flow": hud_flow,
            "requests": len(times),
            "request_times": times,
            "intervals": intervals,
            "requests_per_minute": rate,
            "min_interval": min(intervals) if intervals else None,
            "median_interval": median(intervals) if intervals else None,
            "intervals_under_10s": sum(interval < 10 for interval in intervals),
            "too_frequent": rate > 6 or any(interval < 10 for interval in intervals),
        }
        if hud_flow:
            flow_rows = [
                json.loads(line)
                for line in (out / "head.jsonl").read_text().splitlines()
                if json.loads(line)["type"].startswith("flow_")
            ]
            (out / "flow.json").write_text(json.dumps(flow_rows, indent=2) + "\n")
            report["takeovers"] = sum(row["type"] == "flow_enter" for row in flow_rows)
        (out / "frequency.json").write_text(json.dumps(report, indent=2) + "\n")
        return report
    finally:
        capture.release()
        pipeline.close()
        if conductor is not None:
            conductor.close()
        if log is not None:
            log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--ocr", action="store_true", help="enable asynchronous scene and GPS OCR")
    parser.add_argument(
        "--hud-flow", action="store_true", help="replay HUD and flow with capture-clock scene OCR"
    )
    parser.add_argument("--quiet-seconds", type=float, default=60)
    parser.add_argument("--head-delay", type=float, help="scripted answer latency in recording seconds")
    args = parser.parse_args()
    print(
        json.dumps(
            run_offline(
                args.recording,
                args.out,
                ocr=args.ocr,
                quiet_seconds=args.quiet_seconds,
                head_delay=args.head_delay,
                hud_flow=args.hud_flow,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
