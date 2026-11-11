"""A recorded tour for the readers: every screen the pilot can open, the camera's turn rate by the
arrow, and a tilt sweep. Inputs are timed, not read back, because the readers are what is being
tested. Stops with a neutral pad when a person takes the controller or a frame is late.
"""

import json
import sys
import time
from pathlib import Path

from pilot import hud as hud_reader
from pilot import minimap
from pilot.bridge import Bridge
from pilot.conductor import minimap_crop
from pilot.contract import Pad

TICK = 1 / 30
N = Pad()


def press(button, seconds=0.12):
    return (f"press {button}", Pad(buttons=(button,)), seconds)


STEPS = [("game", N, 1.0)]
STEPS += [press("options", 0.25), ("pause menu", N, 3.0), press("cross"), ("map", N, 3.0)]
STEPS += [press("circle"), ("pause menu again", N, 1.5), press("circle"), ("game", N, 2.5)]
STEPS += [("weapon wheel", Pad(buttons=("l1",)), 2.5), ("game", N, 1.5)]
STEPS += [press("up"), ("phone", N, 3.0), press("circle"), ("game", N, 2.0)]
STEPS += [("hold touchpad", Pad(buttons=("touchpad",)), 1.0), ("interaction menu", N, 3.0)]
STEPS += [press("circle"), ("game", N, 2.0)]
for index, stick in enumerate((0.3, 0.45, 0.65, 1.0)):
    sign = 1 if index % 2 == 0 else -1
    STEPS += [(f"turn {sign * stick:+.2f}", Pad(right=(sign * stick, 0.0)), 0.5), ("after turn", N, 1.5)]
for name, y, count in (("tilt down", 0.5, 6), ("tilt up", -0.5, 12), ("tilt down", 0.5, 6)):
    for _ in range(count):
        STEPS += [(name, Pad(right=(0.0, y)), 0.3), (f"after {name}", N, 1.0)]

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
rows, why = [], "finished"
with Bridge() as bridge:
    status = bridge.status()
    if not status["session_up"] or status["human_input"]:
        sys.exit(f"not started: session_up={status['session_up']} human_input={status['human_input']}")
    frame = bridge.frame()
    if hud_reader.read(frame.rgb).screen != "game" or minimap.read(minimap_crop(frame.rgb)).minimap == "none":
        sys.exit("not started: the picture is not the game with a minimap")
    folder = bridge.record_start(out, shadow=False)
    begun = time.monotonic()
    try:
        for step, (name, pad, seconds) in enumerate(STEPS):
            until = time.monotonic() + seconds
            while time.monotonic() < until:
                tick = time.monotonic()
                if bridge.pad(pad) == 409:
                    why = "person on the controller"
                    break
                frame = bridge.frame()
                if frame is None or frame.age > 0.5:
                    why = "late frame"
                    break
                hud = hud_reader.read(frame.rgb)
                reading = minimap.read(minimap_crop(frame.rgb))
                rows.append({"t": round(tick - begun, 3), "step": step, "name": name, "frame": frame.id,
                             "pad": pad.payload(), "screen": hud.screen, "minimap": reading.minimap,
                             "arrow": reading.arrow, "corrupt": reading.corrupt})
                time.sleep(max(0.0, TICK - (time.monotonic() - tick)))
            if why != "finished":
                break
    finally:
        bridge.pad(N)
        bridge.record_stop()
(Path(folder) / "tour.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
print(why, "| ticks", len(rows), "| recording", folder)
