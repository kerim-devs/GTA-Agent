"""Evaluate P49 on disposable copies, one recording at a time (under 2 GB)."""
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot/src"))
from pilot.trimming import check, cut, plan


def main():
    sources = Path("/Users/kerim/recordings")
    results = Path(__file__).resolve().parent
    work = results / "work"
    if work.exists() and any(work.iterdir()):
        raise RuntimeError("Work directory must be empty before evaluation")
    work.mkdir(exist_ok=True)
    for name in ("20261111-171046", "20261111-194609", "20261111-183820"):
        source = sources / "kerim" / name
        local = work / "source" / name
        destination = work / "trimmed" / "kerim" / name
        total = sum((source / filename).stat().st_size for filename in
                    ("video.mp4", "frames.jsonl", "pad.jsonl", "meta.json"))
        if total * 2 > 2_000_000_000:
            raise RuntimeError("Copies could exceed the 2 GB working limit")
        local.mkdir(parents=True)
        for filename in ("video.mp4", "frames.jsonl", "pad.jsonl", "meta.json"):
            shutil.copy2(source / filename, local / filename)
        specification = plan(local, sources / "derived" / "kerim" / name)
        plan_path = results / f"{name}-plan.json"
        plan_path.write_text(json.dumps(specification, indent=2) + "\n")
        metadata = cut(local, plan_path, destination)
        print(f"{name}: copied and cut; checking", flush=True)
        verification = check(local, destination)
        (results / f"{name}-result.json").write_text(json.dumps(
            {"source": str(source), "cut": metadata, "check": verification}, indent=2) + "\n")
        print(json.dumps({"recording": name, **verification}), flush=True)
        shutil.rmtree(work / "source")
        if name != "20261111-183820":
            shutil.rmtree(work / "trimmed")
    print("Last trimmed copy retained for the processing-chain check; remove work contents afterwards.", flush=True)


if __name__ == "__main__":
    main()
