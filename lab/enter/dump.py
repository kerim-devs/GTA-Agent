"""What the object detector saw while the pilot tried to get into a vehicle, ten times a second.

For every stretch of enter_vehicle in the given sessions, with three seconds before and after: the
detections, what the map said, and what the skill sent to the pad. Needs the native detector, so it
runs outside a sandbox.

    pilot/.venv/bin/python lab/enter/dump.py /Users/kerim/recordings/pilot/20261112-110449 ... > lab/enter/runs.json
"""

import json
import sys
from pathlib import Path

import cv2

from pilot.objects import Detector

STEP = 6  # frames of the 60 a second
MARGIN = 180


def main(folders):
    detector = Detector()
    runs = []
    for folder in map(Path, folders):
        rows = [json.loads(line) for line in (folder / "play.jsonl").open()]
        rows = [row for row in rows if row.get("reading")]
        index = {json.loads(line)["frame_id"]: i for i, line in enumerate((folder / "frames.jsonl").open())}
        by_frame = {index[row["frame_id"]]: row for row in rows if row["frame_id"] in index}
        mine = sorted(i for i, row in by_frame.items() if (row.get("skill") or {}).get("name") == "enter_vehicle")
        spans = []
        for i in mine:
            if spans and i - spans[-1][1] <= 2 * MARGIN:
                spans[-1][1] = i
            else:
                spans.append([i, i])
        video = cv2.VideoCapture(str(folder / "video.mp4"))
        position = 0
        for first, last in spans:
            samples, row = [], None
            for i in range(max(0, first - MARGIN), last + MARGIN + 1):
                row = by_frame.get(i, row)
                if i % STEP or row is None:
                    continue
                if i != position:
                    video.set(cv2.CAP_PROP_POS_FRAMES, i)
                ok, image = video.read()
                position = i + 1
                if not ok:
                    break
                skill, pad = row.get("skill") or {}, row.get("sent_pad") or {}
                samples.append(
                    {
                        "t": round(row["t"], 2),
                        "map": row["reading"]["minimap"],
                        "corrupt": row["reading"]["corrupt"],
                        "skill": [skill.get("name"), skill.get("status"), skill.get("reason")],
                        "left": pad.get("left"),
                        "right": pad.get("right"),
                        "buttons": pad.get("buttons"),
                        "objects": [
                            [d.kind, [round(v) for v in d.box], round(d.confidence, 2)]
                            for d in detector.detect(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
                        ],
                    }
                )
            runs.append({"session": folder.name, "samples": samples})
        video.release()
    json.dump({"step_seconds": STEP / 60, "runs": runs}, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1:])
