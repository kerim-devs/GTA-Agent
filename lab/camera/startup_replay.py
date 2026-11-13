"""Measure the P86 startup check and replay recorded head requests, entirely offline.

Run from the repository root: pilot/.venv/bin/python lab/camera/startup_replay.py
Labels were assigned visually before checking the classifier. Detector boxes and
OCR are frozen from local YOLOX/Vision runs; no server or console is contacted.
"""

import json
import sys
from collections import Counter
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot/src"))

from pilot.camera import read_tilt, startup_plan
from pilot.contract import Detection, Hud, Observation, Reading
from pilot.head import HeadRequest
from pilot.mission import MissionHead

FIXTURES = ROOT / "pilot/tests/fixtures/startup-story"


def camera_observation(row, root=FIXTURES):
    frame = cv2.cvtColor(cv2.imread(str(root / row["file"])), cv2.COLOR_BGR2RGB)
    player = row["player"]
    figure = Detection("person", tuple(player["box"]), player["confidence"]) if player else None
    objects = tuple(
        Detection(item["kind"], tuple(item["box"]), item["confidence"])
        for item in row["objects"]
        if not player or item["box"] != player["box"]
    )
    return Observation(
        Reading("flat", "none", None, None, None, False, 1), False, row["t"],
        frame=frame, figure=figure, objects=objects, objects_time=row["t"],
        mode="foot", hud=Hud(),
    )


def camera_measurement():
    rows = json.loads((FIXTURES / "camera.json").read_text())
    confusion = Counter()
    results = []
    for row in rows:
        observation = camera_observation(row)
        got = read_tilt(observation)
        confusion[f"{row['label']}->{got}"] += 1
        results.append({
            "session": row["session"], "frame_id": row["frame_id"],
            "label": row["label"], "read": got,
            "plan": [call.name for call in startup_plan(observation)],
        })
    correct = sum(r["label"] == r["read"] for r in results)
    return {"correct": correct, "total": len(rows), "accuracy": correct / len(rows),
            "confusion": dict(confusion), "frames": results}


def head_replay():
    # The recording's initial story choice is given. Historical persistent memory
    # and chooser state cannot be reconstructed from the random seed alone.
    first_choice = True

    def recorded_start(offers):
        nonlocal first_choice
        if first_choice:
            first_choice = False
            return "story"
        return None

    head = MissionHead(goal_seed=241505890, chooser=recorded_start)
    results = []
    for row in json.loads((FIXTURES / "head-first45.json").read_text()):
        request = HeadRequest(**row["request"])
        answer = head.decide(request)
        results.append({
            "id": row["id"], "t": row["t"], "last": request.last_skill,
            "goal": answer.goal, "step": answer.step,
            "plan": [{"name": call.name, "args": call.args} for call in answer.plan],
        })
    return results


if __name__ == "__main__":
    print(json.dumps({"camera": camera_measurement(), "head": head_replay()}, indent=2))
