# Times NitroGen where it runs, with no network in the way (card P63): the seconds until it is loaded,
# the memory it takes beside the judge, and the time for one request, one frame in and one chunk of
# actions out. Prints the numbers as JSON and keeps them in time_local.json in the folder.
#
#   lab/policy/pc.sh lab/policy/time_local.ps1
$root = "C:\Users\gta\policy"
Set-Location $root
$env:HF_HOME = "$root\hf"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
$code = @'
"""Times NitroGen where it runs: loading, memory and seconds per request (card P63)."""
import contextlib
import io
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import torch
from transformers import SiglipVisionConfig, SiglipVisionModel

ROOT = Path(r"C:\Users\gta\policy")
sys.path.insert(0, str(next(ROOT.glob("NitroGen-*"))))
from nitrogen.inference_session import InferenceSession, load_model  # noqa: E402


def note(text):
    print(text, file=sys.stderr, flush=True)


def gpu_used():
    query = ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"]
    return int(subprocess.run(query, capture_output=True, text=True).stdout.split()[0])


report = {"torch": torch.__version__, "gpu_used_before_mb": gpu_used()}

# The checkpoint's 1.97 GB are its 493 M parameters as float32, the vision tower among them, and it is
# loaded strictly. So the tower is built from its configuration alone and the 2.6 GB of pretrained
# weights, which the checkpoint would overwrite, are not fetched over a slow line.
pretrained = SiglipVisionModel.from_pretrained
SiglipVisionModel.from_pretrained = staticmethod(lambda name, *a, **k: SiglipVisionModel(SiglipVisionConfig.from_pretrained(name)))
log = io.StringIO()
started = time.perf_counter()
try:
    with contextlib.redirect_stdout(log):
        loaded = load_model(str(ROOT / "ng.pt"))
    report["vision_tower"] = "built from its configuration, weights from the checkpoint"
except Exception as error:
    note(f"the tower from its configuration alone failed ({type(error).__name__}: {error}); fetching the pretrained one")
    SiglipVisionModel.from_pretrained = pretrained
    started = time.perf_counter()
    with contextlib.redirect_stdout(log):
        loaded = load_model(str(ROOT / "ng.pt"))
    report["vision_tower"] = "pretrained weights fetched, then overwritten by the checkpoint"
model, tokenizer, img_proc, cfg, mapping, ratio = loaded
report["load_s"] = round(time.perf_counter() - started, 1)
note(f"loaded in {report['load_s']} s")

session = InferenceSession(model, str(ROOT / "ng.pt"), tokenizer, img_proc, cfg, mapping, None, False, 1.0, ratio, None)
m, d = cfg.model_cfg, cfg.modality_cfg
report["config"] = {
    "parameters_m": round(sum(p.numel() for p in model.parameters()) / 1e6, 1),
    "vision_encoder": m.vision_encoder_name,
    "image_processor": type(img_proc).__name__,
    "action_horizon": m.action_horizon,
    "flow_steps": m.num_inference_timesteps,
    "frames_per_sample": d.frame_per_sample,
    "action_per_chunk": d.action_per_chunk,
    "frame_spacing": d.frame_spacing,
    "action_shift": d.action_shift,
    "action_interleaving": d.action_interleaving,
    "action_downsample_ratio": ratio,
    "games": None if mapping is None else len(mapping),
}
if mapping:
    names = [str(game) for game in mapping]
    (ROOT / "games.json").write_text(json.dumps(names, indent=1))
    report["games_like_gta"] = [n for n in names if "theft" in n.lower() or "gta" in n.lower()]
    report["games_first"] = names[:30]

rng = np.random.default_rng(0)
frames = {
    "256x256": rng.integers(0, 256, (256, 256, 3), dtype=np.uint8),
    "1280x720": rng.integers(0, 256, (720, 1280, 3), dtype=np.uint8),
}


def timed(frame, count):
    seconds = []
    for _ in range(count):
        began = time.perf_counter()
        with contextlib.redirect_stdout(io.StringIO()):
            pred = session.predict(frame)  # ends on the CPU, so the card has finished when it returns
        seconds.append(time.perf_counter() - began)
    return seconds, pred


def summary(seconds):
    ordered = sorted(seconds)
    return {
        "median_ms": round(1000 * statistics.median(ordered), 1),
        "p90_ms": round(1000 * ordered[int(0.9 * len(ordered))], 1),
        "worst_ms": round(1000 * ordered[-1], 1),
        "requests": len(ordered),
    }


timed(frames["256x256"], 20)  # warm-up
torch.cuda.reset_peak_memory_stats()
own = model.num_inference_timesteps
report["requests"] = {}
for steps in dict.fromkeys((own, 8, 4)):
    model.num_inference_timesteps = steps
    timed(frames["256x256"], 5)
    for name, frame in frames.items():
        seconds, pred = timed(frame, 200 if steps == own else 60)
        report["requests"][f"{steps} flow steps, frame {name}"] = summary(seconds)
        note(f"{steps} flow steps, frame {name}: {report['requests'][f'{steps} flow steps, frame {name}']}")
model.num_inference_timesteps = own
report["chunk"] = {key: list(np.asarray(value).shape) for key, value in pred.items()}
report["first_action"] = {key: np.round(np.asarray(value, dtype=float)[0], 2).tolist() for key, value in pred.items()}
report["memory"] = {
    "torch_peak_mb": round(torch.cuda.max_memory_allocated() / 2**20),
    "torch_reserved_mb": round(torch.cuda.memory_reserved() / 2**20),
    "gpu_used_after_mb": gpu_used(),
}
text = json.dumps(report, indent=1)
(ROOT / "time_local.json").write_text(text)
print(text)
'@
[IO.File]::WriteAllText("$root\time_local.py", $code)
& "$root\venv\Scripts\python.exe" "$root\time_local.py"
if ($LASTEXITCODE -ne 0) { throw "the timing failed ($LASTEXITCODE)" }
