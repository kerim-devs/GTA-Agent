"""What does the game's own camera do on foot? Tilt it, turn it, stand, walk, and record.

Sends only the two sticks. Stops at once, with a neutral pad, when a person takes the controller,
when the picture is not the game on foot, or when a frame is late.
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
NEUTRAL = Pad()
FORWARD = Pad(left=(0.0, -0.6))
PHASES = [
    ("still", NEUTRAL, 1.0),
    ("tilt+", Pad(right=(0.0, 0.7)), 0.5),
    ("stand after tilt+", NEUTRAL, 2.5),
    ("walk after tilt+", FORWARD, 2.0),
    ("still", NEUTRAL, 1.0),
    ("tilt-", Pad(right=(0.0, -0.7)), 0.5),
    ("stand after tilt-", NEUTRAL, 2.5),
    ("walk after tilt-", FORWARD, 2.0),
    ("still", NEUTRAL, 1.0),
    ("turn", Pad(right=(0.7, 0.0)), 0.6),
    ("stand after turn", NEUTRAL, 2.5),
    ("walk after turn", FORWARD, 2.0),
    ("still", NEUTRAL, 1.5),
]

out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
rows, why = [], "finished"
with Bridge() as bridge:
    status = bridge.status()
    if not status["session_up"] or status["human_input"]:
        sys.exit(f"not started: session_up={status['session_up']} human_input={status['human_input']}")
    frame = bridge.frame()
    hud = hud_reader.read(frame.rgb)
    reading = minimap.read(minimap_crop(frame.rgb))
    if hud.screen != "game" or reading.minimap != "flat":
        sys.exit(f"not started: screen={hud.screen} minimap={reading.minimap}")
    folder = bridge.record_start(out, shadow=False)
    begun = time.monotonic()
    try:
        for name, pad, seconds in PHASES:
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
                if hud.screen != "game" or (reading.minimap != "flat" and not reading.corrupt):
                    why = f"screen={hud.screen} minimap={reading.minimap}"
                    break
                rows.append({"t": round(tick - begun, 3), "phase": name, "frame": frame.id,
                             "arrow": reading.arrow, "corrupt": reading.corrupt})
                time.sleep(max(0.0, TICK - (time.monotonic() - tick)))
            if why != "finished":
                break
    finally:
        bridge.pad(NEUTRAL)
        bridge.record_stop()
(Path(folder) / "probe.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
print(why, "| ticks", len(rows), "| recording", folder)
