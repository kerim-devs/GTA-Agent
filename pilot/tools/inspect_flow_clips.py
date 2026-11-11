"""Extract source-clock evidence by frame index, never by MP4 presentation time."""

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from pilot.contract import Hud, Reading
from pilot.flow import Flow
from pilot.skills import Observation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path)
    parser.add_argument("--start", type=float, required=True)
    parser.add_argument("--end", type=float, required=True)
    parser.add_argument("--step", type=float, default=0.5)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--every-frame", action="store_true")
    parser.add_argument(
        "--labels", type=Path, help="Manual source-time intervals for an open-loop flow replay"
    )
    args = parser.parse_args()
    if args.step <= 0 or args.end < args.start:
        parser.error("step must be positive and end must follow start")
    frames = [json.loads(line) for line in (args.recording / "frames.jsonl").read_text().splitlines()]
    pads = [json.loads(line) for line in (args.recording / "pad.jsonl").read_text().splitlines()]
    args.output.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(args.recording / "video.mp4"))
    selected = []
    target = args.start
    last_index = -1
    while target <= args.end + 1e-8:
        frame = min(frames, key=lambda item: abs(item["t"] - target))
        index = frame["i"]
        if index != last_index:
            cap.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, image = cap.read()
            if not ok:
                raise RuntimeError(f"cannot decode frame {index}")
            path = args.output / f"{frame['t']:08.3f}-{index}.jpg"
            if not cv2.imwrite(str(path), image):
                raise RuntimeError(f"cannot write {path}")
            selected.append({"i": index, "t": frame["t"], "file": path.name})
            last_index = index
        if args.every_frame:
            if index + 1 == len(frames):
                break
            target = frames[index + 1]["t"]
        else:
            target += args.step
    cap.release()
    sheet = np.zeros((((len(selected) + 3) // 4) * 230, 4 * 384, 3), dtype=np.uint8)
    for n, frame in enumerate(selected):
        thumb = cv2.resize(cv2.imread(str(args.output / frame["file"])), (384, 216))
        row, col = divmod(n, 4)
        sheet[row * 230 : row * 230 + 216, col * 384 : (col + 1) * 384] = thumb
        cv2.putText(
            sheet,
            f"t={frame['t']:.3f} i={frame['i']}",
            (col * 384 + 4, row * 230 + 228),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (255, 255, 255),
            1,
        )
    cv2.imwrite(str(args.output / "contact.jpg"), sheet)
    if len(selected) > 24:
        for start in range(0, len(selected), 24):
            page = sheet[start // 4 * 230 : (start // 4 + 6) * 230]
            cv2.imwrite(str(args.output / f"contact-{start // 24:02d}.jpg"), page)
    evidence = {
        "recording": str(args.recording),
        "frames": selected,
        "pad": [pad for pad in pads if args.start - 1.1 <= pad["t"] <= args.end + 1.1],
    }
    (args.output / "index.json").write_text(json.dumps(evidence, indent=2) + "\n")
    if args.labels:
        labels = json.loads(args.labels.read_text())
        flow = Flow()
        reading = Reading("tilted", "purple", 0.0, 0.0, 0.0, False, 1.0)
        replay = []
        previous = None
        for frame in frames:
            if not args.start <= frame["t"] <= args.end:
                continue
            label = next((label for label in labels if label["start"] <= frame["t"] < label["end"]), {})
            screen = label.get("screen", "game")
            result = flow.tick(
                Observation(reading, True, frame["t"], hud=Hud(screen=screen)), label.get("text")
            )
            state = (screen, result.action if result else "ordinary", result.pad.buttons if result else ())
            if state != previous or (result and result.events):
                replay.append(
                    {
                        "i": frame["i"],
                        "t": frame["t"],
                        "screen": screen,
                        "action": state[1],
                        "buttons": state[2],
                        "events": result.events if result else (),
                    }
                )
            previous = state
        (args.output / "flow-replay.json").write_text(json.dumps(replay, indent=2) + "\n")
    print(f"Extracted {len(selected)} source-clock frames to {args.output}")


if __name__ == "__main__":
    main()
