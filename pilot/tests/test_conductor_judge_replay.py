"""Offline conductor replays using recorded readings and timed judge replies."""

import json
from concurrent.futures import Future
from pathlib import Path

import numpy as np
import pytest

from pilot.conductor import Conductor
from pilot.contract import Answer, Judgment, Observation, Reading
from pilot.head import HeadResponse, SkillCall
from pilot.scene import EventDetector

RECORDINGS = Path.home() / "recordings" / "pilot"
RGB = np.zeros((720, 1280, 3), dtype=np.uint8)


class ReplayJudge:
    def __init__(self, rows, origin):
        self.rows = iter(rows)
        self.next = next(self.rows, None)
        self.origin = origin
        self.delivered = 0

    def poll(self, rgb, capture):
        if self.next is None or self.next["t"] - self.origin > capture:
            return None
        row = self.next
        self.next = next(self.rows, None)
        self.delivered += 1
        return Judgment(
            row["capture"] - self.origin,
            {key: Answer(**value) for key, value in row["answers"].items()},
            row["probabilities"],
            row["duration"],
            row["server"],
        )

    def drain_failures(self):
        return []

    def close(self):
        pass


class FootJudge:
    def poll(self, rgb, capture):
        return Judgment(capture, {"mode": Answer("foot", 1.0)}, {}, 0, "offline-foot")

    def drain_failures(self):
        return []

    def close(self):
        pass


class CountingDetector(EventDetector):
    def __init__(self):
        super().__init__()
        self.counts = {"vehicle_enter": 0, "vehicle_exit": 0}

    def update(self, *args, **kwargs):
        events = super().update(*args, **kwargs)
        for event in events:
            if event.kind in self.counts:
                self.counts[event.kind] += 1
        return events


@pytest.mark.parametrize("session", ["20261111-115541", "20261111-115803"])
@pytest.mark.parametrize("with_judge", [False, True])
def test_recorded_conductor_vehicle_events(session, with_judge, tmp_path):
    directory = RECORDINGS / session
    if not (directory / "play.jsonl").exists():
        pytest.skip("local P33 console recording is not available")
    rows = [json.loads(line) for line in (directory / "play.jsonl").read_text().splitlines()]
    heads = [json.loads(line) for line in (directory / "head.jsonl").read_text().splitlines()]
    recorded = {"vehicle_enter": 0, "vehicle_exit": 0}
    for head in heads:
        if head["type"] == "request":
            for event in head["request"]["events"]:
                if event["kind"] in recorded:
                    recorded[event["kind"]] += 1
    judge = None
    judge_rows = []
    if with_judge:
        if session == "20261111-115541":
            judge = FootJudge()
        else:
            judge_rows = [json.loads(line) for line in (directory / "judge.jsonl").read_text().splitlines()]
            # First recorded head request minus the first session-relative play tick.
            first_request = next(head for head in heads if head["type"] == "request")
            judge = ReplayJudge(judge_rows, first_request["t"] - rows[0]["t"])

    def submit(function, request):
        future = Future()
        future.set_result(HeadResponse((SkillCall("wait", {"duration": 60}),), "Wait."))
        return future

    detector = CountingDetector()
    conductor = Conductor(tmp_path, judge=judge, detector=detector, submit=submit)
    try:
        for row in rows:
            conductor.tick(Observation(Reading(**row["reading"]), None, row["t"]), RGB)
    finally:
        conductor.close()
    if judge_rows:
        assert judge.delivered == len(judge_rows)
    print(
        f"{session} judge={with_judge}: ticks={len(rows)} "
        f"vehicle_enter={detector.counts['vehicle_enter']} vehicle_exit={detector.counts['vehicle_exit']}"
    )
    assert recorded == {"vehicle_enter": 1, "vehicle_exit": 0}
    assert detector.counts == ({"vehicle_enter": 0, "vehicle_exit": 0} if with_judge else recorded)
