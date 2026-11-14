"""Run the new regression on HEAD, restoring the owned working file byte for byte."""

import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
target = root / 'pilot/src/pilot/avoid.py'
saved = target.read_bytes()
try:
    original = subprocess.check_output(['git', 'show', 'HEAD:pilot/src/pilot/avoid.py'], cwd=root)
    target.write_bytes(original)
    result = subprocess.run([sys.executable, '-m', 'pytest', '-q', 'pilot/tests/test_brake_held.py'], cwd=root)
finally:
    target.write_bytes(saved)
    assert target.read_bytes() == saved
print('Baseline pytest exit:', result.returncode, '; working file restored byte for byte', flush=True)
if result.returncode == 0:
    raise SystemExit('Expected the regression to fail on HEAD')
