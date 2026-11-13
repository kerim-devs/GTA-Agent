"""Replay original first frames through the real map readers and walk skill."""

import json
import math
from pathlib import Path

import cv2

from measure import frame_at
from pilot.contract import Observation
from pilot.foot import hud_crop
from pilot.minimap import read
from pilot.walkto import WalkTo
from pilot.waymark import find_waypoint, near_place, way_by_road


def run():
    root = Path(__file__).resolve().parent
    reports = []
    for session, first in [
        ("20261113-022849", 0.055079),
        ("20261113-005541", 0.105382),
        ("20261113-010434", 0.051006),
    ]:
        skill = WalkTo({})
        commands = []
        frame = frame_at(session, first)
        crop = hud_crop(frame)
        marker = find_waypoint(crop)
        plan = None if marker is None else way_by_road(crop, marker.x, marker.y)
        cv2.imwrite(str(root / f"{session}.png"), cv2.cvtColor(crop, cv2.COLOR_RGB2BGR))
        for index in range(22):
            t = first + index * 0.1
            frame = frame_at(session, t)
            reading = read(hud_crop(frame))
            result = skill.step(Observation(reading, True, t, frame=frame, mode="foot"))
            commands.append(
                {
                    "t": t,
                    "left": result.pad.left,
                    "right": result.pad.right,
                    "status": result.status,
                    "reason": result.reason,
                }
            )
        moved = next((row for row in commands if math.hypot(*row["left"]) > 0.1), None)
        reports.append(
            {
                "session": session,
                "first": first,
                "symbol": near_place(crop),
                "original_plan": plan,
                "first_movement": moved,
                "commands": commands,
            }
        )
    (root / "starts.json").write_text(json.dumps(reports, indent=2) + "\n")
    print(
        json.dumps(
            [
                {k: v for k, v in report.items() if k != "commands"}
                for report in reports
            ],
            indent=2,
        )
    )


if __name__ == "__main__":
    run()
