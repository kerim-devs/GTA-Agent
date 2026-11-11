The detector uses the official YOLOX Tiny ONNX export from Megvii-BaseDetection/YOLOX release 0.1.1rc0. YOLOX and the published model are provided under Apache 2.0; the accompanying license is in LICENSE.yolox. ONNX Runtime is MIT licensed. No remote inference service is used, and runtime telemetry is disabled before session creation.

Run `.venv/bin/python tools/fetch_models.py` from `pilot` to download `yolox_tiny.onnx` once. The 20,219,662-byte model is intentionally excluded from git. Its SHA-256 is `427cc366d34e27ff7a03e2899b5e3671425c262ea2291f88bb942bc1cc70b0f7`. Both the fetcher and detector verify that exact digest. Downloads are explicit; constructing the detector never fetches anything.

The measurements and limitations are in `docs/reports/P14-objects.md` and `lab/objects/metrics.json` at the repository root. Passing the software gate does not establish the card's detection-quality targets.
