"""Record independently reviewed holdout boxes supplied as JSON on stdin."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "holdout"
path = ROOT / "labels.json"
manifest = json.loads((path if path.exists() else ROOT / "sample.json").read_text())
updates = json.load(sys.stdin)
records = {r["id"]: r for r in manifest["frames"]}
assert set(updates) <= set(records)
for ident, update in updates.items():
    assert not records[ident].get("reviewed"), ident
    for label in update["labels"]:
        x0, y0, x1, y1 = label["box"]
        assert 0 <= x0 < x1 <= 1280 and 0 <= y0 < y1 <= 720, label
        assert label["kind"] in ("person", "car", "truck", "bus", "motorcycle", "bicycle")
        assert isinstance(label["player"], bool)
    records[ident].update(update, reviewed=True)
complete = all(r.get("reviewed") for r in records.values())
manifest["annotation"] = (
    "Independent manual boxes checked on each raw 1280x720 frame after model/settings freeze; no predictions or sheets used."
    if complete
    else "Pending manual annotation"
)
manifest["box_convention"] = (
    "xyxy full-image pixels; visible object extent, borderline small objects retained"
)
path.write_text(json.dumps(manifest, indent=2) + "\n")
print(f"Reviewed {sum(bool(r.get('reviewed')) for r in records.values())}/{len(records)} frames")
