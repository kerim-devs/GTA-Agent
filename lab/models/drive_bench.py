"""Ask one model the driving decisions of lab/models/drive-set.json, in several ways of asking.

    pilot/.venv/bin/python lab/models/drive_bench.py run --url URL --model ID [--extra JSON] [--ways a,b]
    pilot/.venv/bin/python lab/models/drive_bench.py par --url URL --model ID [--extra JSON]
    pilot/.venv/bin/python lab/models/drive_bench.py table

The ways of asking:

`pic`    one picture, two questions: the pedal for the next second (keep driving, lift off, brake)
         and the lane (stay, pass left, pass right)
`two`    the same with the picture of half a second before it as well
`state`  one picture and, as text, the speed and the route as the pilot read them and what its
         detector sees ahead, with how that changed in half a second
`focus`  one picture, the same text, and the one question a specialist would be asked: is there
         something in my path that I hit unless I slow down
`think`  as `state`, with one sentence on what is ahead before the letters (every third item)

`par` asks three focused questions at once of the one model, forty times, and times the slowest of
the three: what several specialists on the one card would cost.

Right and wrong, by what the picture or Kerim's hand says: before a standing or crossing vehicle,
and where Kerim braked or lifted, keeping the pedal down is a miss; where there is nothing in the
path, an oncoming vehicle or one beside the lane, and where Kerim held the pedal, braking is a
needless brake and lifting a needless lift; behind a slower vehicle braking is too much.

While it runs it writes live.json beside the pictures, which live.html there shows; every answer is
kept in results/<model>.jsonl there, and the table in lab/models/results/drive-<model>.json.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import statistics
import sys
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = Path("/Users/kerim/recordings/derived/drive-bench")
ITEMS = json.loads((HERE / "drive-set.json").read_text()) if (HERE / "drive-set.json").exists() else []

SYSTEM = (
    "You are the driver of the car seen from behind in the middle of a screenshot of Grand Theft Auto V. "
    "You follow the purple route line on the small map at the bottom left. Drive like a calm, skilled "
    "human: keep moving, slow down only for a real reason, and never hit anything."
)
JOINT = (
    "1. The pedal for the next second?\nA: keep driving\nB: lift off the accelerator\nC: brake\n"
    "2. The lane?\nA: stay\nB: move left to pass\nC: move right to pass\n\n"
)
LETTERS = "Reply with one letter per question, separated by a single space, and nothing else."
FOCUS = (
    "Is there a vehicle, a person or an obstacle in your own path that you hit unless you slow down "
    "within the next two seconds?\nA: no, the way is free, keep driving\n"
    "B: something is ahead but far or moving away, lifting off is enough\nC: yes, brake now\n\n"
    "Reply with the letter only."
)
LANE = (
    "Is your own lane blocked by something that stands or crawls, with free road beside it?\n"
    "A: no, stay in the lane\nB: yes, pass on the left\nC: yes, pass on the right\n\nReply with the letter only."
)
TURN = (
    "By the purple line on the small map at the bottom left: does your route turn within the next "
    "few car lengths?\nA: no, it goes on ahead\nB: it turns left\nC: it turns right\n\nReply with the letter only."
)
WAYS = ("pic", "two", "state", "focus", "think")
RISK = {"standing", "crossing", "brake", "lift"}
FREE = {"nothing", "oncoming", "beside", "clear", "cruise"}


def slug(model, tag=""):
    return re.sub(r"[^a-z0-9.]+", "-", model.lower()).strip("-") + tag


def instruments(item):
    lines = []
    if item["speed"] is not None:
        lines.append(f"- Speed: {item['speed']:.0f} m/s ({item['speed'] * 3.6:.0f} km/h)")
    if item["route"]:
        lines.append(f"- Route: {item['route']}")
    lines.append("- Seen ahead: " + ("; ".join(item["things"]) if item["things"] else "no vehicle or person"))
    return "What the car's instruments say:\n" + "\n".join(lines) + "\n\n"


def picture(name):
    return (OUT / f"{name}.b64").read_text()


def question(item, way):
    """(pictures, text, most tokens) for one way of asking."""
    now = picture(item["id"])
    if way == "pic":
        return [now], JOINT + LETTERS, 6
    if way == "two":
        note = "The first picture was taken half a second before the second. Decide for the second.\n\n"
        return [picture(item["id"] + "-before"), now], note + JOINT + LETTERS, 6
    if way == "state":
        return [now], instruments(item) + JOINT + LETTERS, 6
    if way == "focus":
        return [now], instruments(item) + FOCUS, 4
    if way == "think":
        ask = "First write one short sentence on what is in your path. Then, on a new line, one letter per question separated by a single space."
        return [now], instruments(item) + JOINT + ask, 60
    raise ValueError(way)


def post(url, model, pictures, text, tokens, extra, timeout=60):
    content = [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{p}"}} for p in pictures]
    body = {
        "model": model,
        "temperature": 0,
        "max_tokens": tokens,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": content + [{"type": "text", "text": text}]},
        ],
        **extra,
    }
    request = urllib.request.Request(
        url + "/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"}
    )
    started = time.perf_counter()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        data = json.load(response)
    return (data["choices"][0]["message"].get("content") or "").strip(), time.perf_counter() - started


def letters(answer, way):
    found = re.findall(r"\b([ABC])\b", answer.splitlines()[-1] if way == "think" and answer else answer)
    if not found:
        return None, None
    return found[0], (found[1] if len(found) > 1 else None)


def verdict(label, pedal):
    if pedal is None:
        return "unread"
    if label in RISK:
        return "miss" if pedal == "A" else "right"
    if label in FREE:
        return "needless brake" if pedal == "C" else "needless lift" if pedal == "B" else "right"
    return "too much" if pedal == "C" else "right"  # behind a slower vehicle


WORDS = {"A": "keep driving", "B": "lift off", "C": "brake", None: "?"}
LANES = {"A": "stay", "B": "pass left", "C": "pass right", None: ""}


def tally(rows):
    out = {}
    for way in WAYS:
        mine = [r for r in rows if r["way"] == way]
        if not mine:
            continue
        risk = [r for r in mine if r["label"] in RISK]
        free = [r for r in mine if r["label"] in FREE]
        slow = [r for r in mine if r["label"] == "slower"]
        seconds = sorted(r["seconds"] for r in mine)
        share = lambda part, name: None if not part else round(sum(r["verdict"] == name for r in part) / len(part), 3)  # noqa: E731
        out[way] = {
            "asked": len(mine),
            "right": share(mine, "right"),
            "missed of what asks for slowing": share(risk, "miss"),
            "needless brake where the way is free": share(free, "needless brake"),
            "needless lift where the way is free": share(free, "needless lift"),
            "brake behind a slower vehicle": share(slow, "too much"),
            "unread": share(mine, "unread"),
            "median seconds": round(statistics.median(seconds), 3),
            "p90 seconds": round(seconds[int(len(seconds) * 0.9)], 3),
        }
    return out


def jpegs():
    for item in ITEMS:
        for name in (item["id"], item["id"] + "-before"):
            target = OUT / f"{name}.jpg"
            if not target.exists():
                target.write_bytes(base64.b64decode(picture(name)))


def run(args):
    extra = json.loads(args.extra) if args.extra else {}
    ways = args.ways.split(",") if args.ways else list(WAYS)
    jpegs()
    (OUT / "results").mkdir(exist_ok=True)
    log = OUT / "results" / f"{slug(args.model)}.jsonl"
    rows = [json.loads(line) for line in log.open()] if log.exists() else []
    done = {(r["id"], r["way"]) for r in rows}
    plan = [(way, item) for way in ways for n, item in enumerate(ITEMS) if way != "think" or n % 3 == 0]
    recent = []
    with log.open("a") as out:
        for count, (way, item) in enumerate(plan, 1):
            if (item["id"], way) in done:
                continue
            pictures, text, tokens = question(item, way)
            try:
                answer, seconds = post(args.url, args.model, pictures, text, tokens, extra)
            except Exception as error:  # a timeout is an answer the pilot would not have had
                answer, seconds = f"error: {error!r}"[:120], 60.0
            pedal, lane = letters(answer, way)
            row = {
                "id": item["id"],
                "way": way,
                "label": item["label"],
                "source": item["source"],
                "answer": answer,
                "pedal": pedal,
                "lane": lane,
                "verdict": verdict(item["label"], pedal),
                "seconds": round(seconds, 3),
            }
            rows.append(row)
            out.write(json.dumps(row) + "\n")
            out.flush()
            recent = (recent + [row])[-10:]
            live = {
                "model": args.model,
                "way": way,
                "progress": f"{count} of {len(plan)}",
                "item": item,
                "two": way == "two",
                "text": text,
                "row": row,
                "says": WORDS[pedal] + (", " + LANES[lane] if lane else ""),
                "recent": recent,
                "tally": tally(rows),
                "finished": [p.stem for p in sorted((OUT / "results").glob("*.jsonl"))],
            }
            (OUT / "live.tmp").write_text(json.dumps(live))
            (OUT / "live.tmp").replace(OUT / "live.json")
            if args.pace:
                time.sleep(max(0.0, args.pace - seconds))
    summary = {"model": args.model, "extra": extra, "items": len(ITEMS), "ways": tally(rows)}
    (HERE / "results" / f"drive-{slug(args.model)}.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary["ways"], indent=1))


def par(args):
    extra = json.loads(args.extra) if args.extra else {}
    walls, singles = [], []
    for item in ITEMS[::8][:40]:
        now = picture(item["id"])
        took = [0.0, 0.0, 0.0]

        def ask(k, text, now=now, item=item, took=took):
            took[k] = post(args.url, args.model, [now], instruments(item) + text, 4, extra)[1]

        threads = [threading.Thread(target=ask, args=(k, text)) for k, text in enumerate((FOCUS, LANE, TURN))]
        started = time.perf_counter()
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        walls.append(time.perf_counter() - started)
        singles.append(post(args.url, args.model, [now], instruments(item) + FOCUS, 4, extra)[1])
    walls.sort()
    singles.sort()
    result = {
        "model": args.model,
        "three at once, median seconds": round(statistics.median(walls), 3),
        "three at once, p90 seconds": round(walls[int(len(walls) * 0.9)], 3),
        "one alone, median seconds": round(statistics.median(singles), 3),
    }
    (HERE / "results" / f"drive-par-{slug(args.model)}.json").write_text(json.dumps(result, indent=1))
    print(json.dumps(result))


def table(_args):
    for path in sorted((HERE / "results").glob("drive-*.json")):
        data = json.loads(path.read_text())
        if "ways" not in data:
            print(json.dumps(data))
            continue
        for way, row in data["ways"].items():
            print(
                f"{data['model']:24s} {way:6s} right {row['right']:.2f}  missed {row['missed of what asks for slowing']:.2f}"
                f"  needless brake {row['needless brake where the way is free']:.2f}"
                f"  needless lift {row['needless lift where the way is free']:.2f}"
                f"  brake behind slower {row['brake behind a slower vehicle']}"
                f"  {row['median seconds']:.2f}s (p90 {row['p90 seconds']:.2f})"
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for name, call in (("run", run), ("par", par), ("table", table)):
        one = sub.add_parser(name)
        one.set_defaults(call=call)
        if name != "table":
            one.add_argument("--url", required=True)
            one.add_argument("--model", required=True)
            one.add_argument("--extra")
        if name == "run":
            one.add_argument("--ways")
            one.add_argument("--pace", type=float, default=0.0, help="least seconds an item stays on the live page")
    arguments = parser.parse_args()
    arguments.call(arguments)
