"""Repeat the acceptance regressions against HEAD and always restore the working source."""

import hashlib
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
source = ROOT / "pilot/src/pilot/drive.py"
saved = source.read_bytes()
before = subprocess.check_output(["git", "show", "HEAD:pilot/src/pilot/drive.py"], cwd=ROOT)
try:
    source.write_bytes(before)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_swerve.py",
            "-q",
            "-k",
            "parked_box or clear_kerb or downhill_backing or recorded_seconds",
        ],
        cwd=ROOT / "pilot",
        capture_output=True,
        text=True,
        check=False,
    )
    (HERE / "p110-acceptance-before.txt").write_text(result.stdout + result.stderr)
    print(result.stdout[-3500:])
finally:
    source.write_bytes(saved)
    assert source.read_bytes() == saved
    print("Restored drive.py SHA256:", hashlib.sha256(saved).hexdigest())
