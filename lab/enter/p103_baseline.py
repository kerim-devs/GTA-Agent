"""Run the new regressions against HEAD, restoring both source files even on failure."""
import hashlib
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
paths=[Path('pilot/src/pilot')/name for name in ('vehicle_entry.py','errands.py')]
saved={p:(ROOT/p).read_bytes() for p in paths}
try:
    for p in paths:
        original=subprocess.check_output(['git','show',f'HEAD:{p}'],cwd=ROOT)
        (ROOT/p).write_bytes(original)
    with (ROOT/'lab/enter/p103-before-tests.txt').open('w') as output:
        result=subprocess.run([str(ROOT/'pilot/.venv/bin/python'),'-m','pytest','-q','tests/test_car_in_town.py'],cwd=ROOT/'pilot',stdout=output,stderr=subprocess.STDOUT)
    print('Baseline regression exit:',result.returncode)
finally:
    for p,content in saved.items():
        (ROOT/p).write_bytes(content)
        assert (ROOT/p).read_bytes()==content
        print('Restored',p,hashlib.sha256(content).hexdigest())
