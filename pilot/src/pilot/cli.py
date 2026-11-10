"""Command-line entry points for the live runtime and offline replay."""

import argparse
import math
from pathlib import Path

from .bridge import Bridge
from .loop import RECORDINGS, run_drive
from .replay import run_replay


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
    args = parser.parse_args(argv)
    if args.command == "drive":
        with Bridge() as bridge:
            run_drive(
                bridge,
                seconds=args.seconds,
                shadow=args.shadow,
                record=not args.no_record,
                record_dir=args.record_dir,
            )
    else:
        run_replay(args.recording, out=args.out)


if __name__ == "__main__":
    main()
