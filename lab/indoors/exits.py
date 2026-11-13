"""Scripted exits seeded with the three recordings' initial arrow readings.

Only the initial arrow comes from video. Room geometry, movement and the place/door
sensor are synthetic; replay cannot show the camera turning in response to new input.
"""

import json
import math
import sys
from pathlib import Path

from measure import frame_at

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pilot/tests"))
from pytest import MonkeyPatch
from test_buildings import Room, play, sensor

from pilot import ahead, indoors
from pilot.ahead import View
from pilot.foot import hud_crop
from pilot.leave import LeaveBuilding
from pilot.minimap import read
from pilot.wayround import WayRound


def run():
    outputs = []
    for session in ("20261113-024118", "20261113-025032", "20261113-025632"):
        reading = read(hud_crop(frame_at(session, 1)))
        for method in ("remembered", "model", "wall"):
            room = Room(inside=True)
            room.camera = -(reading.arrow or 0)

            class Door:
                def ask(self, frame, capture, **kwargs):
                    return True

                def answer(self, since):
                    angle = (
                        math.degrees(math.atan2(4 - room.x, -room.y))
                        - room.camera
                        + 180
                    ) % 360 - 180
                    part = -1 if angle < -20 else 1 if angle > 20 else 0
                    parts = tuple(float(i == part) for i in (-1, 0, 1))
                    return View(
                        indoors=float(room.inside),
                        exit=float(abs(angle) < 65),
                        parts=parts,
                    )

            with MonkeyPatch.context() as patch:
                patch.setattr(
                    ahead,
                    "active",
                    (lambda: Door()) if method == "model" else lambda: None,
                )
                patch.setattr(ahead, "place", lambda: None)
                sensor(patch, room)
                indoors.forget()
                if method == "remembered":
                    # Synthetic remembered approach: world north, expressed in this initial picture.
                    indoors.remember(-room.camera, (0, -1))
                skill = LeaveBuilding({})
                result = play(skill, room, 60)
                outputs.append(
                    {
                        "session": session,
                        "initial_arrow": reading.arrow,
                        "method": method,
                        "seconds": result[-1][0],
                        "status": result[-1][1].status,
                        "reason": result[-1][1].reason,
                        "trace": skill.guard.views,
                        "neutral_end": result[-1][1].pad.left == (0, 0)
                        and result[-1][1].pad.right == (0, 0),
                    }
                )
                indoors.forget()
    report = {
        "evidence": "Synthetic room seeded only with recorded initial arrow; no live replay outcome.",
        "constants": {
            key: getattr(WayRound, key)
            for key in (
                "ABOUT",
                "TURN_RATE",
                "LOOK_TURN",
                "LOOK_STEP",
                "LOOK_SETTLE",
                "LOOK_WAIT",
                "LOOKS",
                "EXIT_RUN",
                "CLEAR",
                "WALL_STEP",
                "WALL_TURNS",
                "LEG_START",
                "LEG_HELD_AFTER",
            )
        },
        "runs": outputs,
    }
    (Path(__file__).parent / "exits.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    run()
