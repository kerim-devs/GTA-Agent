"""Fetch the official Apache-2.0 YOLOX Tiny weights once, verifying their digest."""

import hashlib
from pathlib import Path
from urllib.request import urlopen

MODEL = Path(__file__).resolve().parents[1] / "models" / "yolox_tiny.onnx"
URL = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_tiny.onnx"
SHA256 = "427cc366d34e27ff7a03e2899b5e3671425c262ea2291f88bb942bc1cc70b0f7"


def fetch(destination: Path = MODEL) -> Path:
    if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest() == SHA256:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".download")
    try:
        digest = hashlib.sha256()
        with urlopen(URL, timeout=60) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                digest.update(chunk)
                output.write(chunk)
        if digest.hexdigest() != SHA256:
            raise RuntimeError("YOLOX Tiny checksum mismatch; downloaded weights were discarded")
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


if __name__ == "__main__":
    print(fetch())
