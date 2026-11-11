"""Run the heavier, BSD-licensed torchvision fallback on the same development frames."""

import hashlib
import json
import multiprocessing
import sys
from pathlib import Path

import cv2
import torch
from torchvision.models.detection import fasterrcnn_resnet50_fpn_v2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot/tools"))
from evaluate_objects import busy_core, evaluate, poller_probe
from fetch_models import ARTIFACTS, TORCH_MODEL
from pilot.contract import Detection
from pilot.objects import _frame, is_player


class TorchDetector:
    def __init__(self):
        if not torch.backends.mps.is_available():
            raise RuntimeError("This comparison requires the MPS GPU backend")
        path = ROOT / "pilot/models" / TORCH_MODEL
        with path.open("rb") as stream:
            assert hashlib.file_digest(stream, "sha256").hexdigest() == ARTIFACTS[TORCH_MODEL]
        torch.set_num_threads(2)
        self.model = fasterrcnn_resnet50_fpn_v2(weights=None, weights_backbone=None)
        self.model.load_state_dict(torch.load(path, map_location="cpu", weights_only=True))
        self.model.eval().to("mps")
        self.confidence = 0.25

    @torch.inference_mode()
    def detect(self, frame, *, exclude_player=True):
        _frame(frame)
        tensor = torch.from_numpy(frame).permute(2, 0, 1).float().to("mps") / 255
        output = self.model([tensor])[0]
        boxes, scores, classes = (output[key].cpu().numpy() for key in ("boxes", "scores", "labels"))
        kinds = {1: "person", 2: "bicycle", 3: "car", 4: "motorcycle", 6: "bus", 8: "truck"}
        results = []
        for box, score, kind in zip(boxes, scores, classes, strict=True):
            if kind in kinds and score >= self.confidence:
                detection = Detection(kinds[kind], tuple(map(float, box)), float(score))
                if not exclude_player or not is_player(detection):
                    results.append(detection)
        return tuple(results)

    __call__ = detect


def main():
    folder = ROOT / "lab/objects"
    records = json.loads((folder / "labels.json").read_text())["frames"]
    frames = [cv2.cvtColor(cv2.imread(str(folder / r["file"])), cv2.COLOR_BGR2RGB) for r in records]
    detector = TorchDetector()
    stop, ready = multiprocessing.Event(), multiprocessing.Event()
    load = multiprocessing.Process(target=busy_core, args=(stop, ready))
    load.start()
    try:
        assert ready.wait(10)
        for frame in frames[:10]:
            detector(frame)
        speed = poller_probe(detector, frames[40], seconds=5)
        for confidence in (0.15, 0.25, 0.4, 0.55):
            detector.confidence = confidence
            result = evaluate(detector, records, frames)
            name = f"fasterrcnn-native-c{confidence}"
            result.update(
                candidate=name,
                weights_sha256=ARTIFACTS[TORCH_MODEL],
                poller=speed,
                labels_sha256=hashlib.sha256((folder / "labels.json").read_bytes()).hexdigest(),
                timing_note="Late fallback, evaluated after fixed ONNX selection; no holdout tuning.",
            )
            (folder / f"candidate-{name}.json").write_text(json.dumps(result, indent=2) + "\n")
            print(
                json.dumps(
                    {
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
                ),
                flush=True,
            )
    finally:
        stop.set()
        load.join()


if __name__ == "__main__":
    main()
