"""Run new regressions against HEAD, restoring both worktree files even on failure."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILES = ("pilot/src/pilot/drive.py", "pilot/src/pilot/avoid.py")


def main():
    saved = {name: (ROOT / name).read_bytes() for name in FILES}
    try:
        for name in FILES:
            (ROOT / name).write_bytes(subprocess.check_output(["git", "show", f"HEAD:{name}"], cwd=ROOT))
        with (ROOT / "lab/drive/p101-before-tests.txt").open("w") as output:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "pilot/tests/test_round_what_stands.py",
                ],
                cwd=ROOT,
                check=False,
                stdout=output,
                stderr=subprocess.STDOUT,
            )
        print(f"HEAD regression exit: {result.returncode}")
    finally:
        for name, source in saved.items():
            (ROOT / name).write_bytes(source)
    assert all((ROOT / name).read_bytes() == source for name, source in saved.items())
    print("Worktree driver and avoider restored byte for byte.")


if __name__ == "__main__":
    main()
