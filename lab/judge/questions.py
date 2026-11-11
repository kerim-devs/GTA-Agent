"""The judge's questions and the one request that asks them, shared by the scripts in this folder.

What is measured here has to be what the pilot asks later, to the letter: asked together, questions
change each other's answers (docs/LOG.md, 11 November).
"""

import base64
import json
import math
import time
import urllib.request

import cv2

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
JOINT = (
    "\n\n".join(f"{i}. {question}" for i, (question, _) in enumerate(QUESTIONS.values(), 1))
    + "\n\nReply with one letter per question, in the order of the questions, "
    "separated by single spaces, and nothing else."
)


def encode(bgr, width: int) -> str:
    """The frame as the model gets it: scaled to `width`, JPEG, base64."""
    height = round(bgr.shape[0] * width / bgr.shape[1])
    small = cv2.resize(bgr, (width, height), interpolation=cv2.INTER_AREA)
    return base64.b64encode(cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 90])[1]).decode()


def post(url: str, model: str, image: str, text: str, max_tokens: int) -> tuple[dict, float]:
    """One request; returns the first choice as the server sent it and the seconds it took."""
    body = {
        "model": model,
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
        url + "/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"}
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=120) as response:
        data = json.load(response)
    return data["choices"][0], time.perf_counter() - started


def ask_joint(url: str, model: str, image: str) -> tuple[dict, float]:
    return post(url, model, image, JOINT, 2 * len(QUESTIONS) + 2)


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


def probability(letter: str, top: dict, meaning: dict) -> float | None:
    """The share of `letter` among the answers the question allows; None without log-probabilities."""
    weights = {key: math.exp(value) for key, value in top.items() if key in meaning}
    return round(weights[letter] / sum(weights.values()), 3) if letter in weights else None
