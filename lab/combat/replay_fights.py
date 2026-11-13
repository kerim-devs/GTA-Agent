"""Run the fixed-schedule enemy bench with scratch and ledger owned by P77."""
import argparse
import hashlib
import cv2
import importlib.util
import json
import sys
from pathlib import Path

cv2.setNumThreads(1)
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot" / "src"))
from pilot.approaches import Config, create
from pilot.reaction import append_result, compact, load_scenes, replay


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.baseline:
        spec = importlib.util.spec_from_file_location("baseline_combat", ROOT / "lab/combat/baseline_combat.py")
        old = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(old)
        import pilot.combat as combat
        import pilot.guard as guard
        combat.Fight = guard.Fight = old.Fight
    fingerprint = hashlib.sha256((ROOT/'pilot/src/pilot/combat.py').read_bytes()).hexdigest()
    completed = []
    if args.output.exists():
        completed = [json.loads(line) for line in args.output.read_text().splitlines() if line.strip()]
        if any(row.get('combat_sha256') != fingerprint for row in completed):
            raise ValueError('Refusing to mix implementations in one ledger')
    completed_ids = {row['scene']['id'] for row in completed}
    for scene in load_scenes(ROOT / "lab/reaction/scenes.json"):
        if scene.kind != "enemy" or scene.id in completed_ids:
            continue
        approach = create("pilot+guard", Config(output=ROOT / "lab/combat", recording=scene.recording, modelled_delay=0.1))
        result = replay(scene, approach, mode="modelled", cost_s=1 / 30)
        after = [sample for sample in result["samples"] if sample["t"] >= result["scene"]["onset"]]
        first = {key: next((sample["t"] - result["scene"]["onset"] for sample in after if sample["pad"][key] > 0), None) for key in ("l2", "r2")}
        row = {"approach": "pilot+guard-old" if args.baseline else "pilot+guard-p77", "repeat": 0, "combat_sha256": fingerprint,
               "sampling": "fixed 30 Hz, modelled 100ms head delay", "p77": {
                   "l2_s": first["l2"], "r2_s": first["r2"],
                   "aim_within_1s": first["l2"] is not None and first["l2"] <= 1,
                   "fired": first["r2"] is not None,
               }, **compact(result)}
        append_result(args.output, row)
        print(json.dumps({"scene": scene.id, "metrics": row["metrics"]}), flush=True)


if __name__ == "__main__":
    main()
