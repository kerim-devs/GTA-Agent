"""Evaluate the packaged reader with the research harness."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "pilot" / "src"))

from pilot.minimap import read  # noqa: E402, F401
