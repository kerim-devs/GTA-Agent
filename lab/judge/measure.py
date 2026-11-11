"""Ask a local vision model fixed questions about the sampled frames and time every answer.

    pilot/.venv/bin/python lab/judge/measure.py --model qwen/qwen3-vl-4b --width 640 [--joint]

The server is any OpenAI-compatible one (LM Studio, llama.cpp). Each question has fixed answers and
the model replies with one letter. Without `--joint` every question is a request of its own; with it
all questions go out in one request and the answer is one letter per question.

The truth is `sample.json` (what the readers say) corrected by `truth.json` (what a person sees).
Results go to lab/judge/results/<model>-<width><tag>.json.
"""

import argparse
import base64
import json
import statistics
import time
import urllib.request
from pathlib import Path

import cv2

HERE = Path(__file__).resolve().parent
SYSTEM = (
    "You look at one screenshot of the game Grand Theft Auto V with a German interface "
    "and answer multiple-choice questions about it. Reply with the letter of the answer only."
)
# The questions do not exclude each other: a phone can be open while the figure stands on foot.
# The first version asked for one situation out of five and lost every such frame.
QUESTIONS = {
    "mode": (
        "How is the player character moving right now?\n"
        "A: on foot: walking, running, standing, fighting or climbing\n"
        "B: driving or riding a vehicle\n"
        "C: neither: a cutscene, a loading or black screen, or the character is dead",
        {"A": "foot", "B": "vehicle", "C": "none"},
    ),
    "overlay": (
        "Is a menu drawn on top of the game picture? Examples: the pause menu, the big map, a phone "
        "in the bottom right corner, a round weapon wheel, a list menu in the top left corner.\n"
        "A: yes\nB: no",
        {"A": True, "B": False},
    ),
    "banner": (
        "Is there a large coloured banner text across the middle of the screen, as after a failed "
        "or passed mission, a death or an arrest?\nA: yes\nB: no",
        {"A": True, "B": False},
    ),
    "wanted": (
        "Look at the top right corner. Are white police wanted stars lit there?\nA: yes\nB: no",
        {"A": True, "B": False},
    ),
    "path": (
        "Is the way straight ahead of the player free to move along?\n"
        "A: free\nB: blocked by a wall, vehicle or other obstacle close ahead\nC: cannot tell",
        {"A": "free", "B": "blocked", "C": "unknown"},
    ),
    "car": (
        "Is there a car or motorbike within a few steps that the player could get into?\nA: yes\nB: no",
        {"A": True, "B": False},
    ),
}
SCORED = ("mode", "overlay", "banner", "wanted")

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--url", default="http://127.0.0.1:1234")
parser.add_argument("--model", required=True)
parser.add_argument("--width", type=int, default=640, help="frame width sent to the model; the height follows")
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


def post(image: str, text: str, max_tokens: int) -> tuple[dict, float]:
    body = {
        "model": args.model,
        "temperature": 0,
        "max_tokens": max_tokens,
        "logprobs": True,
        "top_logprobs": 5,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image}"}},
                    {"type": "text", "text": text},
                ],
            },
        ],
    }
    request = urllib.request.Request(
        args.url + "/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"}
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=120) as response:
        data = json.load(response)
    return data["choices"][0], time.perf_counter() - started


def letters(choice: dict) -> list[tuple[str, dict]]:
    """The answer letters in order, each with the log-probabilities of its alternatives."""
    found = []
    try:
        for token in choice["logprobs"]["content"]:
            letter = token["token"].strip().upper()
            if len(letter) == 1 and letter.isalpha():
                top = {item["token"].strip(): round(item["logprob"], 3) for item in token["top_logprobs"]}
                found.append((letter, top))
    except (KeyError, IndexError, TypeError):
        pass
    if not found:
        found = [(c, {}) for c in choice["message"]["content"].upper() if c.isalpha()]
    return found


def ask(image: str) -> dict:
    answers = {}
    if args.joint:
        numbered = "\n\n".join(f"{i}. {q}" for i, (q, _) in enumerate(QUESTIONS.values(), 1))
        text = (
            f"{numbered}\n\nReply with one letter per question, in the order of the questions, "
            "separated by single spaces, and nothing else."
        )
        choice, seconds = post(image, text, 2 * len(QUESTIONS) + 2)
        found = letters(choice)
        for index, (key, (_, meaning)) in enumerate(QUESTIONS.items()):
            letter, top = found[index] if index < len(found) else ("", {})
            answers[key] = {"letter": letter, "value": meaning.get(letter), "seconds": None, "top": top}
        answers["mode"]["seconds"] = round(seconds, 3)
        return answers
    for key, (question, meaning) in QUESTIONS.items():
        choice, seconds = post(image, question, 2)
        letter, top = (letters(choice) or [("", {})])[0]
        answers[key] = {"letter": letter, "value": meaning.get(letter), "seconds": round(seconds, 3), "top": top}
    return answers


hand = json.loads((HERE / "truth.json").read_text())
rows = json.loads((HERE / "sample.json").read_text())[: args.limit]
results = []
for row in rows:
    bgr = cv2.imread(str(HERE / "sample" / f"{row['name']}.jpg"))
    height = round(bgr.shape[0] * args.width / bgr.shape[1])
    small = cv2.resize(bgr, (args.width, height), interpolation=cv2.INTER_AREA)
    image = base64.b64encode(cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 90])[1]).decode()
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
