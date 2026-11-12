"""Quality gate — one call: `.venv/bin/python tools/gate.py`. Lint, format check, tests."""

import argparse
import subprocess
import sys
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--full", action="store_true")
args = parser.parse_args()
started = time.perf_counter()

STEPS = [
    ["ruff", "check", "src", "tests", "tools"],
    ["ruff", "format", "--check", "src", "tests", "tools"],
    ["pytest", "-q", *(["--full"] if args.full else [])],
]

for step in STEPS:
    print("$", " ".join(step), flush=True)
    if subprocess.call([sys.executable, "-m", *step]) != 0:
        sys.exit(f"gate failed at: {' '.join(step)}")
elapsed = time.perf_counter() - started
print(f"gate passed in {elapsed:.2f}s ({'full' if args.full else 'default'})")
if not args.full and elapsed >= 90:
    sys.exit("default gate exceeded 90 seconds")
