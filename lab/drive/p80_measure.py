"""Run the P80 parked-car matrix from the repository root."""
import runpy
from pathlib import Path

scope = runpy.run_path(str(Path(__file__).resolve().parents[2] / "pilot/tools/evaluate_player_driver.py"))
parked = scope["parked"]

if __name__ == "__main__":
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    rows = scope["parked_matrix"]()
    args.out.write_text(json.dumps(rows, indent=2) + "\n")
