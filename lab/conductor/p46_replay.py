"""Replay recorded lower-loop outcomes and head timing through the real conductor.

This isolates plan lifecycle from perception. It never opens a Bridge or a video.
After a new skill departs from the recorded trajectory its real implementation
receives only the logged minimap reading, so that tail is not console evidence.
"""

import argparse
import json
from concurrent.futures import Future
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import numpy as np

from pilot.conductor import Conductor
from pilot.contract import Blip, Pad, Reading, SkillResult
from pilot.head import SkillCall, parse_response
from pilot.skills import Observation, Skill, make_skill


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def signature(request):
    def skill(value):
        value = value or {}
        return (
            value.get("name"),
            value.get("status"),
            value.get("reason") if value.get("status") == "failed" else None,
        )

    return (
        tuple((event["kind"], skill(event.get("skill"))) for event in request["events"]),
        skill(request.get("last_skill")),
    )


class NoEvents:
    def update(self, *args, **kwargs):
        return ()


class Tape:
    def __init__(self, requests, responses, offset, original):
        self.requests = requests
        self.responses = responses
        self.offset = offset
        self.original = original
        self.time = 0
        self.row = None
        self.jobs = []
        self.matched = []
        self.unmatched = []
        self.counterfactual = 0
        self.completion_clock = None

    def clock(self):
        if self.completion_clock is not None:
            value, self.completion_clock = self.completion_clock, None
            return value
        return self.time

    def submit(self, function, request):
        future = Future()
        actual = asdict(request)
        candidates = [
            row
            for row in self.requests
            if abs(row["t"] - self.offset - self.time) < 1e-6
            and signature(row["request"]) == signature(actual)
        ]
        if candidates:
            source = candidates[0]
            response = self.responses.get(source["id"])
            self.matched.append(source["id"])
            if response is not None:
                self.jobs.append((response["t"] - self.offset, future, response, self.time))
        else:
            self.unmatched.append(
                {"t": self.time, "events": actual["events"], "last_skill": actual["last_skill"]}
            )
        return future

    def advance(self, row):
        self.time, self.row = row["t"], row
        for due, future, response, started in self.jobs:
            if due <= self.time + 1e-7 and not future.done():
                self.completion_clock = started + response["duration"]
                future.set_result(
                    parse_response({key: response[key] for key in ("plan", "sentence", "lesson")})
                )

    def factory(self, call, **kwargs):
        return RecordedSkill(make_skill(call, **kwargs), self)


class RecordedSkill:
    def __init__(self, skill, tape):
        self.skill, self.tape = skill, tape
        self.started = None

    def __getattr__(self, name):
        return getattr(self.skill, name)

    def step(self, observation):
        if self.started is None:
            self.started = observation.time
            self.skill.started = observation.time
        # Exercise the production timeout result, rather than rewriting the tape.
        if isinstance(self.skill, Skill) and observation.time - self.started >= self.skill.limit:
            result = self.skill.step(observation)
            if self.tape.original and self.name in ("walk_to", "face"):
                return SkillResult(status="failed", reason="time-limit")
            return result
        source = self.tape.row
        if (source.get("skill") or {}).get("name") == self.name:
            result = source["result"]
            pad = dict(result["pad"])
            for key in ("left", "right", "buttons"):
                if key in pad:
                    pad[key] = tuple(pad[key])
            return SkillResult(Pad(**pad), result["status"], result.get("reason"))
        self.tape.counterfactual += 1
        return self.skill.step(observation)


def plan(conductor):
    runner = conductor.runner
    return {
        "active": None if runner.active is None else runner.active.name,
        "queue": [skill.name for skill in runner.queue],
    }


def replay(recording, out, *, original=False):
    play = rows(recording / "play.jsonl")
    head = rows(recording / "head.jsonl")
    requests = [row for row in head if row["type"] == "request"]
    responses = {row["id"]: row for row in head if row["type"] == "response"}
    offset = requests[0]["t"] - play[0]["t"]
    tape = Tape(requests, responses, offset, original)
    rgb = np.zeros((720, 1280, 3), dtype=np.uint8)
    states = []
    first_skill = next((row["skill"] for row in play if row.get("skill")), {})
    opening = (
        (SkillCall("level_camera", {"duration": 8}),) if first_skill.get("name") == "level_camera" else ()
    )
    with patch("pilot.skills.make_skill", tape.factory):
        conductor = Conductor(
            out,
            submit=tape.submit,
            detector=NoEvents(),
            ocr=False,
            clock=tape.clock,
            notebook=out / "notebook.txt",
            opening=opening,
        )
    try:
        with patch("pilot.skills.make_skill", tape.factory), (out / "play.jsonl").open("x") as log:
            for source in play:
                tape.advance(source)
                if source["reading"] is None:
                    state = {
                        "t": source["t"],
                        "frame_id": source["frame_id"],
                        "skill": conductor.describe(),
                        "result": None,
                        "plan": plan(conductor),
                    }
                    log.write(json.dumps(state, separators=(",", ":")) + "\n")
                    states.append(state)
                    continue
                data = dict(source["reading"])
                data["blips"] = tuple(Blip(**item) for item in data.get("blips", ()))
                observation = Observation(Reading(**data), None, source["t"])
                external = []
                for request in requests:
                    if abs(request["t"] - offset - source["t"]) < 1e-6:
                        external.extend(
                            event
                            for event in request["request"]["events"]
                            if event["kind"] not in ("startup", "skill_failed", "skill_ended", "plan_ending")
                        )
                result = conductor.tick(observation, rgb, events=external)
                state = {
                    "t": source["t"],
                    "frame_id": source["frame_id"],
                    "skill": conductor.describe(result),
                    "result": asdict(result),
                    "plan": plan(conductor),
                }
                log.write(json.dumps(state, separators=(",", ":")) + "\n")
                states.append(state)
    finally:
        conductor.close()
    summary = {
        "recording": str(recording),
        "ticks": len(play),
        "offset": offset,
        "matched_requests": tape.matched,
        "unmatched_source_requests": [row["id"] for row in requests if row["id"] not in tape.matched],
        "unmatched_replay_requests": tape.unmatched,
        "ticks_without_recorded_skill_outcome": tape.counterfactual,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return states, summary, play


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    source = args.recording.resolve()
    out = args.out.resolve()
    recordings = Path("/Users/kerim/recordings").resolve()
    if out == source or source in out.parents or out == recordings or recordings in out.parents:
        parser.error("output must be outside the recordings directory")
    before, baseline, recorded = replay(source, out / "original", original=True)
    after, changed, _ = replay(source, out / "changed")
    differences = []
    baseline_mismatches = []
    for old, new, actual in zip(before, after, recorded, strict=True):
        old_skill, new_skill, actual_skill = old["skill"] or {}, new["skill"] or {}, actual["skill"] or {}
        keys = ("name", "status")
        if tuple(old_skill.get(key) for key in keys) != tuple(actual_skill.get(key) for key in keys):
            baseline_mismatches.append({"t": actual["t"], "recorded": actual_skill, "replayed": old_skill})
        if old["plan"] != new["plan"] or tuple(old_skill.get(key) for key in keys) != tuple(
            new_skill.get(key) for key in keys
        ):
            reason = (
                "plain time limit completes"
                if (new["result"] or {}).get("reason") == "time-limit"
                else "continuation survives predecessor timeout; subsequent observations remain recorded"
            )
            differences.append(
                {
                    "t": new["t"],
                    "frame_id": new["frame_id"],
                    "recorded": actual_skill,
                    "before": old["plan"],
                    "after": new["plan"],
                    "reason": reason,
                }
            )
    (out / "differences.jsonl").write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in differences)
    )
    (out / "baseline-mismatches.jsonl").write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in baseline_mismatches)
    )
    report = {
        "baseline": baseline,
        "changed": changed,
        "changed_ticks": len(differences),
        "baseline_mismatches": len(baseline_mismatches),
    }
    (out / "comparison.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if baseline_mismatches or baseline["unmatched_replay_requests"] or baseline["unmatched_source_requests"]:
        raise SystemExit("baseline does not reproduce the recorded lifecycle")


if __name__ == "__main__":
    main()
