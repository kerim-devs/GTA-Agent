"""Load the packaged reader in the existing standalone lab harness."""

import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "pilot/src"))
source = Path(os.environ.get("P34_BASELINE", ROOT / "pilot/src/pilot/minimap.py"))
spec = importlib.util.spec_from_file_location("pilot.p34_reader", source)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
read = module.read
