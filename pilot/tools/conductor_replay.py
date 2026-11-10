"""Replay video and metadata through the conductor without constructing a Bridge."""

import argparse
import json
import math
from concurrent.futures import Future
from itertools import pairwise
from pathlib import Path
from statistics import median

import cv2

from pilot.conductor import Conductor, background, minimap_crop
from pilot.loop import Pipeline
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


def run_offline(recording: Path, out: Path, *, ocr=False, quiet_seconds=60):
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
    pipeline = Pipeline(gps_reader=None if ocr else NoGPS())
    conductor = None
    log = None
    count = 0
    first = last = None
    try:
        conductor = Conductor(
            out,
            notebook=out / "notebook.txt",
            quiet_seconds=quiet_seconds,
            ocr=ocr,
            submit=immediate if not ocr else background,
        )
        log = (out / "play.jsonl").open("x")
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
                result = conductor.tick(Observation(reading, None, t), rgb)
                first = t if first is None else first
                from dataclasses import asdict

                log.write(
                    json.dumps(
                        {
                            "t": t - first,
                            "frame_id": item["frame_id"],
                            "fresh": True,
                            "reading": asdict(reading),
                            "skill": conductor.runner.describe(),
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
        report = {
            "recording": str(recording.resolve()),
            "frames": count,
            "elapsed": elapsed,
            "ocr": ocr,
            "requests": len(times),
            "request_times": times,
            "intervals": intervals,
            "requests_per_minute": rate,
            "min_interval": min(intervals) if intervals else None,
            "median_interval": median(intervals) if intervals else None,
            "intervals_under_10s": sum(interval < 10 for interval in intervals),
            "too_frequent": rate > 6 or any(interval < 10 for interval in intervals),
        }
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
    parser.add_argument("--quiet-seconds", type=float, default=60)
    args = parser.parse_args()
    print(
        json.dumps(
            run_offline(args.recording, args.out, ocr=args.ocr, quiet_seconds=args.quiet_seconds), indent=2
        )
    )


if __name__ == "__main__":
    main()
