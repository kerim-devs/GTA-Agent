"""Command-line entry points for the live runtime and offline replay."""

import argparse
import math
import sys
from dataclasses import asdict, fields
from pathlib import Path

from . import hud
from .bridge import Bridge
from .conductor import PLAY_RECORDINGS, run_play
from .drive import DriveConfig, Driver
from .flow import Flow
from .head import CodexHead, CodexServerHead, ScriptedHead
from .loop import RECORDINGS, Pipeline, run_drive
from .objects import Reader as ObjectReader
from .overlay import overlay_port, run_overlay
from .replay import run_replay

MEASURED_DELAY_S = 0.14  # input to picture over the wired link with the game in performance mode


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
    values: dict[str, float | int] = {"command_delay": MEASURED_DELAY_S}
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
    play.add_argument("--record-dir", type=absolute_path, default=PLAY_RECORDINGS)
    play.add_argument("--notebook", type=Path)
    play.add_argument("--head", choices=("scripted", "codex", "codex-server"), default="scripted")
    play.add_argument("--head-model")
    play.add_argument("--head-effort", default="low")
    play.add_argument("--head-timeout", type=duration, default=45.0)
    play.add_argument("--quiet-seconds", type=duration, default=60.0)
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
        head = (
            ScriptedHead()
            if args.head == "scripted"
            else (CodexServerHead if args.head == "codex-server" else CodexHead)(
                model=args.head_model, effort=args.head_effort, timeout=args.head_timeout
            )
        )
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
                    hud=None if args.no_hud_flow else hud,
                    flow=None if args.no_hud_flow else Flow(),
                )
            )
    else:
        run_replay(args.recording, out=args.out, pipeline=pipeline)


if __name__ == "__main__":
    main()
