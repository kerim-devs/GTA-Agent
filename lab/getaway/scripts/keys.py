"""Minimap crops of the key frames of Kerim's recordings, with the derived readings beside them.

keys.py <recording-name> ... ; writes $P68_WORK/keys/<name>.npz with crops (N,170,260,3), index, t, wanted, map,
screen, corrupt, kind (section kind)."""

import bisect
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from common import KEYS

KERIM = Path("/Users/kerim/recordings/kerim")
DERIVED = Path("/Users/kerim/recordings/derived/kerim")
OUT = KEYS
OUT.mkdir(parents=True, exist_ok=True)

for name in sys.argv[1:]:
    rec = KERIM / name
    video = rec / "video.mp4"
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-skip_frame", "nokey", "-show_entries",
         "frame=pts_time", "-of", "csv=p=0", str(video)],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    index = [round(float(v.strip(",")) * 60) for v in probe if v.strip(",") and v.strip(",") != "N/A"]
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-skip_frame", "nokey", "-i", str(video), "-vf", "crop=260:170:30:530",
         "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, check=True,
    ).stdout
    crops = np.frombuffer(raw, np.uint8).reshape(-1, 170, 260, 3)
    n = min(len(crops), len(index))
    crops, index = crops[:n], index[:n]
    frames = {}
    for line in (rec / "frames.jsonl").open():
        row = json.loads(line)
        frames[row["i"]] = row["t"]
    times = [frames.get(i, float("nan")) for i in index]
    hud = [json.loads(line) for line in (DERIVED / name / "hud.jsonl").open()] if (DERIVED / name).exists() else []
    hud_t = [row["t"] for row in hud]
    sections = []
    if (DERIVED / name / "sections.json").exists():
        sections = json.load((DERIVED / name / "sections.json").open())["sections"] or []

    def near(t):
        if not hud:
            return {}
        k = bisect.bisect_left(hud_t, t)
        best = min((j for j in (k - 1, k) if 0 <= j < len(hud)), key=lambda j: abs(hud_t[j] - t))
        return hud[best] if abs(hud_t[best] - t) < 0.3 else {}

    def kind(t):
        for s in sections:
            if s["start"] <= t < s["end"]:
                return s["kind"]
        return ""

    rows = [near(t) for t in times]
    np.savez_compressed(
        OUT / f"{name}.npz",
        crops=crops,
        index=np.array(index),
        t=np.array(times),
        wanted=np.array([r.get("wanted") if r.get("wanted") is not None else -1 for r in rows]),
        map=np.array([str(r.get("map")) for r in rows]),
        screen=np.array([str(r.get("screen")) for r in rows]),
        corrupt=np.array([bool(r.get("corrupt")) for r in rows]),
        kind=np.array([kind(t) for t in times]),
    )
    print(name, n, "keyframes")
