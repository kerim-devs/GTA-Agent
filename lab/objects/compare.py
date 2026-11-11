"""Compare pinned YOLOX candidates on the original, already-seen labels only."""

import argparse
import hashlib
import json
import multiprocessing
import sys
from pathlib import Path

import cv2
import onnx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot" / "tools"))
from evaluate_objects import busy_core, evaluate, poller_probe
from pilot.objects import Detector, WEIGHTS


def native_model(size):
    source = ROOT / "pilot" / "models" / f"yolox_{size}.onnx"
    with source.open("rb") as weights:
        if hashlib.file_digest(weights, "sha256").hexdigest() != WEIGHTS[source.name]:
            raise RuntimeError("Fetch the pinned source weights before creating native tiles")
    target = source.with_stem(source.stem + "_736")
    model = onnx.load(source)
    for dim in model.graph.input[0].type.tensor_type.shape.dim[2:]:
        dim.dim_value = 736
    for output in model.graph.output:
        output.type.tensor_type.shape.dim[1].dim_value = 11109
    del model.graph.value_info[:]
    model = onnx.shape_inference.infer_shapes(model)
    onnx.save(model, target)
    WEIGHTS[target.name] = hashlib.sha256(target.read_bytes()).hexdigest()
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", default=("tiny", "s", "m", "l"))
    args = parser.parse_args()
    records = json.loads((ROOT / "lab/objects/labels.json").read_text())["frames"]
    frames = [
        cv2.cvtColor(cv2.imread(str(ROOT / "lab/objects" / r["file"])), cv2.COLOR_BGR2RGB) for r in records
    ]
    results = []
    stop, ready = multiprocessing.Event(), multiprocessing.Event()
    load = multiprocessing.Process(target=busy_core, args=(stop, ready))
    load.start()
    try:
        assert ready.wait(10)
        for size in args.models:
            for tiles in (False, True) if size not in ("tiny", "rtdetr") else (False,):
                if size == "rtdetr":
                    path = ROOT / "pilot/models/rtdetr_v2_r18vd.onnx"
                else:
                    path = native_model(size) if tiles else ROOT / "pilot/models" / f"yolox_{size}.onnx"
                detector = Detector(path)
                detector.tiled = tiles
                for frame in frames[:10]:
                    detector(frame)
                speed = poller_probe(detector, frames[40], seconds=5)
                for confidence in (0.15, 0.25, 0.4, 0.55):
                    detector.confidence = confidence
                    result = evaluate(detector, records, frames)
                    name = f"{size}-{'native-tiles' if tiles else detector.size}-c{confidence}"
                    result.update(candidate=name, weights_sha256=WEIGHTS[path.name], poller=speed)
                    (ROOT / "lab/objects" / f"candidate-{name}.json").write_text(
                        json.dumps(result, indent=2) + "\n"
                    )
                    summary = {
                        k: result[k]
                        for k in (
                            "candidate",
                            "groups",
                            "invented_fraction",
                            "player_reported_fraction",
                            "mean_ms",
                            "poller",
                        )
                    }
                    results.append(summary)
                    (ROOT / "lab/objects" / f"candidates-{'-'.join(args.models)}.json").write_text(
                        json.dumps(results, indent=2) + "\n"
                    )
                    print(json.dumps(summary), flush=True)
    finally:
        stop.set()
        load.join()


if __name__ == "__main__":
    main()
