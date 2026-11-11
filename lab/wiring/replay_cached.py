"""Re-run wiring against the native OCR captured by the first full-video replay."""

import argparse
import json
import sys
from pathlib import Path
from typing import get_args, get_type_hints

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot"))

from pilot.scene import SceneText  # noqa: E402
from tools.conductor_replay import run_offline  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("recording", type=Path)
    parser.add_argument("text_log", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    records = [json.loads(line) for line in args.text_log.read_text().splitlines()]
    line_type = get_args(get_type_hints(SceneText)["lines"])[0]

    class Reader:
        index = 0

        def read(self, rgb):
            record = records[self.index]
            self.index += 1
            data = dict(record["text"])
            data["lines"] = tuple(line_type(**item) for item in data["lines"])
            return SceneText(**data)

    reader = Reader()
    report = run_offline(args.recording, args.out, hud_flow=True, text_reader=reader)
    emitted = [json.loads(line) for line in (args.out / "text.jsonl").read_text().splitlines()]
    assert emitted == records, "cached text must retain the original capture timestamps and payloads"
    assert reader.index == len(records)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
