"""crops_at.py <recording-dir> <out.npz> <every-seconds>: HUD crops of a recording every so many seconds."""
import json, subprocess, sys
import numpy as np
rec, out, every = sys.argv[1], sys.argv[2], float(sys.argv[3])
raw = subprocess.run(["ffmpeg", "-v", "error", "-i", f"{rec}/video.mp4", "-vf", f"fps=1/{every},crop=260:170:30:530",
                      "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
crops = np.frombuffer(raw, np.uint8).reshape(-1, 170, 260, 3)
np.savez_compressed(out, crops=crops, t=np.arange(len(crops)) * every + every / 2)
print(out, len(crops))
