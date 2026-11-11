"""Ask a local vision model fixed questions about the sampled frames and time every answer.

    pilot/.venv/bin/python lab/judge/measure.py --model qwen/qwen3-vl-4b --width 640 [--joint]

The server is any OpenAI-compatible one (LM Studio, llama.cpp). Each question has fixed answers and
the model replies with one letter. Without `--joint` every question is a request of its own; with it
all questions go out in one request and the answer is one letter per question.

The truth is `sample.json` (what the readers say) corrected by `truth.json` (what a person sees).
Results go to lab/judge/results/<model>-<width><tag>.json.
"""

import argparse
import json
import statistics
from pathlib import Path

import cv2
from pilot.judge import QUESTIONS, ask_joint, encode, letters, post

HERE = Path(__file__).resolve().parent
SCORED = ("mode", "overlay", "banner", "wanted")

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--url", default="http://127.0.0.1:1234")
parser.add_argument("--model", required=True)
parser.add_argument(
    "--width", type=int, default=640, help="frame width sent to the model; the height follows"
)
parser.add_argument("--joint", action="store_true", help="all questions in one request")
parser.add_argument("--limit", type=int)
parser.add_argument("--tag", default="")
args = parser.parse_args()


def truth(row: dict, hand: dict) -> dict:
    """What each scored question should answer on this frame; None where it is not scored."""
    situation, screen = row["situation"], row["screen"]
    if row["name"] in hand["unclear"]:
        mode = None
    elif row["name"] in hand["foot"]:
        mode = "foot"
    elif situation in ("foot", "vehicle"):
        mode = situation
    elif situation == "menu":
        # The pause menu and the map cover the picture; under the small menus the figure stands.
        mode = "foot" if screen in ("weapon_wheel", "phone", "interaction_menu") else None
    else:
        mode = "none"
    playing = situation in ("foot", "vehicle")
    return {
        "mode": mode,
        "overlay": situation == "menu",
        "banner": situation == "dead_or_failed",
        "wanted": row["wanted"] > 0 if playing and row["wanted"] is not None else None,
    }


def ask(image: str) -> dict:
    answers = {}
    if args.joint:
        choice, seconds = ask_joint(args.url, args.model, image)
        found = letters(choice)
        for index, (key, (_, meaning)) in enumerate(QUESTIONS.items()):
            letter, top = found[index] if index < len(found) else ("", {})
            answers[key] = {"letter": letter, "value": meaning.get(letter), "seconds": None, "top": top}
        answers["mode"]["seconds"] = round(seconds, 3)
        return answers
    for key, (question, meaning) in QUESTIONS.items():
        choice, seconds = post(args.url, args.model, image, question, 2)
        letter, top = (letters(choice) or [("", {})])[0]
        answers[key] = {
            "letter": letter,
            "value": meaning.get(letter),
            "seconds": round(seconds, 3),
            "top": top,
        }
    return answers


hand = json.loads((HERE / "truth.json").read_text())
rows = json.loads((HERE / "sample.json").read_text())[: args.limit]
results = []
for row in rows:
    image = encode(cv2.imread(str(HERE / "sample" / f"{row['name']}.jpg")), args.width)
    answers = ask(image)
    results.append({**row, "truth": truth(row, hand), "answers": answers})
    print(row["name"], "".join(value["letter"] or "?" for value in answers.values()), flush=True)


def share(pairs):
    pairs = list(pairs)
    return None if not pairs else round(sum(a == b for a, b in pairs) / len(pairs), 3)


def scored(key, keep=lambda row: True):
    return [
        (row["answers"][key]["value"], row["truth"][key])
        for row in results
        if row["truth"][key] is not None and keep(row)
    ]


def spread(values):
    values = sorted(values)
    return {"median": round(statistics.median(values), 3), "p90": values[int(len(values) * 0.9)]}


first = [row["answers"]["mode"]["seconds"] for row in results]
summary = {
    "model": args.model,
    "width": args.width,
    "joint": args.joint,
    "frames": len(results),
    **{key: share(scored(key)) for key in SCORED},
    "scored_frames": {key: len(scored(key)) for key in SCORED},
    "mode_by_truth": {
        name: share(scored("mode", lambda row, name=name: row["truth"]["mode"] == name))
        for name in ("foot", "vehicle", "none")
    },
    "overlay_by_screen": {
        name: share(scored("overlay", lambda row, name=name: row["screen"] == name))
        for name in ("game", "pause", "map", "weapon_wheel", "phone", "interaction_menu")
    },
    "seconds_frame": spread(
        first if args.joint else [sum(a["seconds"] for a in row["answers"].values()) for row in results]
    ),
    "logprobs": any(row["answers"]["mode"]["top"] for row in results),
}
if not args.joint:
    rest = [a["seconds"] for row in results for key, a in row["answers"].items() if key != "mode"]
    summary["seconds_first_question"], summary["seconds_next_questions"] = spread(first), spread(rest)
out = HERE / "results"
out.mkdir(exist_ok=True)
stem = f"{args.model.replace('/', '-')}-{args.width}{'-joint' if args.joint else ''}{args.tag}"
(out / f"{stem}.json").write_text(json.dumps({"summary": summary, "rows": results}, indent=1) + "\n")
print(json.dumps(summary, indent=1))
