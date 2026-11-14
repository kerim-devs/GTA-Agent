"""Run the new behavioural tests on HEAD, restoring both owned files in finally."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILES = ('pilot/src/pilot/avoid.py', 'pilot/src/pilot/skills.py')


if __name__ == '__main__':
    saved = {name: (ROOT / name).read_bytes() for name in FILES}
    try:
        for name in FILES:
            (ROOT / name).write_bytes(subprocess.check_output(['git', 'show', f'HEAD:{name}'], cwd=ROOT))
        result = subprocess.run([sys.executable, '-m', 'pytest', '-q', 'tests/test_brake_for_the_lane.py'],
                                cwd=ROOT / 'pilot', capture_output=True, text=True)
        (ROOT / 'lab/avoid/p106-before-tests.txt').write_text(result.stdout + result.stderr)
        print(result.stdout[-4000:])
        print('baseline exit', result.returncode)
    finally:
        for name, content in saved.items():
            (ROOT / name).write_bytes(content)
        print('Both current files restored byte for byte.')
