"""Writes lab/models/scene.json: frames labelled with where the figure stands, a room, a landing or the street.

    pilot/.venv/bin/python lab/models/scene_build.py

room     the 61 barber frames of lab/indoors/heldout.json and the apartment of session 20261113-121513,
         one frame every 20 s in which the game's own picture was up (the pause map shows no minimap)
landing  22.5 to 30.0 s of that session, four frames a second: the figure had opened the apartment's door
         and stood on the landing above the street, with the stairs down in front of it, and then walked
         back in. This is the place the pilot did not understand.
street   the outdoor frames of lab/indoors/heldout.json, walks at street level
porch    the 31 of those frames taken after the barber's exit (session 20261113-025632): the figure
         stands on the shop's wooden porch, one step above the ground and under its roof, which is
         neither the street nor a landing above it. Asked, not scored: every model calls most of them
         a landing, and that is not wrong.

The labels of the two older sets are theirs; the session of 13 November was labelled from contact
sheets of the recording. Frames of one walk are close in time and look alike, so the counts say how
often a model is right on these places, not on rooms and landings in general.
"""

import bisect
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SESSION = "20261113-121513"
RECORDINGS = Path("/Users/kerim/recordings/pilot")

frames = []
for sample in json.loads((ROOT / "lab" / "indoors" / "heldout.json").read_text())["samples"]:
    where = "room" if sample["indoors"] else "porch" if sample["session"] == "20261113-025632" else "street"
    frames.append({"session": sample["session"], "t": float(sample["t"]), "where": where})

rows = [json.loads(line) for line in (RECORDINGS / SESSION / "play.jsonl").open()]
times = [row["t"] for row in rows]
for at in range(40, 1800, 20):
    row = rows[min(len(rows) - 1, bisect.bisect_left(times, at))]
    if abs(row["t"] - at) < 1 and (row.get("reading") or {}).get("minimap") not in (None, "none"):
        frames.append({"session": SESSION, "t": float(at), "where": "room"})
for step in range(31):
    frames.append({"session": SESSION, "t": 22.5 + step * 0.25, "where": "landing"})

out = Path(__file__).with_name("scene.json")
out.write_text(json.dumps({"frames": frames}, indent=1) + "\n")
print({place: sum(frame["where"] == place for frame in frames) for place in ("room", "landing", "street", "porch")})
