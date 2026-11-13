"""The whole pilot over recorded play, without a console: does anything in it throw, stand or loop?

A recording of Kerim's play is put through the conductor as a live session would be: the readers on
every frame, the screen texts as they were derived from the recording, the flow reflex, the guard, the
standing watchdog and the head's rules, each answer applied at once. The world does not answer the
pilot's pad, so this proves nothing about how well it plays: a walk gets nowhere and a menu does not
open. What it does show is what only real pictures bring out: a reading nobody expected, a text the
reader garbled, a rule that throws, a plan that is refused, a head that is asked forty times a minute.

    tools/smoke.py <recording> [<recording> ...] [--derived DIR] [--out DIR] [--seconds S] [--guard]

The summary of each recording is printed as one JSON line, and the run fails if any of them threw.
"""

import argparse
import json
import sys
import tempfile
import traceback
from collections import Counter
from concurrent.futures import Future
from pathlib import Path

import cv2

from pilot import hud
from pilot.conductor import Conductor, minimap_crop
from pilot.flow import Flow
from pilot.guard import Guard
from pilot.localhead import ErrandChooser, LocalHead
from pilot.loop import Pipeline
from pilot.mission import MissionHead
from pilot.scene import SceneText
from pilot.skills import Observation

TICK = 1 / 30
TEXT_FIELDS = ("help", "objective", "subtitle", "banner", "phone_menu")


def immediate(function, *args):
    future = Future()
    try:
        future.set_result(function(*args))
    except Exception as exc:
        future.set_exception(exc)
    return future


class NoGPS:
    def poll(self, crop, timestamp):
        return None


def texts(path: Path):
    """The derived screen texts of a recording as (time, SceneText), oldest first."""
    rows = []
    if path.exists():
        with path.open() as lines:
            for line in lines:
                row = json.loads(line)
                text = row.get("text") or {}
                rows.append((float(row["t"]), SceneText(**{key: text.get(key, "") for key in TEXT_FIELDS})))
    return rows


def default_head():
    """The head of `pilot play --head local`, with no server named: the model is silent and the rules play."""
    return MissionHead(LocalHead(), goal_seed=7, chooser=ErrandChooser())


def run(recording: Path, derived: Path | None, out: Path, *, seconds=None, guard=True, head=default_head):
    summary = {"recording": recording.name, "ticks": 0, "seconds": 0.0, "error": None}
    capture = cv2.VideoCapture(str(recording / "video.mp4"))
    if not capture.isOpened():
        summary["error"] = "cannot decode the video"
        return summary
    read = texts(derived / recording.name / "readings.jsonl") if derived is not None else []
    summary["texts"] = len(read)
    out.mkdir(parents=True, exist_ok=True)
    brain = head()
    conductor = Conductor(
        out,
        head=brain,
        notebook=out / "notebook.txt",
        ocr=False,
        flow=Flow(calls=True),
        guard=Guard() if guard else None,
        standing=Conductor.STANDING_SECONDS,
        submit=immediate,
        quiet_seconds=60,
    )
    pipeline = Pipeline(gps_reader=NoGPS())
    skills, reasons, pads = Counter(), Counter(), Counter()
    first = last = None
    cursor = 0
    try:
        with (recording / "frames.jsonl").open() as metadata:
            for line in metadata:
                ok, bgr = capture.read()
                if not ok:
                    break
                t = float(json.loads(line)["t"])
                if last is not None and t - last < TICK * 0.9:
                    continue  # the recording has every frame; the pilot ticks thirty times a second
                first = t if first is None else first
                if seconds is not None and t - first > seconds:
                    break
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                reading, moving, _ = pipeline.step(minimap_crop(rgb), t, feedback=False)
                fresh, fresh_time = None, None
                while cursor < len(read) and read[cursor][0] <= t:
                    fresh_time, fresh = read[cursor]
                    cursor += 1
                seen = hud.read(rgb, text=conductor.text if fresh is None else fresh)
                result = conductor.tick(
                    Observation(reading, moving, t, hud=seen), rgb, text=fresh, text_time=fresh_time
                )
                name = (conductor.describe(result) or {}).get("name") or "none"
                skills[name] += 1
                if (
                    result.pad.buttons
                    or any(result.pad.left)
                    or any(result.pad.right)
                    or result.pad.l2
                    or result.pad.r2
                ):
                    pads[name] += 1
                if result.reason in ("flow", "guard", "carry-on", "pad-refused"):
                    reasons[result.reason] += 1
                last = t
                summary["ticks"] += 1
    except Exception:
        summary["error"] = traceback.format_exc(limit=12)
        summary["error_at"] = last
    finally:
        capture.release()
        conductor.close()
    rows = [json.loads(line) for line in (out / "head.jsonl").read_text().splitlines()]
    requests = [row for row in rows if row["type"] == "request"]
    answers = [row for row in rows if row["type"] == "response"]
    events = Counter(event.get("kind") for row in requests for event in row["request"]["events"])
    planned = Counter(call["name"] for row in answers for call in row.get("plan") or ())
    summary.update(
        {
            "seconds": 0.0 if first is None or last is None else round(last - first, 1),
            "requests": len(requests),
            "requests_a_minute": round(len(requests) * 60 / max(1.0, (last or 0) - (first or 0)), 1),
            "answers_failed": sum(1 for row in answers if row.get("error")),
            "answer_errors": sorted({row["error"] for row in answers if row.get("error")})[:8],
            "dispositions": dict(Counter(row.get("disposition") for row in answers)),
            "events": dict(events.most_common()),
            "planned": dict(planned.most_common()),
            "rules": dict(getattr(brain, "counts", Counter()).most_common()),
            "ticks_by_skill": dict(skills.most_common()),
            "ticks_with_a_pad": dict(pads.most_common()),
            "held_by": dict(reasons),
            "goals": [
                f"{item['name']} {item['outcome']}: {item['reason']}"
                for item in getattr(getattr(brain, "goals", None), "history", [])
            ][-40:],
        }
    )
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("recordings", nargs="+", type=Path)
    parser.add_argument("--derived", type=Path, default=Path("/Users/kerim/recordings/derived/kerim"))
    parser.add_argument("--out", type=Path, help="where each replay's logs go; a temporary folder otherwise")
    parser.add_argument("--seconds", type=float, help="only the first seconds of each recording")
    parser.add_argument("--no-guard", action="store_true")
    args = parser.parse_args(argv)
    failed = 0
    with tempfile.TemporaryDirectory(prefix="pilot-smoke-") as scratch:
        root = args.out or Path(scratch)
        for recording in args.recordings:
            summary = run(
                recording,
                args.derived if args.derived.exists() else None,
                root / recording.name,
                seconds=args.seconds,
                guard=not args.no_guard,
            )
            failed += summary["error"] is not None
            print(json.dumps(summary, ensure_ascii=False), flush=True)
    if failed:
        sys.exit(f"{failed} of {len(args.recordings)} recordings threw")


if __name__ == "__main__":
    main()
