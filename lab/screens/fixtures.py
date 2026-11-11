"""Recreate the nine cable fixtures and UI-only composite masks."""

from pathlib import Path
import sys, json, hashlib
import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot/src"))
sys.path.insert(0, str(ROOT / "lab/screens"))
from pilot import hud
from prepare import SOURCES
from build_anchors import ANCHORS

root = ROOT / "lab/screens"
fixtures = ROOT / "pilot/tests/fixtures/screens"
fixtures.mkdir(exist_ok=True)
(root / "masks").mkdir(exist_ok=True)
rows = []
for source, i, screen in [
    ("tour", 120, "pause"),
    ("calibration2", 2400, "pause"),
    ("tour", 360, "map"),
    ("tour", 780, "weapon_wheel"),
    ("tour", 1080, "phone"),
    ("tour", 1380, "interaction_menu"),
    ("kerim", 3000, "game"),
    ("kerim", 7500, "game"),
    ("kerim", 12000, "game"),
]:
    path = Path.home() / "recordings" / SOURCES[source]
    c = cv2.VideoCapture(str(path / "video.mp4"))
    c.set(1, i)
    ok, bgr = c.read()
    assert ok
    c.release()
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    name = f"{source}-{i:05d}"
    cv2.imwrite(str(fixtures / f"{name}.png"), bgr)
    metadata = [json.loads(l) for l in (path / "frames.jsonl").read_text().splitlines()]
    rows.append(
        dict(
            id=name,
            source=source,
            recording=SOURCES[source],
            i=i,
            capture_s=metadata[i]["t"],
            rgb_sha256=hashlib.sha256(rgb.tobytes()).hexdigest(),
            screen=screen,
        )
    )
(root / "fixtures.json").write_text(json.dumps(rows, indent=2) + "\n")
for screen, names in {
    "pause": ["PAUSE_UI", "PAUSE_TITLE_UI"],
    "map": ["MAP_UI"],
    "weapon_wheel": ["WHEEL_UI"],
    "phone": ["PHONE_UI"],
    "interaction_menu": ["INTERACTION_UI"],
}.items():
    mask = np.zeros((720, 1280), np.uint8)
    for name in names:
        _, (x0, y0, x1, y1) = ANCHORS[name]
        mask[y0:y1, x0:x1] |= getattr(hud, name + "_MASK").astype(np.uint8) * 255
    cv2.imwrite(str(root / "masks" / f"{screen}.png"), mask)
