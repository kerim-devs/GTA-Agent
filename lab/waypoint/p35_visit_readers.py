import json
from pathlib import Path

import cv2

from pilot.scene import TextReader
from pilot.waypoint import land_at_cursor, read_map

ROOT = Path("/Users/kerim/recordings/pilot")
VISITS = {
    "124637": [2.605],
    "123334": [3.002, 5.404, 8.957, 11.944, 12.8, 13.1],
    "123938": [
        22.95,
        28.145,
        29.746,
        40.8,
        42.042,
        43.643,
        57.1,
        62.2,
        64.0,
        79.2,
        89.8,
        93.4,
        105.1,
        121.0,
        133.1,
    ],
    "125537": [3.006, 4.691],
}


def frame(recording, requested):
    frames = [json.loads(line) for line in (recording / "frames.jsonl").read_text().splitlines()]
    chosen = min(frames, key=lambda item: abs(item["t"] - requested))
    capture = cv2.VideoCapture(str(recording / "video.mp4"))
    capture.set(cv2.CAP_PROP_POS_FRAMES, chosen["i"])
    ok, image = capture.read()
    capture.release()
    assert ok
    return chosen, cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


reader = TextReader()
rows = []
for stamp, times in VISITS.items():
    recording = ROOT / f"20261111-{stamp}"
    for requested in times:
        meta, image = frame(recording, requested)
        text = reader.read(image)
        picture = read_map(image, text)
        rows.append(
            {
                "recording": f"20261111-{stamp}",
                "requested_time": requested,
                "frame": meta,
                "text": [
                    {"text": line.text, "confidence": line.confidence, "box": line.box}
                    for line in text.lines
                    if line.confidence >= 0.5
                ],
                "map": {
                    "screen": picture.screen,
                    "cursor": picture.cursor,
                    "player": picture.player,
                    "missions": picture.missions,
                    "waypoint": picture.waypoint,
                    "proof": picture.proof,
                    "land": land_at_cursor(image) if picture.screen == "map" else None,
                },
            }
        )
Path(__file__).with_name("p35-visits-evidence.json").write_text(json.dumps(rows, indent=2) + "\n")
for row in rows:
    print(
        json.dumps(
            {
                "recording": row["recording"],
                "t": row["frame"]["t"],
                "frame_id": row["frame"]["frame_id"],
                "map": row["map"],
                "text": [line["text"] for line in row["text"]],
            }
        )
    )
