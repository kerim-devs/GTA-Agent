"""Run the four behavioural regressions with the unchanged driver loaded from HEAD."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot/src"))
sys.path.insert(0, str(ROOT / "pilot/tests"))
from p98_replay import baseline
import test_town_corners as tests

tests.Driver, _ = baseline()
for name in sorted(
    n for n in vars(tests) if n.startswith("test_") and "blocks" not in n
):
    try:
        getattr(tests, name)()
    except AssertionError:
        print("EXPECTED FAIL before P102", name)
    else:
        print("ALREADY PASSED before P102", name)
