"""Puts NitroGen's pad states beside Kerim's on stretches of his recordings (card P63).

    pilot/.venv/bin/python lab/policy/agree.py [--endpoint http://127.0.0.1:18790] [--drive 4] [--foot 3]
        [--fight 3] [--seconds 10] [--hz 5] [--steps 16] [--out lab/policy/agree.json]

The server of `serve.ps1` has to run with its port forwarded. Every sampled frame is squeezed to 256 by
256 as the repository's client does it and sent on; the chunk that comes back is 18 actions at 60 a
second, the first of them three steps after the frame, and each is compared with what Kerim's hand
held at that moment. Beside every score stands what one answer held for the whole time would get,
because a stretch in which he steers one way is matched by anything that steers that way. His pad and
the frames share the recorder's clock, and the model was trained on videos that show the pad of the
moment, so no lead is added; the stick is also scored with his hand shifted by fractions of a second,
which shows whether a wrong clock explains a poor score.
Recordings are read and never written.
"""

import argparse
import base64
import bisect
import http.client
import json
import math
import statistics
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

import cv2

RECORDINGS = Path("/Users/kerim/recordings/kerim")
LABELS = Path("/Users/kerim/recordings/derived/kerim")
# The labels that make a stretch one of a kind, and the share of it they have to cover. A fight is
# full of running and looking, so it counts from a lower share.
KINDS = {
    "drive": (("follow_route", "drive_free"), 0.8),
    "foot": (("walk", "sprint"), 0.8),
    "fight": (("aim", "fire"), 0.4),
}
NEUTRAL = {"buttons": [], "left": [0.0, 0.0], "right": [0.0, 0.0], "l2": 0.0, "r2": 0.0}
OFFSETS = (-0.3, -0.15, 0.0, 0.15, 0.3)
CLEAR = 0.5  # a stick of Kerim's that points somewhere on purpose
ALIVE = 0.25  # a stick of the model's that points anywhere at all


def lines(path):
    with path.open() as source:
        return [json.loads(line) for line in source if line.strip()]


def stretches(kind, count, seconds):
    """The `count` windows that the kind's labels cover best, one a recording."""
    names, share = KINDS[kind]
    found = []
    for labels in sorted(LABELS.glob("*/actions.jsonl")):
        recording = RECORDINGS / labels.parent.name
        if not all(
            (recording / name).exists()
            for name in ("video.mp4", "pad.jsonl", "frames.jsonl")
        ):
            continue
        rows = lines(labels)
        spans = [(row["start"], row["end"]) for row in rows if row["action"] in names]
        end = max((row["end"] for row in rows), default=0.0)
        best = None
        for start, _ in spans:
            begin = max(
                0.0, start - 1.0
            )  # a second early, so that a fight has its beginning
            if begin + seconds + 0.5 > end:
                continue
            covered = sum(
                max(0.0, min(e, begin + seconds) - max(s, begin)) for s, e in spans
            )
            if covered >= share * seconds and (best is None or covered > best[0]):
                best = (covered, begin)
        if best:
            found.append(
                {
                    "kind": kind,
                    "recording": recording.name,
                    "begin": round(best[1], 3),
                    "covered_s": round(best[0], 2),
                }
            )
    found.sort(key=lambda row: -row["covered_s"])
    return found[:count]


class Hand:
    """Kerim's pad at any moment: a state holds until the next one is logged."""

    def __init__(self, path):
        self.rows = [row for row in lines(path) if row.get("src", "human") == "human"]
        self.times = [row["t"] for row in self.rows]

    def at(self, t):
        index = bisect.bisect_right(self.times, t) - 1
        return self.rows[index] if index >= 0 else NEUTRAL


def sampled(recording, begin, seconds, hz):
    """Frames of the stretch, `hz` a second, with the time each was captured."""
    times = [row["t"] for row in lines(recording / "frames.jsonl")]
    wanted = sorted(
        {bisect.bisect_left(times, begin + k / hz) for k in range(int(seconds * hz))}
    )
    wanted = [index for index in wanted if index < len(times)]
    video = cv2.VideoCapture(str(recording / "video.mp4"))
    video.set(cv2.CAP_PROP_POS_FRAMES, wanted[0])
    position = wanted[0]
    for index in wanted:
        while position < index:
            video.grab()
            position += 1
        ok, bgr = video.read()
        position += 1
        if not ok:
            break
        yield times[index], bgr
    video.release()


def ask(connection, bgr, capture, steps):
    small = cv2.resize(bgr, (256, 256), interpolation=cv2.INTER_AREA)
    _, jpeg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 95])
    body = json.dumps(
        {
            "version": 1,
            "capture": capture,
            "image_jpeg_base64": base64.b64encode(jpeg).decode(),
            "steps": steps,
        }
    )
    began = time.perf_counter()
    connection.request("POST", "/policy", body, {"Content-Type": "application/json"})
    response = connection.getresponse()
    data = response.read()
    took = time.perf_counter() - began
    if response.status != 200:
        raise RuntimeError(f"the server answered {response.status}: {data[:200]!r}")
    return json.loads(data), took


def within(a, b, degrees=45.0):
    dot = a[0] * b[0] + a[1] * b[1]
    return (
        math.degrees(
            math.acos(max(-1.0, min(1.0, dot / (math.hypot(*a) * math.hypot(*b)))))
        )
        <= degrees
    )


def quiet(pad):
    sticks = math.hypot(*pad["left"]) <= ALIVE and math.hypot(*pad["right"]) <= ALIVE
    return sticks and not pad["buttons"] and pad["l2"] <= 0.5 and pad["r2"] <= 0.5


def compare(total, reply, hand, capture):
    chunk, rate, first = reply["chunk"], reply["rate_hz"], reply["first_step"]
    moments = [capture + (first + step) / rate for step in range(len(chunk))]
    for model, moment in zip(chunk, moments):
        for offset in OFFSETS:
            his = hand.at(moment + offset)["left"]
            if math.hypot(*his) > CLEAR:
                total[f"stick_clear@{offset}"] += 1
                if math.hypot(*model["left"]) > ALIVE and within(model["left"], his):
                    total[f"stick_within_45@{offset}"] += 1
        his = hand.at(moment)
        total["ticks"] += 1
        if math.hypot(*his["left"]) > CLEAR:
            total[
                f"kerim_points_{round(math.degrees(math.atan2(his['left'][1], his['left'][0])) / 22.5) % 16}"
            ] += 1
        if abs(his["left"][0]) > 0.3:
            total[
                "kerim_steers_right" if his["left"][0] > 0 else "kerim_steers_left"
            ] += 1
        total["model_quiet"] += quiet(model)
        total["kerim_quiet"] += quiet(his)
        if math.hypot(*his["left"]) > CLEAR and math.hypot(*model["left"]) <= ALIVE:
            total["stick_idle"] += 1
        if abs(his["left"][0]) > 0.3:
            total["steer_clear"] += 1
            total["steer_same_side"] += (
                abs(model["left"][0]) > 0.1 and model["left"][0] * his["left"][0] > 0
            )
            # counted apart from a stick at rest: a mirrored axis would show as mostly the other side
            total["steer_other_side"] += (
                abs(model["left"][0]) > 0.1 and model["left"][0] * his["left"][0] < 0
            )
            total[
                "model_x_while_he_steers_right"
                if his["left"][0] > 0
                else "model_x_while_he_steers_left"
            ] += model["left"][0]
        for trigger in ("l2", "r2"):
            total[f"{trigger}_kerim"] += his[trigger] > 0.5
            total[f"{trigger}_model"] += model[trigger] > 0.5
            total[f"{trigger}_both"] += his[trigger] > 0.5 and model[trigger] > 0.5
        for button in model["buttons"]:
            total[f"model_presses_{button}"] += 1
        for button in his["buttons"]:
            total[f"kerim_presses_{button}"] += 1
    # One steering moment a frame, as the plan counts them: Kerim steers clearly over the chunk's
    # third of a second, and the model's mean stick is on the same side.
    his_x = statistics.fmean(hand.at(moment)["left"][0] for moment in moments)
    model_x = statistics.fmean(model["left"][0] for model in chunk)
    if abs(his_x) > CLEAR:
        total["steering_moments"] += 1
        total["moments_right" if his_x > 0 else "moments_left"] += 1
        total["steering_moments_same_side"] += (
            abs(model_x) > 0.1 and model_x * his_x > 0
        )
        total["steering_moments_other_side"] += (
            abs(model_x) > 0.1 and model_x * his_x < 0
        )


def fixed(total):
    """What one answer held for the whole stretch would score: the bar the model has to clear."""
    points = [total[f"kerim_points_{sector}"] for sector in range(16)]
    # a fixed direction is within 45 degrees of his in its own sector of 22.5 degrees and two each side
    stick = max(
        sum(points[(sector + step) % 16] for step in range(-2, 3))
        for sector in range(16)
    )
    return {
        "stick": f"{stick} of {sum(points)}" if sum(points) else "none to count",
        "steer": f"{max(total['kerim_steers_left'], total['kerim_steers_right'])} of {total['steer_clear']}",
        "moments": f"{max(total['moments_left'], total['moments_right'])} of {total['steering_moments']}",
    }


def share(total, part, whole):
    return (
        f"{total[part]} of {total[whole]} ({100 * total[part] / total[whole]:.0f}%)"
        if total[whole]
        else "none to count"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--endpoint", default="http://127.0.0.1:18790")
    parser.add_argument("--drive", type=int, default=4)
    parser.add_argument("--foot", type=int, default=3)
    parser.add_argument("--fight", type=int, default=3)
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--hz", type=float, default=5.0)
    parser.add_argument("--steps", type=int, default=16, choices=(4, 8, 16))
    parser.add_argument(
        "--out", type=Path, default=Path(__file__).with_name("agree.json")
    )
    args = parser.parse_args()

    address = urlparse(args.endpoint)
    connection = http.client.HTTPConnection(address.hostname, address.port, timeout=30)
    connection.request("GET", "/info")
    info = json.loads(connection.getresponse().read())
    print("server:", info)

    chosen = [
        row
        for kind in KINDS
        for row in stretches(kind, getattr(args, kind), args.seconds)
    ]
    totals = {kind: Counter() for kind in KINDS}
    round_trips, server_seconds = [], []
    for row in chosen:
        recording = RECORDINGS / row["recording"]
        hand = Hand(recording / "pad.jsonl")
        frames = 0
        for capture, bgr in sampled(recording, row["begin"], args.seconds, args.hz):
            reply, took = ask(connection, bgr, capture, args.steps)
            round_trips.append(took)
            server_seconds.append(reply["seconds"])
            compare(totals[row["kind"]], reply, hand, capture)
            frames += 1
        row["frames"] = frames
        print(
            f"{row['kind']:5} {row['recording']} from {row['begin']:.1f} s: {frames} frames"
        )
    connection.close()

    ordered = sorted(round_trips)
    timing = {
        "requests": len(ordered),
        "round_trip_median_ms": round(1000 * statistics.median(ordered), 1),
        "round_trip_p90_ms": round(1000 * ordered[int(0.9 * len(ordered))], 1),
        "round_trip_worst_ms": round(1000 * ordered[-1], 1),
        "server_median_ms": round(1000 * statistics.median(server_seconds), 1),
    }
    print("\nfrom this Mac through the forwarded port:", timing)
    for kind, total in totals.items():
        if not total["ticks"]:
            continue
        bar = fixed(total)
        print(f"\n{kind}: {total['ticks']} ticks")
        print(
            f"  the left stick within 45 degrees of Kerim's clear stick: {share(total, 'stick_within_45@0.0', 'stick_clear@0.0')}; one fixed direction gets {bar['stick']}"
        )
        print(
            f"  the model's stick at rest while his is clear: {share(total, 'stick_idle', 'stick_clear@0.0')}"
        )
        print(
            "  the same with his hand shifted: "
            + ", ".join(
                f"{offset:+.2f} s {share(total, f'stick_within_45@{offset}', f'stick_clear@{offset}')}"
                for offset in OFFSETS
                if offset
            )
        )
        print(
            f"  steering to the same side where he steers: {share(total, 'steer_same_side', 'steer_clear')}; one fixed side gets {bar['steer']}"
        )
        print(
            f"  clear steering moments on the same side: {share(total, 'steering_moments_same_side', 'steering_moments')}; one fixed side gets {bar['moments']}"
        )
        print(
            f"  to the other side: {share(total, 'steer_other_side', 'steer_clear')} of the ticks and {share(total, 'steering_moments_other_side', 'steering_moments')} of the moments; "
            f"the model's mean x is {total['model_x_while_he_steers_left'] / max(total['kerim_steers_left'], 1):+.2f} while he steers left ({total['kerim_steers_left']} ticks) "
            f"and {total['model_x_while_he_steers_right'] / max(total['kerim_steers_right'], 1):+.2f} while he steers right ({total['kerim_steers_right']} ticks)"
        )
        for trigger, meaning in (("l2", "aim or brake"), ("r2", "fire or throttle")):
            print(
                f"  {trigger} ({meaning}): the model holds it on {share(total, f'{trigger}_both', f'{trigger}_kerim')} of his ticks, and he holds it on {share(total, f'{trigger}_both', f'{trigger}_model')} of the model's"
            )
        print(
            f"  nothing pressed at all: the model on {share(total, 'model_quiet', 'ticks')}, Kerim on {share(total, 'kerim_quiet', 'ticks')}"
        )
        pressed = {
            key.removeprefix("model_presses_"): count
            for key, count in total.items()
            if key.startswith("model_presses_")
        }
        print(f"  buttons the model presses, in ticks: {pressed or 'none'}")
    args.out.write_text(
        json.dumps(
            {
                "server": info,
                "steps": args.steps,
                "hz": args.hz,
                "seconds": args.seconds,
                "stretches": chosen,
                "timing": timing,
                "totals": totals,
                "fixed": {kind: fixed(total) for kind, total in totals.items()},
            },
            indent=1,
        )
        + "\n"
    )
    print(f"\nwritten to {args.out}")


if __name__ == "__main__":
    main()
