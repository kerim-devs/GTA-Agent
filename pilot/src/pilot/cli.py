"""Command-line entry points for the live runtime and offline replay."""

import argparse
import json
import math
import sys
from dataclasses import asdict, fields
from pathlib import Path

from . import hud, profile
from .bridge import Bridge
from .calibrate import RECORDINGS as CALIBRATIONS
from .calibrate import run_calibrate, selection
from .conductor import PLAY_RECORDINGS, Conductor, run_play
from .drive import DriveConfig, Driver
from .flow import Flow
from .head import CodexHead, CodexServerHead, ScriptedHead, SkillCall
from .judge import Reader as JudgeReader
from .loop import RECORDINGS, Pipeline, run_drive
from .mission import MissionHead
from .objects import Reader as ObjectReader
from .overlay import overlay_port, run_overlay
from .replay import run_replay

MEASURED_DELAY_S = 0.14  # input to picture over the wired link with the game in performance mode
# What the console asked of the driver on 11 November, once the pedals answered. With its own
# values it held the car to two to seven metres a second by the brake, a third of the time on it,
# and after two minutes was as far from the waypoint as before (session 20261111-130010). The
# brake that holds a speed is off altogether: the speed it reads lags, the car has stopped while
# the reading still says fast, and the game takes a held brake at a standstill for reverse. And a
# reading called damaged is ridden out for two seconds: in the town's grid of blocks the minimap
# reader calls nine clean frames in ten damaged, and the driver stood still on them (session
# 20261111-130955). With these the pilot drove 2.5 km through town to its waypoint.
LIVE = {
    "brake_gain": 0.0,
    "brake_margin": 6.0,
    "speed_limit": 12.0,
    "slow_speed": 4.0,
    "lateral_acceleration": 3.0,
    "damage_hold": 2.0,
}


def duration(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("seconds must be finite and positive")
    return number


def absolute_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("record-dir must be an absolute path")
    return path


def drive_config(settings: list[str]) -> DriveConfig:
    """The driver's defaults with the measured delay, then every `name=value` from the command line."""
    kinds = {field.name: field.type for field in fields(DriveConfig)}
    values: dict[str, float | int] = {"command_delay": MEASURED_DELAY_S, **LIVE}
    for setting in settings:
        name, _, value = setting.partition("=")
        if name not in kinds:
            raise SystemExit(f"unknown setting {name!r}; known: {', '.join(sorted(kinds))}")
        try:
            values[name] = int(value) if kinds[name] in (int, "int") else float(value)
        except ValueError:
            raise SystemExit(f"{name} needs a number, not {value!r}") from None
    return DriveConfig(**values)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="pilot")
    subcommands = parser.add_subparsers(dest="command", required=True)
    calibrate = subcommands.add_parser("calibrate", help="Measure console timing and controls")
    calibrate.add_argument("--only", action="append", default=[], metavar="CHECK[,CHECK]")
    calibrate.add_argument("--skip", action="append", default=[], metavar="CHECK[,CHECK]")
    calibrate.add_argument("--car", action="store_true")
    calibrate.add_argument("--yes", action="store_true")
    calibrate.add_argument("--shadow", action="store_true")
    calibrate.add_argument("--record-dir", type=absolute_path, default=CALIBRATIONS)
    calibrate.add_argument("--head", choices=("codex", "off"), default="codex")
    drive = subcommands.add_parser("drive", help="Run the local driving loop")
    drive.add_argument("--seconds", type=duration)
    drive.add_argument("--shadow", action="store_true")
    drive.add_argument("--no-record", action="store_true")
    drive.add_argument("--record-dir", type=absolute_path, default=RECORDINGS)
    replay = subcommands.add_parser("replay", help="Evaluate a recording offline")
    replay.add_argument("recording", type=Path)
    replay.add_argument("--out", type=Path)
    play = subcommands.add_parser("play", help="Run event-driven skills and an asynchronous head")
    play.add_argument("--seconds", type=duration)
    play.add_argument("--shadow", action="store_true")
    play.add_argument("--no-record", action="store_true")
    play.add_argument("--no-ocr", action="store_true")
    play.add_argument("--no-hud-flow", action="store_true", help="disable HUD readings and screen reflexes")
    play.add_argument("--no-objects", action="store_true", help="run without the object detector")
    play.add_argument(
        "--judge",
        action="append",
        default=[],
        metavar="URL=MODEL",
        help="local judge servers in preference order",
    )
    play.add_argument("--no-level", action="store_true", help="do not level the camera before the first plan")
    play.add_argument("--record-dir", type=absolute_path, default=PLAY_RECORDINGS)
    play.add_argument("--notebook", type=Path)
    play.add_argument(
        "--head",
        choices=("scripted", "codex", "codex-server", "rules", "rules-only"),
        default="scripted",
        help="rules decides the plain cases at once and asks the codex server for the rest; "
        "rules-only never asks a model",
    )
    play.add_argument(
        "--plan",
        action="append",
        default=[],
        metavar="JSON",
        help='with the scripted head: a plan to run, e.g. \'[{"name": "enter_vehicle", "args": {}}]\'; '
        "give it again for the answer to the next request",
    )
    play.add_argument("--head-model")
    play.add_argument("--head-effort", default="low")
    play.add_argument("--head-timeout", type=duration, default=45.0)
    play.add_argument("--quiet-seconds", type=duration, default=60.0)
    play.add_argument(
        "--game", choices=sorted(profile.PROFILES), default="gta5", help="whose buttons and dead zones"
    )
    for command in (drive, replay, play):
        command.add_argument(
            "--set", action="append", default=[], metavar="NAME=VALUE", help="override a DriveConfig field"
        )
    overlay = subcommands.add_parser("overlay", help="Serve a local OBS overlay from recordings")
    overlay.add_argument("--root", type=Path, default=PLAY_RECORDINGS, help="Session recordings root")
    overlay.add_argument("--port", type=overlay_port, default=9396, help="Loopback HTTP port (default: 9396)")
    overlay.add_argument("--demo", type=Path, help="Replay one recorded session at its original pace")
    overlay.add_argument(
        "--shadow", action="store_true", help="Label a known shadow session (not persisted by play)"
    )

    args = parser.parse_args(argv)
    if args.command == "calibrate":
        try:
            checks = selection(args.only, args.skip, car=args.car)
        except ValueError as error:
            parser.error(str(error))
        head = CodexHead(timeout=45) if "head" in checks and args.head == "codex" else None
        with Bridge() as bridge:
            run_calibrate(
                bridge,
                only=args.only,
                skip=args.skip,
                car=args.car,
                yes=args.yes,
                shadow=args.shadow,
                record_dir=args.record_dir,
                head=head,
            )
        return
    if args.command == "overlay":
        run_overlay(args.root, args.port, args.demo, args.shadow)
        return
    config = drive_config(args.set)
    pipeline = Pipeline(driver=Driver(config))
    if args.command == "drive":
        with Bridge() as bridge:
            run_drive(
                bridge,
                seconds=args.seconds,
                shadow=args.shadow,
                record=not args.no_record,
                record_dir=args.record_dir,
                pipeline=pipeline,
                config=asdict(config),
            )
    elif args.command == "play":
        try:
            judge = JudgeReader(args.judge) if args.judge else None
        except ValueError as error:
            parser.error(str(error))
        if args.plan and args.head != "scripted":
            parser.error("--plan needs the scripted head")
        # Before the first skill, the reflex and the runtime are built: each keeps the profile it was
        # built under.
        profile.use(args.game)
        try:
            plans = [{"plan": json.loads(plan), "sentence": "Geplanter Schritt."} for plan in args.plan]
        except json.JSONDecodeError as error:
            parser.error(f"--plan is not JSON: {error}")
        if args.head == "scripted":
            head = ScriptedHead(plans or None)
        elif args.head == "rules-only":
            head = MissionHead()
        else:
            head = (CodexHead if args.head == "codex" else CodexServerHead)(
                model=args.head_model, effort=args.head_effort, timeout=args.head_timeout
            )
            if args.head == "rules":
                head = MissionHead(head)
        objects = None
        if not args.no_objects:
            try:
                objects = ObjectReader()
            except RuntimeError as exc:
                # Without the weights the pilot still plays; the skills that need them say so.
                print(f"object detector off: {exc}", file=sys.stderr)
        with Bridge() as bridge:
            print(
                run_play(
                    bridge,
                    seconds=args.seconds,
                    shadow=args.shadow,
                    record=not args.no_record,
                    record_dir=args.record_dir,
                    pipeline=pipeline,
                    head=head,
                    notebook=args.notebook or args.record_dir / "notebook.txt",
                    ocr=not args.no_ocr,
                    quiet_seconds=args.quiet_seconds,
                    driver_factory=lambda: Driver(config),
                    objects=objects,
                    judge=judge,
                    awake=Conductor.AWAKE_SECONDS,
                    hud=None if args.no_hud_flow else hud,
                    flow=None if args.no_hud_flow else Flow(),
                    opening=() if args.no_level else (SkillCall("level_camera", {}),),
                )
            )
    else:
        run_replay(args.recording, out=args.out, pipeline=pipeline)


if __name__ == "__main__":
    main()
