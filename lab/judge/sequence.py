"""Ask the judge about stretches of a recording, frame after frame, and keep every raw answer.

    pilot/.venv/bin/python lab/judge/sequence.py --url http://<server>:1234 --model qwen/qwen3-vl-8b \
        /Users/kerim/recordings/kerim/20261111-065022 1300-2600 9700-10200

A stretch is a range of frame numbers of the recording's video; every `--step`th frame is asked,
which at 60 frames a second and a step of 15 is the four requests a second the judge will make.
The rows go to lab/judge/sequences/<recording>-<first>-<last>.jsonl: the frame, its time in the
recording, the seconds the request took and the server's first choice as it came, so that parsing
and the rule for accepting an answer can be tried on real sequences without a server.
"""

import argparse
import json
from pathlib import Path

import cv2
from questions import QUESTIONS, ask_joint, encode, letters

HERE = Path(__file__).resolve().parent

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("recording", type=Path)
parser.add_argument("stretches", nargs="+", metavar="FIRST-LAST")
parser.add_argument("--url", default="http://127.0.0.1:1234")
parser.add_argument("--model", required=True)
parser.add_argument("--width", type=int, default=640)
parser.add_argument("--step", type=int, default=15)
args = parser.parse_args()

times = [json.loads(line) for line in (args.recording / "frames.jsonl").read_text().splitlines()]
video = cv2.VideoCapture(str(args.recording / "video.mp4"))
out = HERE / "sequences"
out.mkdir(exist_ok=True)
for stretch in args.stretches:
    first, last = (int(part) for part in stretch.split("-"))
    video.set(cv2.CAP_PROP_POS_FRAMES, first)
    path = out / f"{args.recording.name}-{first}-{last}.jsonl"
    with path.open("w") as rows:
        for index in range(first, last + 1):
            ok, bgr = video.read()
            if not ok:
                break
            if (index - first) % args.step:
                continue
            choice, seconds = ask_joint(args.url, args.model, encode(bgr, args.width))
            answer = "".join(letter for letter, _ in letters(choice))[: len(QUESTIONS)]
            rows.write(
                json.dumps(
                    {
                        "frame": index,
                        "time": times[index]["t"] if index < len(times) else None,
                        "model": args.model,
                        "width": args.width,
                        "seconds": round(seconds, 3),
                        "answer": answer,
                        "choice": choice,
                    }
                )
                + "\n"
            )
            print(index, answer, round(seconds, 3), flush=True)
    print("wrote", path)
