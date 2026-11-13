"""Offline P79 replay using decoded frames, HUD and minimap observations.

The first gameplay frame has no objective (the saved P75 visual annotation).
That annotation replaces only asynchronous OCR, whose clock cannot follow an
accelerated recording. No controller or bridge is constructed.
"""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import cv2

from pilot.contract import Observation
from pilot.hud import read as read_hud
from pilot.minimap import read as read_minimap
from pilot.replay import hud_crop
from pilot.switch import DIRECTIONS, SwitchCharacter

ROOT = Path(__file__).resolve().parents[2]


class NoObjective:
    def submit(self, frame, now):
        self.now = now

    def read(self):
        return self.now, None

    def close(self):
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--recording", type=Path, default=Path("/Users/kerim/recordings/kerim/20261111-190825")
    )
    parser.add_argument("--output", type=Path, default=ROOT / "lab/story/p79-replay.json")
    args = parser.parse_args()
    metadata = {
        row["i"]: row
        for line in (args.recording / "frames.jsonl").read_text().splitlines()
        if 24284 <= (row := json.loads(line))["i"] <= 25850
    }
    skill = SwitchCharacter({"to": "michael"})
    skill.text.close()
    skill.text = NoObjective()
    video = cv2.VideoCapture(str(args.recording / "video.mp4"))
    video.set(cv2.CAP_PROP_POS_FRAMES, min(metadata))
    transitions = []
    last_phase = None
    previous_down = False
    release_time = None
    previous_pad = None
    pad_changes = []
    returning_observations = Counter()
    try:
        for index in range(min(metadata), max(metadata) + 1):
            ok, bgr = video.read()
            if not ok:
                raise RuntimeError(f"Missing frame {index}")
            row = metadata[index]
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            now = row["t"]
            observation = Observation(read_minimap(hud_crop(bgr)), False, now, rgb, hud=read_hud(rgb))
            result = skill.step(observation)
            if skill.phase == "returning":
                returning_observations[skill._refusal(observation) or "readable-game"] += 1
            pad = result.pad
            assert pad.right[1] <= 0
            down = "down" in pad.buttons
            if previous_down and not down:
                release_time = now
                assert pad.right in DIRECTIONS.values()
            if release_time is not None and now - release_time < 0.25:
                assert pad.right in DIRECTIONS.values()
            if pad != previous_pad:
                pad_changes.append({"i": index, "t": now, "buttons": pad.buttons, "right": pad.right})
            if skill.phase != last_phase or result.status != "running":
                transitions.append(
                    {
                        "i": index,
                        "frame_id": row.get("frame_id"),
                        "t": now,
                        "phase": skill.phase,
                        "status": result.status,
                        "reason": result.reason,
                        "minimap": observation.reading.minimap,
                        "screen": observation.hud.screen,
                        "rgb_sha256": hashlib.sha256(rgb.tobytes()).hexdigest(),
                    }
                )
            previous_pad, previous_down, last_phase = pad, down, skill.phase
            if result.status != "running":
                break
    finally:
        skill.text.close()
        video.release()
    report = {
        "recording": args.recording.name,
        "objective": "absent, visual annotation",
        "transitions": transitions,
        "pad_changes": pad_changes,
        "returning_observations": dict(returning_observations),
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if result.status != "done" or result.reason != "switched: michael; was: franklin":
        raise SystemExit("Replay did not agree with the recorded character change")


if __name__ == "__main__":
    main()
