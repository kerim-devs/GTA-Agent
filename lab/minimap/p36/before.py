"""Load the unchanged reader from the task's base commit for reproducible comparisons."""
from pathlib import Path
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parents[3]
BASE_REVISION = "9fe9e34"
sys.path.insert(0, str(ROOT / "pilot/src"))
module = types.ModuleType("pilot.p36_baseline")
sys.modules[module.__name__] = module
source = subprocess.check_output(
    ["git", "show", f"{BASE_REVISION}:pilot/src/pilot/minimap.py"], cwd=ROOT
)
exec(compile(source, f"{BASE_REVISION}:pilot/src/pilot/minimap.py", "exec"), module.__dict__)
read = module.read
