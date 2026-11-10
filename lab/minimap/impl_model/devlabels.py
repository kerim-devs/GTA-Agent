"""Dev labels only (never G02, G05, G09, G12)."""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools import load
HELD = {"G02", "G05", "G09", "G12"}
def dev():
    crops, meta, golden = load()
    by_id = {g["id"]: g for g in golden}
    out = []
    for p in sorted((ROOT / "data" / "labels").glob("*.json")):
        if p.stem in HELD:
            continue
        for lab in json.loads(p.read_text()):
            g = by_id[lab["id"]]
            assert g["split"] == "dev"
            out.append({**lab, "k": g["k"]})
    return crops, meta, out
if __name__ == "__main__":
    crops, meta, labs = dev()
    for l in labs:
        print(l["id"], l["k"], l["minimap"], l["route"], l["near_clock"], l["far_clock"], l["arrow_clock"], "C" if l["corrupt"] else "-", l.get("note",""))
