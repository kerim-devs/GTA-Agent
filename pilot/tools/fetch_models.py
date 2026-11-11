"""Fetch pinned Apache-2.0 detector weights once; inference never downloads anything."""

import argparse
import hashlib
from pathlib import Path
from urllib.request import urlopen

from pilot.objects import MODEL, SHA256, WEIGHTS

TORCH_MODEL = "fasterrcnn_resnet50_fpn_v2_coco-dd69338a.pth"
ARTIFACTS = {**WEIGHTS, TORCH_MODEL: "dd69338a24b8d7381807e247652bdc356325bcbaf1cd3e092e00e0a1a58706bf"}

URL = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/"
RTDETR_URL = (
    "https://huggingface.co/onnx-community/rtdetr_v2_r18vd-ONNX/resolve/main/onnx/model.onnx?download=true"
)


def fetch(destination: Path = MODEL) -> Path:
    filename = destination.name if destination.name in ARTIFACTS else MODEL.name
    expected = ARTIFACTS.get(filename, SHA256)
    url = RTDETR_URL if filename.startswith("rtdetr") else URL + filename
    if filename == TORCH_MODEL:
        url = "https://download.pytorch.org/models/" + filename
    if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest() == expected:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".download")
    try:
        digest = hashlib.sha256()
        with urlopen(url, timeout=60) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                digest.update(chunk)
                output.write(chunk)
        if digest.hexdigest() != expected:
            raise RuntimeError("Detector checksum mismatch; downloaded weights were discarded")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=list(ARTIFACTS), default=MODEL.name)
    args = parser.parse_args()
    print(fetch(MODEL.with_name(args.model)))
