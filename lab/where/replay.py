"""Offline shadow replay. No pad is sent and recorded motion cannot follow decisions."""

import argparse
import bisect
import json
import subprocess
import sys
import types
from dataclasses import asdict, fields
from pathlib import Path

import cv2

from measure import HERE, ROOT, frame, prepare

sys.path.insert(0, str(ROOT / "pilot/src"))

SOURCE = Path("/Users/kerim/recordings/pilot/20261112-143714")


def ticks():
    return [
        r
        for r in map(json.loads, (SOURCE / "play.jsonl").read_text().splitlines())
        if r.get("skill", {}).get("name") == "enter_vehicle"
    ]


def detect():
    from pilot.objects import Detector

    detector = Detector()
    rows, seen = [], set()
    for tick in ticks():
        bucket = int(tick["t"] * 4)
        if bucket in seen:
            continue
        seen.add(bucket)
        bgr = frame(SOURCE, tick["t"])
        objects = detector.detect(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        rows.append({"t": tick["t"], "objects": [asdict(obj) for obj in objects]})
    (HERE / "replay-detections.json").write_text(
        json.dumps(rows, separators=(",", ":")) + "\n"
    )
    print(
        f"Recomputed {len(rows)} detector captures for {len(ticks())} recorded ticks; original detections are absent"
    )


def judge():
    from pilot.judge import ask_where, encode, parse_where

    target = HERE / "replay-answers.jsonl"
    done = set()
    if target.exists():
        done = {r["t"] for r in map(json.loads, target.read_text().splitlines())}
    rows = json.loads((HERE / "replay-detections.json").read_text())
    with target.open("a") as out:
        for index, row in enumerate(rows):
            if row["t"] in done:
                continue
            item = {"t": row["t"]}
            request = {"source": str(SOURCE), "seconds": row["t"]}
            image = encode(prepare(request, False), 640)
            choice, duration = ask_where(
                "http://192.168.0.248:1234", "qwen/qwen3-vl-8b", image, timeout=15
            )
            item["where"] = asdict(parse_where(choice, row["t"], duration, "pc"))
            vehicles = [
                o
                for o in row["objects"]
                if o["kind"] in {"car", "truck", "bus", "motorcycle"}
            ]
            if vehicles:
                obj = max(
                    vehicles,
                    key=lambda o: o["box"][3] + (o["box"][3] - o["box"][1]) * 0.5,
                )
                request["box"] = [
                    v / d for v, d in zip(obj["box"], (1280, 720, 1280, 720))
                ]
                choice, duration = ask_where(
                    "http://192.168.0.248:1234",
                    "qwen/qwen3-vl-8b",
                    encode(prepare(request, False), 640),
                    ("vehicle",),
                    timeout=15,
                )
                item["vehicle"] = asdict(
                    parse_where(choice, row["t"], duration, "pc", ("vehicle",))
                )
                item["box"] = obj["box"]
            out.write(json.dumps(item, separators=(",", ":")) + "\n")
            out.flush()
            if index % 20 == 0:
                print(f"Replay judge {index}/{len(rows)}", flush=True)


def replay():
    from pilot.contract import Answer, Detection, Judgment, Observation, Reading
    from pilot.vehicle_entry import EnterVehicle

    detections = json.loads((HERE / "replay-detections.json").read_text())
    answers = list(
        map(json.loads, (HERE / "replay-answers.jsonl").read_text().splitlines())
    )
    times = [r["t"] for r in detections]
    # Emulate arrival after measured request duration, not at image capture time.
    arrivals = sorted((r["t"] + r["where"]["duration"], r) for r in answers)
    arrival_times = [a[0] for a in arrivals]
    allowed = {f.name for f in fields(Reading)}
    # Compare both implementations on identical reconstructed observations.
    module = types.ModuleType("pilot._p60_before_entry")
    sys.modules[module.__name__] = module
    source = subprocess.check_output(
        ["git", "show", "HEAD:pilot/src/pilot/vehicle_entry.py"], cwd=ROOT, text=True
    )
    exec(compile(source, "HEAD:vehicle_entry.py", "exec"), module.__dict__)
    baseline = module.EnterVehicle({"duration": 40})
    skill = EnterVehicle({"duration": 40})
    count = 0
    with (HERE / "replay-ticks.jsonl").open("w") as out:
        for tick in ticks():
            t = tick["t"]
            d = detections[max(0, bisect.bisect_right(times, t) - 1)]
            index = bisect.bisect_right(arrival_times, t) - 1
            evidence = None if index < 0 else arrivals[index][1]
            judgment = None
            advisory = "missing eye"
            age = None
            if evidence:
                j = evidence["where"]
                age = t - j["capture"]
                judgment = Judgment(
                    j["capture"],
                    {k: Answer(**v) for k, v in j["answers"].items()},
                    j["probabilities"],
                    j["duration"],
                    j["server"],
                )
                where = j["answers"]["where"]["value"]
                edge = j["answers"]["edge"]["value"]
                advisory = (
                    f"unqualified {where}; edge={edge}" if age <= 1.5 else "stale eye"
                )
            observation = Observation(
                Reading(**{k: v for k, v in tick["reading"].items() if k in allowed}),
                None,
                t,
                frame=cv2.cvtColor(frame(SOURCE, t), cv2.COLOR_BGR2RGB),
                objects=tuple(
                    Detection(o["kind"], tuple(o["box"]), o["confidence"])
                    for o in d["objects"]
                ),
                objects_time=d["t"],
                judgment=judgment,
            )
            result = skill.step(observation)
            before = baseline.step(observation)
            recorded = tick.get("result", {})
            simulated = asdict(result)
            changed = json.dumps(simulated.get("pad"), sort_keys=True) != json.dumps(
                recorded.get("pad"), sort_keys=True
            ) or result.status != recorded.get("status")
            policy_changed = result.pad != before.pad or result.status != before.status
            out.write(
                json.dumps(
                    {
                        "t": t,
                        "capture": d["t"],
                        "judge_age": age,
                        "advisory": advisory,
                        "recorded": recorded,
                        "shadow": simulated,
                        "different_from_recording": changed,
                        "policy_changed_from_HEAD": policy_changed,
                        "reason_changed_from_HEAD": result.reason != before.reason,
                        "roadside_wiring": False,
                    },
                    separators=(",", ":"),
                )
                + "\n"
            )
            count += 1
    print(
        f"Wrote {count} shadow ticks; fresh recomputed boxes, measured judge arrival, no changed recorded motion"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["detect", "judge", "replay"])
    args = parser.parse_args()
    {"detect": detect, "judge": judge, "replay": replay}[args.action]()
