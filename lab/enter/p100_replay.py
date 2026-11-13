"""Open-loop entry commands on P100 observations; the recorded world never answers them."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from pilot.contract import Answer, Blip, Detection, Judgment, Observation, Reading
from pilot.vehicle_entry import EnterVehicle

OUT = Path(__file__).parent


def observation(sample):
    row = sample["play"]
    reading = dict(row["reading"])
    reading["blips"] = tuple(Blip(**b) for b in reading.get("blips", []))
    judgment = sample["judge"]
    mode = None
    if judgment is not None:
        origin = sample["judge_origin"]
        capture = judgment["capture"] - origin
        mode = judgment.get("mode") if row["t"] - capture <= 1.5 else None
        judgment = Judgment(
            capture,
            {k: Answer(**v) for k, v in judgment["answers"].items()},
            judgment["probabilities"],
            judgment["duration"],
            judgment["server"],
        )
    return Observation(
        Reading(**reading),
        None,
        row["t"],
        objects=tuple(Detection(**d) for d in sample["objects"]),
        objects_time=row["t"],
        mode=mode,
        judgment=judgment,
        figure=Detection(**sample["figure"]) if sample["figure"] else None,
        figure_vehicle=Detection(**sample["figure_vehicle"])
        if sample["figure_vehicle"]
        else None,
    )


def replay(run, frames=False):
    from dataclasses import replace

    skill = EnterVehicle({"duration": 25, "kind": "car", "occupied": "allow"})
    video = None
    if frames:
        import cv2

        cv2.setNumThreads(1)
        video = cv2.VideoCapture(
            str(Path("/Users/kerim/recordings/pilot") / run["session"] / "video.mp4")
        )
    ticks = []
    for sample in run["samples"]:
        obs = observation(sample)
        if video is not None:
            video.set(cv2.CAP_PROP_POS_FRAMES, sample["video_frame"])
            ok, bgr = video.read()
            if not ok:
                raise RuntimeError(sample["video_frame"])
            obs = replace(obs, frame=cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        result = skill.step(obs)
        target = skill.target
        ticks.append(
            {
                "t": obs.time,
                "frame": sample["video_frame"],
                "result": asdict(result),
                "target": next(
                    (i + 1 for i, v in enumerate(skill.ever) if v is target), None
                ),
                "target_box": target.obj.box if target else None,
                "target_motion": target.motion if target else None,
                "phase": skill.phase,
            }
        )
    if video is not None:
        video.release()
    return {"session": run["session"], "attempt": run["attempt"], "ticks": ticks}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", action="store_true")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    data = json.loads((OUT / "p100-recorded.json").read_text())
    runs = [replay(run, args.frames) for run in data["runs"]]
    (OUT / args.output).write_text(
        json.dumps(
            {"scope": data["scope"], "frames": args.frames, "runs": runs}, indent=2
        )
        + "\n"
    )
    for run in runs:
        ticks = run["ticks"]
        presses = [t["t"] for t in ticks if "triangle" in t["result"]["pad"]["buttons"]]
        running = sum("cross" in t["result"]["pad"]["buttons"] for t in ticks)
        print(
            run["session"],
            run["attempt"],
            "presses",
            presses,
            "run ticks",
            running,
            "last",
            ticks[-1]["result"]["status"],
            ticks[-1]["result"]["reason"],
        )
