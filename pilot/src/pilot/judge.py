"""The judge's questions and request, shared by the runtime and laboratory scripts.

What is measured here has to be what the pilot asks later, to the letter: asked together, questions
change each other's answers (docs/LOG.md, 11 November).
"""

import base64
import ipaddress
import json
import math
import threading
import time
import urllib.request
from urllib.parse import urlsplit

import cv2

from .contract import Answer, Judgment

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

# Measured separately: adding questions to JOINT changes its established answers.
# These are not enabled in Reader until their recorded-image gates pass.
WHERE_QUESTIONS = {
    "where_plain": (
        "Where are the player character's feet?\n"
        "A: in a traffic lane on the asphalt road\n"
        "B: on the sidewalk or verge outside the road\n"
        "C: on other open ground or in a yard\nD: indoors\nE: cannot see the feet",
        {"A": "carriageway", "B": "roadside", "C": "open", "D": "inside", "E": "unknown"},
    ),
    "where": (
        "Look at where the player character's FEET touch the ground, not the road ahead. "
        "Which surface is the character standing on? A road shoulder, pavement or verge "
        "is not a traffic lane. A private dirt yard is not a carriageway.\n"
        "A: carriageway, a lane used by road traffic\n"
        "B: pavement, verge or roadside outside the traffic lanes\n"
        "C: open ground or a yard\nD: inside a building\nE: cannot tell",
        {"A": "carriageway", "B": "roadside", "C": "open", "D": "inside", "E": "unknown"},
    ),
    "vehicle": (
        "Consider ONLY the vehicle outlined in red. Is it a parked empty vehicle that "
        "the player could take, or part of road traffic? A stopped vehicle in a traffic "
        "lane or at a junction is traffic, not parked. Do not infer empty merely because "
        "you cannot see a driver.\nA: parked and empty\n"
        "B: stopped in traffic or occupied\nC: driving\nD: cannot tell",
        {"A": "parked", "B": "traffic", "C": "driving", "D": "unknown"},
    ),
    "vehicle_plain": (
        "What is the state of the vehicle in the red rectangle?\n"
        "A: parked outside traffic, with an empty driver's seat\n"
        "B: stopped in traffic or with someone inside\n"
        "C: moving along the road\nD: cannot determine its state",
        {"A": "parked", "B": "traffic", "C": "driving", "D": "unknown"},
    ),
    "edge": (
        "If the player character is on the carriageway, on which side of the SCREEN "
        "is the nearer safe road edge, pavement or verge? Compare the feet to the "
        "edges, not the vehicle's direction. If the character is off the carriageway "
        "or the nearer edge cannot be determined, answer C.\n"
        "A: left\nB: right\nC: cannot tell",
        {"A": "left", "B": "right", "C": "unknown"},
    ),
}


def ask_where(url, model, image, names=("where", "edge"), *, timeout=1.0):
    """Ask the exact laboratory questions without changing the live six-question prompt."""
    text = "\n\n".join(WHERE_QUESTIONS[name][0] for name in names)
    text += "\nReply with one answer letter per question, separated by single spaces, and nothing else."
    return post(url, model, image, text, 2 * len(names) + 2, timeout=timeout)


def parse_where(choice, capture, duration, server, names=("where", "edge")):
    """Preserve capture age and uncertainty; reject prose or incomplete replies."""
    content = choice.get("message", {}).get("content", "")
    tokens = content.upper().split() if isinstance(content, str) else []
    if len(tokens) != len(names):
        raise ValueError("wrong number of roadside answer letters")
    annotated = letters(choice)
    answers, probabilities = {}, {}
    for index, name in enumerate(names):
        meaning = WHERE_QUESTIONS[name][1]
        letter = tokens[index]
        if letter not in meaning:
            raise ValueError(f"invalid answer for {name}")
        top = annotated[index][1] if len(annotated) == len(tokens) and annotated[index][0] == letter else {}
        valid = {key: value for key, value in top.items() if key in meaning and math.isfinite(value)}
        weights = {key: math.exp(value - max(valid.values())) for key, value in valid.items()}
        total = sum(weights.values())
        probabilities[name] = {key: weights.get(key, 0.0) / total for key in meaning} if total else {}
        answers[name] = Answer(meaning[letter], round(probabilities[name][letter], 3) if total else None)
    return Judgment(capture, answers, probabilities, duration, server)


def encode(bgr, width: int) -> str:
    """The frame as the model gets it: scaled to `width`, JPEG, base64."""
    height = round(bgr.shape[0] * width / bgr.shape[1])
    small = cv2.resize(bgr, (width, height), interpolation=cv2.INTER_AREA)
    return base64.b64encode(cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 90])[1]).decode()


def post(url: str, model: str, image: str, text: str, max_tokens: int, *, timeout=120) -> tuple[dict, float]:
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
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    with opener.open(request, timeout=timeout) as response:
        data = json.load(response)
    return data["choices"][0], time.perf_counter() - started


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("judge redirects are not allowed")


def ask_joint(url: str, model: str, image: str, *, timeout=120) -> tuple[dict, float]:
    return post(url, model, image, JOINT, 2 * len(QUESTIONS) + 2, timeout=timeout)


def letters(choice: dict) -> list[tuple[str, dict]]:
    """The answer letters in order, each with the log-probabilities of its alternatives."""
    found = []
    try:
        for token in choice["logprobs"]["content"]:
            letter = token["token"].strip().upper()
            if len(letter) == 1 and letter.isalpha():
                # The same letter comes as several tokens, "A" and " A": their shares add up. Taking
                # the last one, as the first measurement did, put 0.003 on an answer the model gave
                # with certainty.
                shares: dict[str, float] = {}
                for item in token["top_logprobs"]:
                    key = item["token"].strip().upper()
                    shares[key] = shares.get(key, 0.0) + math.exp(item["logprob"])
                top = {key: round(math.log(share), 3) for key, share in shares.items() if share > 0}
                found.append((letter, top))
    except (KeyError, IndexError, TypeError, ValueError):
        pass
    if not found:
        found = [(c, {}) for c in choice["message"]["content"].upper() if c.isalpha()]
    return found


def probability(letter: str, top: dict, meaning: dict) -> float | None:
    """The share of `letter` among the answers the question allows; None without log-probabilities."""
    weights = {key: math.exp(value) for key, value in top.items() if key in meaning}
    return round(weights[letter] / sum(weights.values()), 3) if letter in weights else None


def parse(choice: dict, capture: float, duration: float, server: str) -> Judgment:
    """Reject incomplete replies; normalize each question over its own allowed letters."""
    content = choice.get("message", {}).get("content", "")
    tokens = content.upper().split() if isinstance(content, str) else []
    if len(tokens) != len(QUESTIONS):
        raise ValueError("judge reply must contain six answer letters")
    annotated = letters(choice)
    answers, probabilities = {}, {}
    for index, (name, (_, meaning)) in enumerate(QUESTIONS.items()):
        letter = tokens[index]
        if letter not in meaning:
            raise ValueError(f"invalid answer for {name}")
        top = annotated[index][1] if len(annotated) == len(tokens) and annotated[index][0] == letter else {}
        valid = {key: value for key, value in top.items() if key in meaning and math.isfinite(value)}
        answers[name] = Answer(meaning[letter], probability(letter, valid, meaning))
        weights = {key: math.exp(value - max(valid.values())) for key, value in valid.items()}
        total = sum(weights.values())
        probabilities[name] = {key: weights.get(key, 0.0) / total for key in meaning} if total else {}
    return Judgment(capture, answers, probabilities, duration, server)


def endpoint(value: str) -> tuple[str, str]:
    """Accept only explicit local endpoints, without DNS resolution or public uploads."""
    url, separator, model = value.partition("=")
    parsed = urlsplit(url)
    if not separator or not model or parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("judge server must be URL=MODEL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ValueError("judge URL must be a local server origin")
    try:
        _ = parsed.port
        address = ipaddress.ip_address(parsed.hostname) if parsed.hostname != "localhost" else None
    except ValueError as exc:
        raise ValueError("judge server must use localhost or a private numeric IP") from exc
    private = (
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("fc00::/7"),
    )
    if address is not None and not (address.is_loopback or any(address in network for network in private)):
        raise ValueError("judge server must use localhost or a private numeric IP")
    return url.rstrip("/"), model


class ModeFilter:
    """Accept a mode that judgments in a row name, and let it lapse with the age of its frame.

    The first mode takes two judgments and a change of an accepted one three. While Kerim pulls a
    driver out of a car the answers go foot, vehicle, vehicle, foot, foot, none, vehicle: two in a
    row turned the mode three times in two seconds, and every turn makes the head plan afresh.
    No probability lets a single judgment through: in the recorded sequences the one wrong answer
    on foot with stars came with 0.9997, more than most right ones.
    """

    FIRST, CHANGE = 2, 3
    # Against the real server a judgment is about a frame 0.27 s old when it arrives, and the next
    # one comes 0.3 s later; with one request lost to a server that is down the gap reached a
    # second, and a mode that lapsed at one second flickered to nothing.
    LAPSE = 1.5

    def __init__(self):
        self.mode = None
        self.capture = None
        self.candidate = None
        self.run = 0

    def update(self, judgment: Judgment | None, t: float, *, flat: bool = False) -> str | None:
        """`flat`: the minimap of this tick lies flat and is sound, which it only does on foot."""
        if self.capture is not None and t - self.capture > self.LAPSE:
            self.mode = self.candidate = None
            self.capture = None
            self.run = 0
        if (
            judgment is not None
            and 0 <= t - judgment.capture <= 1.0
            and (self.capture is None or judgment.capture > self.capture)
        ):
            answer = judgment.answers.get("mode")
            mode = None if answer is None else answer.value
            if mode == "vehicle" and flat:
                # Standing next to a car the judge says vehicle, three times in a row and more
                # (session 20261112-103305: the head opened the map on foot four times). The map
                # tilts in every vehicle: of 14,000 ticks of driving none lay flat and sound.
                mode = "foot"
            if mode in {"foot", "vehicle", "none"}:
                self.run = self.run + 1 if mode == self.candidate else 1
                self.candidate, self.capture = mode, judgment.capture
                if self.run >= (self.FIRST if self.mode is None else self.CHANGE):
                    self.mode = mode
        return self.mode


class Reader:
    """Nonblocking visual reader with bounded requests and ordered local failover."""

    def __init__(self, servers, *, transport=None, clock=time.monotonic):
        self.servers = [endpoint(server) for server in servers]
        self.transport = transport if transport is not None else self._request
        self.clock = clock
        self.lock = threading.Lock()
        self.active = None
        self.busy = set()
        self.cooldown = {}
        self.strikes = {}
        self.last_start = float("-inf")
        self.failures = []
        self.closed = False

    @staticmethod
    def _request(url, model, image):
        return ask_joint(url, model, image, timeout=1.0)

    def _work(self, job, rgb):
        try:
            image = encode(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), 640)
            with self.lock:
                if self.closed or self.active is not job:
                    return
            choice, _ = self.transport(*self.servers[job["index"]], image)
            result = parse(choice, job["capture"], self.clock() - job["started"], job["server"])
            error = None
        except Exception as exc:
            result, error = None, f"{type(exc).__name__}: {exc}"
        finally:
            duration = self.clock() - job["started"]
            with self.lock:
                self.busy.discard(job["index"])
        with self.lock:
            if not self.closed and self.active is job:
                job.update(done=True, result=result, error=error, duration=duration)

    def poll(self, rgb, capture: float) -> Judgment | None:
        with self.lock:
            if self.closed:
                return None
            now, result = self.clock(), None
            job = self.active
            if job is not None and (job.get("done") or now - job["started"] >= 1.0):
                duration = job.get("duration", now - job["started"])
                error = job.get("error")
                if duration >= 1.0:
                    error = "timeout"
                if error:
                    # Two seconds after the first failure, twice as long after each further one in a
                    # row: a server that is down for good costs a request every half minute, not
                    # every other second. The next server is asked on this very tick.
                    strikes = self.strikes[job["index"]] = self.strikes.get(job["index"], 0) + 1
                    self.cooldown[job["index"]] = now + min(30.0, 2.0**strikes)
                    self.last_start = float("-inf")
                    self.failures.append(
                        {
                            "capture": job["capture"],
                            "duration": duration,
                            "server": job["server"],
                            "answers": {},
                            "probabilities": {},
                            "error": error,
                        }
                    )
                else:
                    result = job["result"]
                    self.strikes[job["index"]] = 0
                self.active = None
            if self.active is None and now - self.last_start >= 0.25 and rgb is not None:
                index = next(
                    (
                        i
                        for i in range(len(self.servers))
                        if i not in self.busy and now >= self.cooldown.get(i, 0)
                    ),
                    None,
                )
                if index is not None:
                    url, model = self.servers[index]
                    job = {"index": index, "server": f"{url}={model}", "capture": capture, "started": now}
                    self.active, self.last_start = job, now
                    self.busy.add(index)
                    threading.Thread(target=self._work, args=(job, rgb.copy()), daemon=True).start()
            return result

    def drain_failures(self):
        with self.lock:
            rows, self.failures = self.failures, []
            return rows

    def close(self):
        with self.lock:
            self.closed = True
            self.active = None
