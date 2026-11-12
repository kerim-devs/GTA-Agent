"""Label what Kerim does in his recordings, and gather the labels into a data set.

    label_actions.py <recording>... --out DIR [--sections PATH] [--lead S] [--game gta5]
    label_actions.py --index DIR [--recordings ROOT]...
    label_actions.py <recording>... --out DIR --index DIR

The first writes DIR/<name>/actions.jsonl (one line per stretch of one action) and labels.json beside it.
The second writes DIR/index.jsonl (two samples a second over everything labelled so far, no pixels) and
DIR/summary.md. A folder whose meta.json has no "seconds" is still being recorded and is skipped.
"""

import argparse
import sys
import time
from pathlib import Path

from pilot.actions import finished, label_recording, write_index
from pilot.profile import PROFILES


def sections_for(path: Path | None, recording: Path) -> Path | None:
    """A sections.json given directly, or a folder of P38 output holding <name>/sections.json."""
    if path is None:
        return None
    if path.is_file():
        return path
    candidate = path / recording.name / "sections.json"
    return candidate if candidate.exists() else None


def main(argv=None) -> int:
    formatter = argparse.RawDescriptionHelpFormatter
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=formatter)
    parser.add_argument("recordings", nargs="*", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--sections", type=Path, help="a sections.json of P38, or a folder of them by name")
    parser.add_argument("--lead", type=float, help="seconds the hand leads the picture, else estimated")
    parser.add_argument("--game", default="gta5", choices=sorted(PROFILES))
    parser.add_argument("--index", type=Path, help="write index.jsonl and summary.md over this output root")
    parser.add_argument(
        "--recordings-root",
        dest="roots",
        type=Path,
        action="append",
        default=[],
        help="where to look a recording up by name when it has moved",
    )
    args = parser.parse_args(argv)
    if args.recordings and args.out is None:
        parser.error("--out is required with recordings")
    if not args.recordings and args.index is None:
        parser.error("give recordings with --out, or --index")
    failed = 0
    for recording in args.recordings:
        if not finished(recording):
            print(f"{recording.name}: skipped, not a finished recording")
            continue
        started = time.perf_counter()
        try:
            info = label_recording(
                recording,
                args.out,
                sections=sections_for(args.sections, recording),
                lead=args.lead,
                profile=PROFILES[args.game],
            )
        except Exception as error:  # one broken recording must not stop the others
            print(f"{recording.name}: failed: {error}")
            failed += 1
            continue
        elapsed = time.perf_counter() - started
        seconds = info["seconds"] or 0
        rate = elapsed / (seconds / 60) if seconds else 0
        lead = f"{info['lead']:.2f} s {info['lead_source']}" if info["has_pad"] else "no controller"
        print(
            f"{recording.name}: {info['stretches']} stretches, lead {lead} "
            f"(estimate {info['lead_estimate']}, r {info['lead_correlation']}), "
            f"{elapsed:.1f} s, {rate:.1f} s per minute of recording"
        )
    if args.index is not None:
        result = write_index(args.index, args.roots)
        print(f"index: {result['recordings']} recordings, {result['samples']} samples")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
