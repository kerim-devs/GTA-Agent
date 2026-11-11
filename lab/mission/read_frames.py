"""Reconstruct observation-only requests from recorded frames, without a live host.

Each sample uses a fresh pipeline: no invented skill/event history, GPS or objects.
Cached OCR is the latest observation at or before the selected video frame.
"""

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
    recording = Path("/Users/kerim/Documents/ChatGPT/gta/recordings/20261110-093238")
    frames = [json.loads(line) for line in (recording / "frames.jsonl").read_text().splitlines()]
    text_path = ROOT.parent / "wiring/text-093238.jsonl"
    texts = [json.loads(line) for line in text_path.read_text().splitlines()]
    targets = sorted(
        set(
            [
                5.2415,
                33.7221,
                34.3377,
                34.8901,
                36.4327,
                41.5,
                205.2057,
                206.8115,
                224.5501,
                536.7607,
                590.005,
                628.8,
                640.5,
                *range(0, 641, 5),
            ]
        )
    )
    cap = cv2.VideoCapture(str(recording / "video.mp4"))
    cases = []
    for target in targets:
        index = min(range(len(frames)), key=lambda i: abs(frames[i]["t"] - target))
        timestamp = frames[index]["t"]
        eligible = [(i, row) for i, row in enumerate(texts, 1) if row["t"] <= timestamp]
        line_number, text_row = eligible[-1] if eligible else (None, None)
        if text_row:
            values = dict(text_row["text"])
            values["lines"] = tuple(TextLine(**line) for line in values["lines"])
            scene = SceneText(**values)
        else:
            scene = SceneText()
        cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, bgr = cap.read()
        if not ok:
            raise RuntimeError(f"Cannot decode recorded frame {index}")
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        pipeline = Pipeline()
        try:
            reading, _, _ = pipeline.step(minimap_crop(rgb), timestamp, feedback=False)
        finally:
            pipeline.close()
        request = dict(
            events=[],
            help=scene.help,
            objective=scene.objective,
            subtitle=scene.subtitle,
            banner=scene.banner,
            minimap=asdict(reading),
            hud=asdict(hud.read(rgb, text=scene)),
            last_skill=None,
            notebook="",
            jpeg_path="",
            objects=[],
        )
        cases.append(
            dict(
                id=f"wifi-{target:g}",
                provenance="reconstructed_recorded_frame",
                source=dict(
                    path=str(recording),
                    frame=index,
                    t=timestamp,
                    text_path="lab/wiring/text-093238.jsonl",
                    text_line=line_number,
                ),
                request=request,
                model=None,
            )
        )
    cap.release()
    (ROOT / "frame_cases.json").write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n")
    print(f"Saved {len(cases)} frame-derived requests")


if __name__ == "__main__":
    main()
