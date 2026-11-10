"""Cut the start off a recording: writes the kept part to `<folder>/.trim` and prints what it holds."""
import json, sys
from pathlib import Path
import av

folder, cut_s = Path(sys.argv[1]), float(sys.argv[2])
frames = [json.loads(l) for l in open(folder / "frames.jsonl") if l.strip()]
pad = [json.loads(l) for l in open(folder / "pad.jsonl") if l.strip()]
meta = json.load(open(folder / "meta.json"))
i0 = next(k for k, r in enumerate(frames) if r["t"] >= cut_s)
t0 = frames[i0]["t"]
out = folder / ".trim"
out.mkdir(exist_ok=False)

kept = 0
with av.open(str(folder / "video.mp4")) as src, av.open(str(out / "video.mp4"), "w") as dst:
    vin = src.streams.video[0]
    vout = dst.add_stream("libx264", rate=meta["fps"])
    vout.width, vout.height, vout.pix_fmt = vin.width, vin.height, "yuv420p"
    vout.options = {"preset": "veryfast", "crf": "18"}
    for n, frame in enumerate(src.decode(video=0)):
        if n < i0:
            continue
        picture = av.VideoFrame.from_ndarray(frame.to_ndarray(format="rgb24"), format="rgb24")
        picture.pts = kept
        for packet in vout.encode(picture):
            dst.mux(packet)
        kept += 1
    for packet in vout.encode():
        dst.mux(packet)
total = n + 1

with open(out / "frames.jsonl", "w") as f:
    for k, r in enumerate(frames[i0:]):
        f.write(json.dumps({"i": k, "frame_id": r["frame_id"], "t": round(r["t"] - t0, 4)}) + "\n")
before = [r for r in pad if r["t"] < t0]
after = [r for r in pad if r["t"] >= t0]
held = {}
for r in before:
    held[r["src"]] = r  # the state each controller was in at the cut
with open(out / "pad.jsonl", "w") as f:
    for r in held.values():
        f.write(json.dumps({**r, "t": 0.0}) + "\n")
    for r in after:
        f.write(json.dumps({**r, "t": round(r["t"] - t0, 4)}) + "\n")
meta.update(
    seconds=round(frames[-1]["t"] - t0, 1),
    frames=len(frames) - i0,
    pad_events=len(held) + len(after),
    trimmed=f"first {t0:.0f} s removed: the car stood still",
)
(out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
print(f"source frames decoded {total}, listed {len(frames)}; cut at frame {i0} ({t0:.1f} s)")
print(f"kept frames written {kept}, listed {len(frames) - i0}; pad events kept {len(held) + len(after)}")
