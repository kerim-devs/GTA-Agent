"""msheet.py out.jpg k...   or  msheet.py out.jpg a:b:step   -- compact plain sheet (scale 2, 6 columns)."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import tools
def parse(args):
    ks = []
    for a in args:
        if ":" in a:
            p = [int(x) for x in a.split(":")]
            ks += list(range(p[0], p[1], p[2] if len(p) > 2 else 1))
        else:
            ks.append(int(a))
    return ks
if __name__ == "__main__":
    tools.sheet(parse(sys.argv[2:]), sys.argv[1], scale=2, cols=6)
