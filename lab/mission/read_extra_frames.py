"""Read manually labelled vehicle frames and Kerim's wanted-state samples."""

import json
from dataclasses import asdict
from pathlib import Path

import cv2

from pilot import hud
from pilot.conductor import minimap_crop
from pilot.loop import Pipeline
from pilot.scene import SceneText, TextLine

ROOT = Path(__file__).resolve().parent


def main():
    labels = json.loads((ROOT.parent / "objects/labels.json").read_text())["frames"]
    texts = [json.loads(line) for line in (ROOT.parent / "wiring/text-093238.jsonl").read_text().splitlines()]
    selected = [row for row in labels if str(row["id"]).zfill(3) in {"071", "072", "073", "075"}]
    samples = [(f"objects-{row['id']}", Path(row["source"]), row["frame_index"], row) for row in selected]
    recording = Path("/Users/kerim/recordings/kerim/20261111-065022")
    samples.extend(
        (f"kerim-{index}", recording, index, None)
        for index in (2758, 3780, 9706, 10115, 10524, 12772, 15020, 15633, 17400)
    )
    cases = []
    for case_id, directory, index, label in samples:
        frames = [json.loads(line) for line in (directory / "frames.jsonl").read_text().splitlines()]
        timestamp = frames[index]["t"]
        scene = SceneText()
        if label:
            text_row = [row for row in texts if row["t"] <= timestamp][-1]
            values = dict(text_row["text"])
            values["lines"] = tuple(TextLine(**line) for line in values["lines"])
            scene = SceneText(**values)
        cap = cv2.VideoCapture(str(directory / "video.mp4"))
        cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, bgr = cap.read()
        cap.release()
        if not ok:
            raise RuntimeError(f"Cannot decode {case_id}")
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        pipeline = Pipeline()
        try:
            reading, _, _ = pipeline.step(minimap_crop(rgb), timestamp, feedback=False)
        finally:
            pipeline.close()
        objects = (
            [{"kind": item["kind"], "box": item["box"]} for item in label["labels"] if not item["player"]]
            if label
            else []
        )
        request = dict(
            events=[],
            help=scene.help,
            objective=scene.objective,
            subtitle=scene.subtitle,
            banner=scene.banner,
            minimap=asdict(reading),
            hud=asdict(hud.read(rgb, text=scene)),
            objects=objects,
            last_skill=None,
            notebook="",
            jpeg_path="",
        )
        cases.append(
            dict(
                id=case_id,
                provenance="reconstructed_recorded_frame",
                source=dict(
                    path=str(directory),
                    frame=index,
                    t=timestamp,
                    object_label=label["id"] if label else None,
                    object_source="lab/objects/labels.json" if label else None,
                    text_source="lab/wiring/text-093238.jsonl" if label else "not_read",
                ),
                request=request,
                model=None,
            )
        )
    (ROOT / "extra_cases.json").write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n")
    print(f"Saved {len(cases)} additional recorded requests")


if __name__ == "__main__":
    main()
