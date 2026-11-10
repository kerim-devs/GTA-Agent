"""Command-line entry points for the live runtime and offline replay."""

import argparse
import math
from dataclasses import asdict, fields
from pathlib import Path

from .bridge import Bridge
from .drive import DriveConfig, Driver
from .loop import RECORDINGS, Pipeline, run_drive
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
    for command in (drive, replay):
        command.add_argument(
            "--set", action="append", default=[], metavar="NAME=VALUE", help="override a DriveConfig field"
        )
    args = parser.parse_args(argv)
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
    else:
        run_replay(args.recording, out=args.out, pipeline=pipeline)


if __name__ == "__main__":
    main()
