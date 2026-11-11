"""Label completed recordings without connecting to a console."""

import argparse
import json
import time
from pathlib import Path

from pilot.sections import analyze, contact_sheet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recordings", nargs="+", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    for recording in args.recordings:
        started = time.perf_counter()
        result = analyze(recording)
        if result is None:
            print(f"{recording.name}: skipped unfinished recording", flush=True)
            continue
        output = args.out / recording.name
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


if __name__ == "__main__":
    main()
