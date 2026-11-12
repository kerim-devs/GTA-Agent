"""Replay recorded detections; commands do not change the recorded figure's position.

Run from the repository root: env -u PS5_HOST pilot/.venv/bin/python lab/enter/replay.py
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot/src"))

from pilot.contract import Detection, Observation, Reading
from pilot.vehicle_entry import EnterVehicle


class Frames:
    def __init__(self, session):
        import cv2

        self.cv2 = cv2
        folder = Path("/Users/kerim/recordings/pilot") / session
        self.rows = [
            json.loads(line)
            for line in (folder / "frames.jsonl").read_text().splitlines()
        ]
        play = [
            json.loads(line)
            for line in (folder / "play.jsonl").read_text().splitlines()
        ]
        by_frame = {row["frame_id"]: row for row in play if row.get("reading")}
        self.indices = {}
        row = None
        for index, frame in enumerate(self.rows):
            row = by_frame.get(frame["frame_id"], row)
            if index % 6 == 0 and row is not None:
                self.indices.setdefault(round(row["t"], 2), []).append(index)
        self.video = cv2.VideoCapture(str(folder / "video.mp4"))
        self.position = None

    def at(self, time):
        # dump.py samples every sixth video frame but carries forward the last play row's clock.
        candidates = [
            i
            for i in self.indices.get(time, ())
            if self.position is None or i >= self.position
        ]
        if not candidates:
            raise ValueError(f"no matching recorded frame at {time}")
        target = candidates[0]
        if (
            self.position is None
            or target < self.position
            or target - self.position > 30
        ):
            self.video.set(self.cv2.CAP_PROP_POS_FRAMES, target)
            self.position = target
        while self.position < target:
            if not self.video.grab():
                raise ValueError("recording ended before requested frame")
            self.position += 1
        ok, bgr = self.video.read()
        self.position += 1
        if not ok:
            raise ValueError("could not decode recorded frame")
        return self.cv2.cvtColor(bgr, self.cv2.COLOR_BGR2RGB)

    def close(self):
        self.video.release()


def replay(run, with_frames=False):
    samples = [s for s in run["samples"] if s["skill"][0] == "enter_vehicle"]
    frames = Frames(run["session"]) if with_frames else None
    skill = EnterVehicle({})
    first = None
    walking = corrupt_actions = 0
    unsafe_presses = 0
    positions = {}
    kinds = {}
    last = None
    for sample in samples:
        observation = Observation(
            Reading(sample["map"], "none", None, None, None, sample["corrupt"], 1.0),
            None,
            sample["t"],
            frame=frames.at(sample["t"]) if frames else None,
            objects=tuple(
                Detection(kind, tuple(box), confidence)
                for kind, box, confidence in sample["objects"]
            ),
            objects_time=sample["t"],
        )
        last = skill.step(observation)
        position = skill.location.position if skill.location else "unknown"
        positions[position] = positions.get(position, 0) + 1
        for vehicle in skill.vehicles:
            kinds[vehicle.occupancy] = kinds.get(vehicle.occupancy, 0) + 1
        if last.pad.buttons and skill.entry_target is not None:
            unsafe_presses += position == "lane" and (
                skill.entry_target.motion == "moving"
                or skill.entry_target.occupancy == "occupied"
            )
        walking += last.pad.left != (0, 0)
        corrupt_actions += sample["corrupt"] and (
            last.pad.left != (0, 0) or bool(last.pad.buttons)
        )
        if last.pad.buttons and first is None:
            first = {
                "time": sample["t"],
                "kind": skill.entry_target.obj.kind,
                "box": list(skill.entry_target.obj.box),
                "motion": skill.entry_target.motion,
                "occupancy": skill.taken_kind,
                "position": position,
            }
    old = [s["t"] for s in samples if "triangle" in s["buttons"]]
    if frames is not None:
        frames.close()
    return {
        "session": run["session"],
        "start": samples[0]["t"],
        "end": samples[-1]["t"],
        "original_first_press": old[0] if old else None,
        "changed_first_press": first,
        "walking_samples": walking,
        "actions_with_corrupt_map": corrupt_actions,
        "last_status": last.status,
        "last_reason": last.reason,
        "road_problem": skill.road_problem,
        "position_counts": positions,
        "vehicle_sample_kinds": kinds,
        "unsafe_lane_presses": unsafe_presses,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--frames",
        action="store_true",
        help="feed the matching original RGB frame to WalkRoad",
    )
    args = parser.parse_args()
    runs = []
    for name in ("runs.json", "runs-console.json"):
        runs.extend(json.loads(Path(__file__).with_name(name).read_text())["runs"])
    print(
        json.dumps(
            {
                "scope": "Choice and first-press timing only; no counterfactual entry success is proven.",
                "frames": args.frames,
                "runs": [replay(run, args.frames) for run in runs],
            },
            indent=2,
        )
    )
