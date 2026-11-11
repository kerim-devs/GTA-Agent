"""Join OCR intervals to P38 sections and compare observation-only mission rules."""

import argparse
import json
from bisect import bisect_right
from dataclasses import asdict
from pathlib import Path

import cv2

from pilot import hud
from pilot.conductor import minimap_crop
from pilot.head import HeadRequest
from pilot.loop import Pipeline
from pilot.mission import MissionHead
from pilot.notes import build_missions, observed_actions, read_sections
from pilot.scene import SceneText, TextLine


def jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def compare(recording, readings, sections, missions, pads):
    frames = jsonl(recording / "frames.jsonl")
    times = [frame["t"] for frame in frames]
    readings = sorted(readings, key=lambda row: row["t"])
    text_times = [row["t"] for row in readings]
    capture = cv2.VideoCapture(str(recording / "video.mp4"))
    cases = []
    try:
        for mission in missions["missions"]:
            for step in mission["steps"]:
                target = min(step["start"] + 3, (step["start"] + step["end"]) / 2)
                frame = frames[max(0, bisect_right(times, target) - 1)]
                timestamp = frame["t"]
                capture.set(cv2.CAP_PROP_POS_FRAMES, frame["i"])
                ok, image = capture.read()
                if not ok:
                    raise RuntimeError(f"Cannot read frame {frame['i']} from {recording}")
                rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                text_index = bisect_right(text_times, timestamp) - 1
                if text_index < 0 or timestamp - text_times[text_index] > 1:
                    scene = SceneText()
                else:
                    raw = readings[text_index]["text"]
                    scene = SceneText(**{**raw, "lines": tuple(TextLine(**line) for line in raw["lines"])})
                pipeline = Pipeline()
                try:
                    minimap, _, _ = pipeline.step(minimap_crop(rgb), timestamp, feedback=False)
                finally:
                    pipeline.close()
                request = HeadRequest(
                    events=[],
                    help=scene.help,
                    objective=scene.objective,
                    subtitle=scene.subtitle,
                    banner=scene.banner,
                    minimap=asdict(minimap),
                    hud=asdict(hud.read(rgb, text=scene)),
                    last_skill=None,
                    notebook="",
                    jpeg_path="",
                    objects=[],
                )
                step["sample_observation"] = {
                    "t": timestamp,
                    "route": request.minimap["route"],
                    "blips": request.minimap["blips"],
                }
                head = MissionHead()
                response = head.decide(request)
                skill = response.plan[0].name if response.plan else None
                human = observed_actions(
                    pads, sections["sections"], timestamp, min(timestamp + 3, step["end"])
                )
                category = classify(skill, head.last_rule, human)
                cases.append(
                    {
                        "objective": step["objective"],
                        "step_start": step["start"],
                        "sample_t": timestamp,
                        "frame": frame["i"],
                        "request": asdict(request),
                        "rule": head.last_rule,
                        "first_skill": skill,
                        "human": human,
                        "result": category,
                    }
                )
    finally:
        capture.release()
    return cases


def classify(skill, rule, human):
    if rule == "moving_default":
        return "model-delegated"
    if human is None:
        return "unknown"
    seconds = human["seconds"]
    expected = {
        "walk": ("walking", "running"),
        "walk_to": ("walking", "running"),
        "drive_route": ("driving",),
        "set_waypoint": ("map_input",),
        "enter_vehicle": ("vehicle_input",),
        "look": ("looking",),
        "wait": ("neutral",),
    }.get(skill)
    if expected is None:
        return "unknown"
    return "matching" if any(seconds.get(key, 0) > 0 for key in expected) else "different"


def write_cases(path, cases):
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ")

    lines = [
        "Rules-only observations from one frame per objective step. Controller actions describe the "
        "following three seconds; Wi-Fi input may lead the picture by 0.6 to 1.1 seconds. Unknown means "
        "the recording cannot establish a comparable action. Matching checks compatible input, "
        "not successful skill completion.",
        "",
        "| Time | Game objective | First skill | Rule | Human action | Result |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for case in cases:
        human = case["human"]
        action = (
            ", ".join(key for key, value in human["seconds"].items() if value > 0) if human else "unknown"
        )
        lines.append(
            "| "
            + " | ".join(
                cell(value)
                for value in (
                    f"{case['sample_t']:.3f}",
                    case["objective"],
                    case["first_skill"],
                    case["rule"],
                    action or "no active input observed",
                    case["result"],
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "Totals: "
            + ", ".join(
                f"{sum(case['result'] == kind for case in cases)} {kind}"
                for kind in ("matching", "different", "model-delegated", "unknown")
            )
            + ".",
            "",
        ]
    )
    path.write_text("\n".join(lines))


def write_summary(path, directories):
    """One page over several recordings: every mission with its steps, and the table of cases."""
    kinds = ("matching", "different", "model-delegated", "unknown")
    lines = ["Missions and cases of the recordings below, as written by mission_notes.py for each.", ""]
    totals = {kind: 0 for kind in kinds}
    table = []
    for directory in directories:
        missions = json.loads((directory / "missions.json").read_text())
        cases = json.loads((directory / "cases.json").read_text())
        counts = {kind: sum(case["result"] == kind for case in cases) for kind in kinds}
        for kind in kinds:
            totals[kind] += counts[kind]
        table.append((directory.name, len(missions["missions"]), len(cases), counts))
        lines.append(f"## {directory.name}")
        lines.append("")
        if not missions["missions"]:
            lines.extend(["No objective was read in this recording.", ""])
        for number, mission in enumerate(missions["missions"], 1):
            reason = mission.get("end_reason", "next objective")
            lines.append(
                f"Mission {number}, {mission['start']:.0f} to {mission['end']:.0f} s, "
                f"{len(mission['steps'])} steps, ended by {reason} ({mission['ending']})."
            )
            lines.append("")
            for step in mission["steps"]:
                lines.append(
                    f"{step['start']:.1f} s, read for {step['duration']:.1f} s, {step['ending']}: "
                    f"{step['objective']}"
                )
                lines.append("")
    lines.extend(
        [
            "## Cases",
            "",
            "| Recording | Missions | Steps | Matching | Different | Left to the model | Unknown |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for name, count, steps, counts in table:
        lines.append(
            f"| {name} | {count} | {steps} | " + " | ".join(str(counts[kind]) for kind in kinds) + " |"
        )
    missions_total = sum(row[1] for row in table)
    steps_total = sum(row[2] for row in table)
    lines.append(
        f"| all | {missions_total} | {steps_total} | "
        + " | ".join(str(totals[kind]) for kind in kinds)
        + " |"
    )
    lines.append("")
    path.write_text("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path, nargs="?")
    parser.add_argument("--texts", type=Path)
    parser.add_argument("--sections", type=Path)
    parser.add_argument(
        "--summary",
        type=Path,
        help="Write one summary file over the output folders given with --dirs instead of one recording",
    )
    parser.add_argument("--dirs", type=Path, nargs="+")
    parser.add_argument(
        "--readings", type=Path, help="Raw OCR cache; defaults to texts' sibling readings.jsonl"
    )
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.summary:
        if not args.dirs:
            parser.error("--summary needs --dirs")
        try:
            write_summary(args.summary, args.dirs)
        except (FileNotFoundError, ValueError) as error:
            parser.exit(1, f"Mission notes failed: {error}\n")
        return
    if not (args.recording and args.texts and args.sections and args.out):
        parser.error("recording, --texts, --sections and --out are required")
    try:
        sections = read_sections(args.sections)
        if Path(sections["recording"]).name != args.recording.name:
            raise ValueError("Sections belong to a different recording")
        readings = jsonl(args.readings or args.texts.with_name("readings.jsonl"))
        pad_path = args.recording / "pad.jsonl"
        pads = jsonl(pad_path) if pad_path.is_file() else []
        missions = build_missions(jsonl(args.texts), sections, pads)
        cases = compare(args.recording, readings, sections, missions, pads)
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "missions.json").write_text(json.dumps(missions, ensure_ascii=False, indent=2) + "\n")
        (args.out / "cases.json").write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n")
        write_cases(args.out / "cases.md", cases)
    except (FileNotFoundError, ValueError, RuntimeError) as error:
        parser.exit(1, f"Mission notes failed: {error}\n")


if __name__ == "__main__":
    main()
