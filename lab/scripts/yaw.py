"""How far the far background moves sideways in a recording, next to the stick the loop held."""
import bisect, json, sys
import av
import numpy as np

d = sys.argv[1]
fr = [json.loads(l) for l in open(d + "/frames.jsonl") if l.strip()]
pad = [json.loads(l) for l in open(d + "/pad.jsonl") if l.strip() and '"agent"' in l]
pt = [r["t"] for r in pad]

def stick(t):
    k = bisect.bisect_right(pt, t) - 1
    return (pad[k]["left"][0], pad[k]["r2"]) if k >= 0 else (0.0, 0.0)

def shift(a, b):
    """Sideways shift of b against a in pixels, by phase correlation of the row means."""
    fa, fb = np.fft.rfft(a - a.mean()), np.fft.rfft(b - b.mean())
    cross = fa * np.conj(fb)
    corr = np.fft.irfft(cross / (np.abs(cross) + 1e-9), n=len(a))
    k = int(np.argmax(corr))
    return k if k < len(a) // 2 else k - len(a)

bands = []
with av.open(d + "/video.mp4") as c:
    for f in c.decode(video=0):
        g = f.to_ndarray(format="gray")[20:230, 200:1100].astype(np.float32)  # skyline band, no HUD
        bands.append(g.mean(axis=0))
pos, x = [0.0], 0.0
for a, b in zip(bands, bands[1:]):
    s = shift(a, b)
    x += s if abs(s) < 60 else 0  # a jump that large is a broken frame, not steering
    pos.append(x)
print(" t[s]  stick   r2   skyline[px]")
for k in range(0, len(fr), 6):
    sx, r2 = stick(fr[k]["t"])
    print(f"{fr[k]['t']:5.1f}  {sx:+.2f}  {r2:.1f}  {pos[k]:+7.0f}")
