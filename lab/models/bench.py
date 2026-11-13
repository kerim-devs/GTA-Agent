"""One model, or a fast one beside a thinking one, on the pilot's own questions: how often right, how fast.

    pilot/.venv/bin/python lab/models/bench.py judge   --url URL --model ID [--extra JSON] [--tag T]
    pilot/.venv/bin/python lab/models/bench.py chooser --url URL --model ID [--extra JSON] [--timeout S] [--tag T]
    pilot/.venv/bin/python lab/models/bench.py think   --url URL --model ID [--extra JSON] [--tokens N] [--tag T]
    pilot/.venv/bin/python lab/models/bench.py scene   --url URL --model ID [--extra JSON] [--think] [--each N]
    pilot/.venv/bin/python lab/models/bench.py beside  --url URL --fast ID --big ID [--seconds S] [--rate HZ]
                                                       [--fast-extra JSON] [--big-extra JSON] [--tag T]

`judge` is the fixed questions the pilot asks several times a second (lab/judge: 210 frames, the
figure's way of moving labelled by hand). `chooser` is the pick among what the rules offer
(lab/chooser: 150 labelled situations), answered with one letter as the pilot asks it. `think` is the
same pick with the model allowed to reason first, for a model that is asked seldom. `scene` asks where
the figure stands, in a room, on a landing above the street or on the street (lab/models/scene.json,
built by scene_build.py), which is what the pilot did not know on 13 November when it stepped out of
an apartment and walked back in. `beside` asks the fast model at the pilot's rate while the big one
answers picks back to back, which is the question whether two models on one card get in each other's
way.

`--extra` is JSON merged into every request body (the switch that turns a model's thinking off or
down differs by model). The questions, pictures and sampling are the pilot's own: this file only
wraps `pilot.judge.post`. Results go to lab/models/results/.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import re
import runpy
import statistics
import sys
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot" / "src"))
sys.path.insert(0, str(ROOT / "lab" / "chooser"))

import cv2

from pilot import judge

RESULTS = Path(__file__).with_name("results")
RECORDINGS = "/Users/kerim/recordings/pilot"


def slug(model, tag=""):
    return re.sub(r"[^a-z0-9.]+", "-", model.lower()).strip("-") + tag


def wrap(extra, counts=None):
    """`pilot.judge.post` with `extra` merged into the body; everything else is the pilot's."""
    original = judge.post

    def post(url, model, image, text, max_tokens, *, timeout=120):
        body = {
            "model": model,
            "temperature": 0,
            "max_tokens": max_tokens,
            "logprobs": True,
            "top_logprobs": 5,
            "messages": [
                {"role": "system", "content": judge.SYSTEM},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image}"}},
                        {"type": "text", "text": text},
                    ],
                },
            ],
            **extra,
        }
        request = urllib.request.Request(
            url + "/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"}
        )
        started = time.monotonic()
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=timeout) as answer:
            data = json.load(answer)
        seconds = time.monotonic() - started
        if counts is not None:
            counts.append((seconds, data.get("usage", {})))
        return data["choices"][0], seconds

    judge.post = post if extra or counts is not None else original
    return original


def spread(values):
    values = sorted(values)
    if not values:
        return None
    return {
        "n": len(values),
        "median": round(statistics.median(values), 3),
        "p90": round(values[max(0, math.ceil(len(values) * 0.9) - 1)], 3),
        "p99": round(values[max(0, math.ceil(len(values) * 0.99) - 1)], 3),
        "max": round(values[-1], 3),
    }


def run_judge(args):
    wrap(json.loads(args.extra))
    tag = (args.tag or "") + "-bench"
    sys.argv = ["measure.py", "--url", args.url, "--model", args.model, "--width", "640", "--joint", "--tag=" + tag]
    runpy.run_path(str(ROOT / "lab" / "judge" / "measure.py"), run_name="__main__")


def run_chooser(args):
    wrap(json.loads(args.extra))
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"chooser-{slug(args.model, args.tag or '')}-{args.timeout:g}s.json"
    sys.argv = ["measure.py", "--server", f"{args.url}={args.model}", "--timeout", str(args.timeout), "--output", str(out)]
    runpy.run_path(str(ROOT / "lab" / "chooser" / "measure.py"), run_name="__main__")


def situations():
    import measure  # lab/chooser/measure.py
    from pilot.chooser import _prompt

    rows = []
    for entry in measure.load():
        options = measure.checked_candidates(entry)
        request = entry["head_request"]
        names = [o.name for o in options]
        text = _prompt(
            "What should the player do next?",
            {o.name: o.description for o in options},
            {"objective": request.objective, "help": request.help},
        )
        frame = cv2.imread(str(request.jpeg_path))
        rows.append((entry, names, text, judge.encode(frame, min(640, frame.shape[1]))))
    return rows


def run_think(args):
    """The pick with room to reason: the answer is the last capital letter A to F the model gives."""
    extra = json.loads(args.extra)
    rows, seconds_all, tokens_all = [], [], []
    picks = situations()
    for entry, names, text, image in picks[:: max(1, math.ceil(len(picks) / args.limit))] if args.limit else picks:
        body = {
            "model": args.model,
            "temperature": 0,
            "max_tokens": args.tokens,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image}"}},
                        {"type": "text", "text": text + args.suffix},
                    ],
                }
            ],
            **extra,
        }
        request = urllib.request.Request(
            args.url + "/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"}
        )
        started = time.monotonic()
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=60) as answer:
                data = json.load(answer)
            message = data["choices"][0]["message"]
            content = message.get("content") or ""
            usage = data.get("usage", {})
        except (OSError, ValueError, LookupError) as exc:  # a timeout counts as no answer
            content, usage = f"error: {type(exc).__name__}", {}
        seconds = time.monotonic() - started
        found = re.findall(r"\b([A-F])\b", content.strip().splitlines()[-1] if content.strip() else "")
        letter = found[-1] if found else None
        name = dict(zip("ABCDEF", names, strict=False)).get(letter)
        rows.append(
            {
                "id": entry["id"],
                "name": name,
                "right": entry["right"],
                "seconds": round(seconds, 3),
                "completion_tokens": usage.get("completion_tokens"),
                "content": content[-160:],
            }
        )
        seconds_all.append(seconds)
        if usage.get("completion_tokens"):
            tokens_all.append(usage["completion_tokens"])
    answered = [row for row in rows if row["name"]]
    result = {
        "model": args.model,
        "extra": extra,
        "max_tokens": args.tokens,
        "situations": len(rows),
        "answered": len(answered),
        "right": sum(row["name"] in row["right"] for row in answered),
        "right_share_of_all": round(sum(row["name"] in row["right"] for row in answered) / len(rows), 3),
        "seconds": spread(seconds_all),
        "completion_tokens_median": statistics.median(tokens_all) if tokens_all else None,
        "rows": rows,
    }
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"think-{slug(args.model, args.tag or '')}.json"
    out.write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}, indent=1))


WHERE = (
    "This is a screenshot of a game. Where is the player's character?\n"
    "A: inside a building, in a room\n"
    "B: outside a building's door on a raised landing, balcony or outside staircase, above the street\n"
    "C: outside at street level, on a road, a pavement, a yard or open ground"
)
PLACES = {"A": "room", "B": "landing", "C": "street"}
THINK = (
    "\nThink briefly first, in at most three short sentences, then end with a last line "
    "of the form 'Answer: X' with the one letter."
)


def scene_frames(cache, each):
    """The labelled frames as the model gets them, cut from the recordings once and kept in `cache`."""
    frames = json.loads(Path(__file__).with_name("scene.json").read_text())["frames"]
    if each:
        chosen = []
        for place in (*PLACES.values(), "porch"):
            rows = [frame for frame in frames if frame["where"] == place]
            chosen += rows[:: max(1, math.ceil(len(rows) / each))]
        frames = chosen
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    videos, out = {}, []
    for frame in frames:
        path = cache / f"{frame['session']}-{frame['t']:07.2f}.jpg"
        if not path.exists():
            if frame["session"] not in videos:
                videos[frame["session"]] = cv2.VideoCapture(f"{RECORDINGS}/{frame['session']}/video.mp4")
            video = videos[frame["session"]]
            video.set(cv2.CAP_PROP_POS_FRAMES, round(frame["t"] * (video.get(cv2.CAP_PROP_FPS) or 60)))
            ok, bgr = video.read()
            if not ok:
                continue
            path.write_bytes(base64.b64decode(judge.encode(bgr, 640)))
        out.append((frame, base64.b64encode(path.read_bytes()).decode()))
    return out


def run_scene(args):
    """Where the figure stands, asked with one letter as the pilot asks, or with room to reason first."""
    extra = json.loads(args.extra)
    rows, seconds_all, tokens_all = [], [], []
    for frame, image in scene_frames(args.cache, args.each):
        body = {
            "model": args.model,
            "temperature": 0,
            "max_tokens": args.tokens if args.think else 3,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image}"}},
                        {"type": "text", "text": WHERE + (args.suffix if args.think else "")},
                    ],
                }
            ],
            **extra,
        }
        if not args.think:
            body["messages"].insert(0, {"role": "system", "content": judge.SYSTEM})
            body.update(logprobs=True, top_logprobs=5)
        request = urllib.request.Request(
            args.url + "/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"}
        )
        started = time.monotonic()
        letter, usage, content = None, {}, ""
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=90) as answer:
                data = json.load(answer)
            choice, usage = data["choices"][0], data.get("usage", {})
            content = choice["message"].get("content") or ""
            if args.think:
                found = re.findall(r"\b([A-C])\b", content.strip().splitlines()[-1] if content.strip() else "")
                letter = found[-1] if found else None
            else:
                found = [item for item in judge.letters(choice) if item[0] in PLACES]
                letter = found[0][0] if found else None
        except (OSError, ValueError, LookupError) as exc:  # a timeout counts as no answer
            content = f"error: {type(exc).__name__}"
        seconds = time.monotonic() - started
        rows.append({**frame, "said": PLACES.get(letter), "seconds": round(seconds, 3), "content": content[-120:]})
        seconds_all.append(seconds)
        if usage.get("completion_tokens"):
            tokens_all.append(usage["completion_tokens"])
    by_place = {}
    for place in (*PLACES.values(), "porch"):
        of = [row for row in rows if row["where"] == place]
        said = {name: sum(row["said"] == name for row in of) for name in (*PLACES.values(), None)}
        by_place[place] = {"n": len(of), "right": said.get(place), "said": {str(k): v for k, v in said.items() if v}}
    scored = [row for row in rows if row["where"] in PLACES.values()]  # the porch is asked, not scored
    result = {
        "model": args.model,
        "extra": extra,
        "think": args.think,
        "frames": len(scored),
        "right": sum(row["said"] == row["where"] for row in scored),
        "right_share": round(sum(row["said"] == row["where"] for row in scored) / max(1, len(scored)), 3),
        "by_place": by_place,
        "seconds": spread(seconds_all),
        "completion_tokens_median": statistics.median(tokens_all) if tokens_all else None,
        "rows": rows,
    }
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"scene-{slug(args.model, args.tag or '')}{'-think' if args.think else ''}.json"
    out.write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "rows"}))


def run_beside(args):
    """The fast model at the pilot's rate, alone and then with the big one answering picks beside it."""
    frames = sorted((ROOT / "lab" / "judge" / "sample").glob("*.jpg"))
    images = [judge.encode(cv2.imread(str(path)), 640) for path in frames[:: max(1, len(frames) // 40)]]
    picks = situations()
    fast_extra, big_extra = json.loads(args.fast_extra), json.loads(args.big_extra)

    def ask(model, image, text, tokens, extra, timeout):
        body = {
            "model": model,
            "temperature": 0,
            "max_tokens": tokens,
            "logprobs": True,
            "top_logprobs": 5,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image}"}},
                        {"type": "text", "text": text},
                    ],
                }
            ],
            **extra,
        }
        request = urllib.request.Request(
            args.url + "/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"}
        )
        started = time.monotonic()
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=timeout) as answer:
                json.load(answer)
        except (OSError, ValueError):
            return None
        return time.monotonic() - started

    def fast_loop(seconds, sink, late):
        end, index = time.monotonic() + seconds, 0
        period = 1.0 / args.rate
        while time.monotonic() < end:
            tick = time.monotonic()
            took = ask(args.fast, images[index % len(images)], judge.JOINT, 2 * len(judge.QUESTIONS) + 2, fast_extra, 1.0)
            (sink if took is not None else late).append(took if took is not None else 1.0)
            index += 1
            rest = period - (time.monotonic() - tick)
            if rest > 0:
                time.sleep(rest)

    alone, alone_late = [], []
    fast_loop(args.seconds, alone, alone_late)
    loaded, loaded_late, big = [], [], []
    stop = threading.Event()

    def big_loop():
        index = 0
        while not stop.is_set():
            _, _, text, image = picks[index % len(picks)]
            took = ask(args.big, image, text + args.big_suffix, args.big_tokens, big_extra, 60)
            if took is not None:
                big.append(took)
            index += 1

    worker = threading.Thread(target=big_loop, daemon=True)
    worker.start()
    fast_loop(args.seconds, loaded, loaded_late)
    stop.set()
    worker.join(timeout=70)
    result = {
        "fast": args.fast,
        "big": args.big,
        "rate_hz": args.rate,
        "seconds_each": args.seconds,
        "big_tokens": args.big_tokens,
        "fast_alone": spread(alone),
        "fast_alone_over_1s": len(alone_late),
        "fast_beside_big": spread(loaded),
        "fast_beside_big_over_1s": len(loaded_late),
        "big_beside_fast": spread(big),
    }
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"beside-{slug(args.fast)}+{slug(args.big, args.tag or '')}.json"
    out.write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result, indent=1))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="what", required=True)
    for name in ("judge", "chooser", "think", "scene"):
        one = sub.add_parser(name)
        one.add_argument("--url", required=True)
        one.add_argument("--model", required=True)
        one.add_argument("--extra", default="{}")
        one.add_argument("--tag", default="")
        if name == "chooser":
            one.add_argument("--timeout", type=float, default=1.5)
        if name == "scene":
            one.add_argument("--think", action="store_true")
            one.add_argument("--suffix", default=THINK, help="empty for a model that reasons by itself")
            one.add_argument("--tokens", type=int, default=400)
            one.add_argument("--each", type=int, default=0, help="at most this many frames of each place")
            one.add_argument("--cache", default=str(Path(__file__).with_name("cache")))
        if name == "think":
            one.add_argument("--limit", type=int, default=0, help="at most this many situations, evenly spread")
            one.add_argument("--tokens", type=int, default=400)
            one.add_argument(
                "--suffix",
                default=THINK,
                help="empty for a model that reasons by itself",
            )
    two = sub.add_parser("beside")
    two.add_argument("--url", required=True)
    two.add_argument("--fast", required=True)
    two.add_argument("--big", required=True)
    two.add_argument("--fast-extra", default="{}")
    two.add_argument("--big-extra", default="{}")
    two.add_argument("--big-tokens", type=int, default=2)
    two.add_argument("--big-suffix", default="")
    two.add_argument("--seconds", type=float, default=45)
    two.add_argument("--rate", type=float, default=4.0)
    two.add_argument("--tag", default="")
    args = parser.parse_args()
    runs = {"judge": run_judge, "chooser": run_chooser, "think": run_think, "scene": run_scene, "beside": run_beside}
    runs[args.what](args)


if __name__ == "__main__":
    main()
