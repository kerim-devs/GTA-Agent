# Serves NitroGen to the pilot over HTTP, on the PC's own loopback and nowhere else (card P63). The
# repository's own server unpickles what it is sent and listens on every interface; this one speaks
# JSON, in the form of the reaction bench's `POST /policy`, and is reached through the forwarded port.
# It runs until Ctrl-C or until the SSH session ends, and nothing of it stays behind.
#
#   lab/policy/pc.sh -L 18790 lab/policy/serve.ps1
$root = "C:\Users\gta\policy"
Set-Location $root
$env:HF_HOME = "$root\hf"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
$code = @'
"""Serves NitroGen as `POST /policy` on the PC's loopback (card P63)."""
import base64
import contextlib
import io
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
from PIL import Image
from transformers import SiglipVisionConfig, SiglipVisionModel

ROOT = Path(r"C:\Users\gta\policy")
PORT = 18790  # away from 18762 and its neighbours, where the reaction bench puts its stand-ins
RATE = 60  # the repository's client plays one action a step at 60 steps a second
sys.path.insert(0, str(next(ROOT.glob("NitroGen-*"))))
from nitrogen.inference_session import InferenceSession, load_model  # noqa: E402
from nitrogen.shared import BUTTON_ACTION_TOKENS  # noqa: E402

# NitroGen's names for the pilot's. GUIDE, BACK and START are left out as the repository's client
# leaves them out, and the pilot never presses the PS or the create button; the four RIGHT_ tokens
# have no button in that client either.
NAMES = {
    "SOUTH": "cross", "EAST": "circle", "WEST": "square", "NORTH": "triangle",
    "LEFT_SHOULDER": "l1", "RIGHT_SHOULDER": "r1", "LEFT_THUMB": "l3", "RIGHT_THUMB": "r3",
    "DPAD_UP": "up", "DPAD_DOWN": "down", "DPAD_LEFT": "left", "DPAD_RIGHT": "right",
}  # fmt: skip

# The checkpoint holds the vision tower's weights and is loaded strictly, so the tower is built from
# its configuration alone and 2.6 GB of pretrained weights are not fetched.
SiglipVisionModel.from_pretrained = staticmethod(lambda name, *a, **k: SiglipVisionModel(SiglipVisionConfig.from_pretrained(name)))
with contextlib.redirect_stdout(io.StringIO()):
    model, tokenizer, img_proc, cfg, mapping, ratio = load_model(str(ROOT / "ng.pt"))
session = InferenceSession(model, str(ROOT / "ng.pt"), tokenizer, img_proc, cfg, mapping, None, False, 1.0, ratio, None)
OWN_STEPS = model.num_inference_timesteps
SHIFT = cfg.modality_cfg.action_shift
INFO = {
    "version": 1, "model": "nvidia/NitroGen ng.pt", "flow_steps": OWN_STEPS, "actions": cfg.model_cfg.action_horizon,
    "rate_hz": RATE, "first_step": SHIFT, "frame": [256, 256],
}  # fmt: skip
busy = threading.Lock()


def unit(value, low=-1.0):
    return round(max(low, min(1.0, float(value))), 3)


def pad(left, right, buttons):
    values = dict(zip(BUTTON_ACTION_TOKENS, buttons))
    return {
        "buttons": [name for token, name in NAMES.items() if values[token] > 0.5],
        # x is right and y is down on both sides: the repository flips y only for the Windows pad
        "left": [unit(left[0]), unit(left[1])],
        "right": [unit(right[0]), unit(right[1])],
        "l2": unit(values["LEFT_TRIGGER"], 0.0),
        "r2": unit(values["RIGHT_TRIGGER"], 0.0),
    }


def predict(image, steps):
    with busy:
        model.num_inference_timesteps = steps
        with contextlib.redirect_stdout(io.StringIO()):
            out = session.predict(image)
    rows = zip(*(np.asarray(out[key], dtype=float) for key in ("j_left", "j_right", "buttons")))
    return [pad(left, right, buttons) for left, right, buttons in rows]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def reply(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self.reply(200, INFO) if self.path == "/info" else self.reply(404, {"error": "unknown path"})

    def do_POST(self):
        began = time.perf_counter()
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path != "/policy":
            return self.reply(404, {"error": "unknown path"})
        try:
            request = json.loads(body)
            image = Image.open(io.BytesIO(base64.b64decode(request["image_jpeg_base64"]))).convert("RGB")
            if image.size != (256, 256):  # the repository's client squeezes the whole picture into the square
                image = image.resize((256, 256), Image.Resampling.BOX)
            steps = int(request.get("steps", OWN_STEPS))
            if steps not in (4, 8, 16):
                raise ValueError("steps is 4, 8 or 16")
            chunk = predict(image, steps)
        except Exception as error:
            return self.reply(400, {"error": f"{type(error).__name__}: {error}"})
        seconds = time.perf_counter() - began
        # The first action belongs SHIFT steps after the frame. `pad` is the action that is due when
        # this reply leaves; a client that knows how old the frame was takes its own from `chunk`.
        index = max(0, min(len(chunk) - 1, round(seconds * RATE) - SHIFT))
        self.reply(200, {
            "version": 1, "capture": request.get("capture"), "pad": chunk[index],
            "why": f"NitroGen, action {index} of {len(chunk)}, {steps} flow steps",
            "chunk": chunk, "rate_hz": RATE, "first_step": SHIFT, "seconds": round(seconds, 4),
        })  # fmt: skip


server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
print(f"NitroGen is serving on 127.0.0.1:{PORT} of the PC; Ctrl-C ends it", flush=True)
try:
    server.serve_forever()
except KeyboardInterrupt:
    pass
'@
[IO.File]::WriteAllText("$root\serve.py", $code)
& "$root\venv\Scripts\python.exe" "$root\serve.py"
