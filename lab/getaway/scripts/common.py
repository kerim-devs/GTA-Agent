"""Paths shared by the P68 measuring scripts.

What they cut from the recordings lies in the folder named by P68_WORK (default `p68-work` in the current
folder): `keys/` holds the key-frame minimap crops of Kerim's recordings written by keys.py (about 360 MB),
`truck/` the ticks of the truck session written by truck_extract.py. The labels are in ../labels. Long scans
wait while the file named by P68_BUSY exists, the sign that somebody plays on the console from this Mac."""

import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LABELS = HERE.parent / "labels"
sys.path.insert(0, str(HERE.parents[2] / "pilot" / "src"))
WORK = Path(os.environ.get("P68_WORK", "p68-work"))
KEYS = WORK / "keys"
BUSY = os.environ.get("P68_BUSY")


def busy() -> bool:
    return bool(BUSY) and Path(BUSY).exists()


def wait_while_busy() -> None:
    while busy():
        time.sleep(30)
