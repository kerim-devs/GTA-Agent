"""Label completed recordings without connecting to a console."""

import argparse
import json
import time
from pathlib import Path

from pilot.sections import Judge, analyze, contact_sheet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recordings", nargs="+", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--judge",
        metavar="URL=MODEL",
        help="ask this server about frames of the stretches the readers leave unknown or doubtful",
    )
    args = parser.parse_args()
    judge = Judge(args.judge) if args.judge else None
    for recording in args.recordings:
        started = time.perf_counter()
        output = args.out / recording.name
        before = len(judge.seconds) if judge else 0
        result = analyze(recording, judge=judge, folder=output)
        if result is None:
            print(f"{recording.name}: skipped unfinished recording", flush=True)
            continue
        output.mkdir(parents=True, exist_ok=True)
        (output / "sections.json").write_text(json.dumps(result, indent=2) + "\n")
        contact_sheet(recording, result, output / "sections.jpg")
        elapsed = time.perf_counter() - started
        rate = elapsed / (result["seconds"] / 60) if result["seconds"] else 0
        print(
            f"{recording.name}: {len(result['sections'])} sections; "
            f"{elapsed:.3f}s; {rate:.3f}s/recording-minute",
            flush=True,
        )
        if judge is not None and judge.down is None:
            asked = judge.seconds[before:]
            print(
                f"{recording.name}: judge {len(asked)} requests, {sum(asked):.1f}s, "
                f"{len(judge.cache)} frames in the cache",
                flush=True,
            )


if __name__ == "__main__":
    main()
