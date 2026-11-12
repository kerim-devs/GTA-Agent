#!/usr/bin/env python3
"""Plan, losslessly cut, and verify offline recording copies."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pilot.trimming import check, cut, plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    planning = commands.add_parser("plan")
    planning.add_argument("recording", type=Path)
    planning.add_argument("--derived", type=Path, required=True)
    planning.add_argument("--out", type=Path, required=True)
    cutting = commands.add_parser("cut")
    cutting.add_argument("recording", type=Path)
    cutting.add_argument("--plan", type=Path, required=True)
    cutting.add_argument("--out", type=Path, required=True)
    checking = commands.add_parser("check")
    checking.add_argument("source", type=Path)
    checking.add_argument("trimmed", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "plan":
            result = plan(args.recording, args.derived)
            if args.out.resolve().is_relative_to(args.recording.resolve()):
                raise ValueError("The plan must be outside the source recording")
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(result, indent=2) + "\n")
        elif args.command == "cut":
            result = cut(args.recording, args.plan, args.out)
        else:
            result = check(args.source, args.trimmed)
        print(json.dumps(result, indent=2))
    except (ValueError, OSError, RuntimeError, ImportError) as exc:
        parser.exit(1, f"trim: {exc}\n")


if __name__ == "__main__":
    main()
