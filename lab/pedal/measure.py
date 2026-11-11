"""Hold the accelerator at a few strengths and read from the minimap how fast the car moves.

    pilot/.venv/bin/python lab/pedal/measure.py 0.1 0.2 0.3 0.45 0.6

The figure has to sit in a car with open ground ahead and nobody on the controller. Each strength is
held for the given seconds with the wheel straight, then the brake until the map stands still. The
sticks and buttons are never touched. The session is recorded like any other, with a `pedal.jsonl`.
"""

import argparse
import json
import statistics
import time
from pathlib import Path

from pilot.bridge import Bridge
from pilot.contract import HUD_RECT, NEUTRAL_PAD, Pad
from pilot.loop import ControllerRuntime, cleanup_runtime, interrupt_handlers
from pilot.motion import map_motion

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("strengths", type=float, nargs="+")
parser.add_argument("--seconds", type=float, default=2.5)
parser.add_argument(
    "--record-dir", type=Path, default=Path("/Users/kerim/recordings/pilot")
)
args = parser.parse_args()
if any(not 0 < strength <= 1 for strength in args.strengths):
    parser.error("a strength is above 0 and at most 1")

TICK = 1 / 30
x, y, w, h = HUD_RECT
rows = []
with Bridge() as bridge:
    runtime = ControllerRuntime(bridge, raw=True)
    recording = False
    log = None
    with interrupt_handlers():
        try:
            destination = bridge.record_start(args.record_dir, shadow=False)
            recording = True
            log = (destination / "pedal.jsonl").open("x")
            started = runtime.last_fresh = time.monotonic()
            previous = None

            def hold(pad, seconds, label):
                global previous
                end = time.monotonic() + seconds
                moved = []
                while time.monotonic() < end:
                    tick = time.monotonic()
                    frame = bridge.frame(None, after=runtime.last_id)
                    received = time.monotonic()
                    fresh = runtime.observe(frame, received)
                    shift = None
                    if fresh:
                        crop = frame.rgb[y : y + h, x : x + w]
                        if previous is not None:
                            shift = map_motion(previous[1], crop)
                            if shift is not None:
                                shift /= max(1e-3, received - frame.age - previous[0])
                                moved.append((received - started, shift))
                        previous = (received - frame.age, crop.copy())
                    _, status = runtime.tick(pad, fresh=fresh, received=received)
                    if status not in (None, 200):
                        raise RuntimeError(f"controller returned {status}")
                    log.write(
                        json.dumps(
                            {
                                "t": received - started,
                                "label": label,
                                "pad": pad.payload(),
                                "speed": shift,
                            }
                        )
                        + "\n"
                    )
                    time.sleep(max(0.0, tick + TICK - time.monotonic()))
                return moved

            hold(NEUTRAL_PAD, 1.0, "rest")
            for strength in args.strengths:
                moved = hold(Pad(r2=strength), args.seconds, f"r2={strength}")
                late = [speed for t, speed in moved[len(moved) // 2 :]]
                rows.append(
                    {
                        "r2": strength,
                        "first_motion": next(
                            (
                                round(t - moved[0][0], 2)
                                for t, speed in moved
                                if speed > 3
                            ),
                            None,
                        ),
                        "speed_px_s_second_half": round(statistics.median(late), 1)
                        if late
                        else None,
                        "speed_px_s_end": round(
                            statistics.median([s for _, s in moved[-8:]]), 1
                        )
                        if moved
                        else None,
                    }
                )
                hold(Pad(l2=1.0), 0.7, "brake")
                hold(NEUTRAL_PAD, 1.5, "rest")
        finally:
            cleanup_runtime(runtime, recording=recording, pipeline=None, logs=(log,))
print(json.dumps(rows, indent=1))
