"""Extract small regression fixtures by recorded frame ID, never video clock time."""

import json
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "lab/foot/p50"


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main():
    jobs = {
        "20261112-100318": [("hill-a-a", 55, True), ("hill-a-b", 55.5, True)],
        "20261112-100713": [("hill-b-a", 100, True), ("hill-b-b", 100.5, True)],
        "20261112-082524": [("hospital-a", 122, True), ("hospital-b", 122.5, True)],
        "20261111-204712": [("pier-a", 120, True), ("pier-b", 120.5, True)],
    }
    provenance = []
    for session, samples in jobs.items():
        recording = Path("/Users/kerim/recordings/pilot") / session
        rows = records(recording / "play.jsonl")
        play = [row for row in rows if row.get("fresh")]
        frames = {row["frame_id"]: row for row in records(recording / "frames.jsonl")}
        heads = records(recording / "head.jsonl")
        origin = heads[0]["t"] - rows[0]["t"]
        if session in ("20261112-100318", "20261112-100713"):
            samples += [
                (f"{session}-blip-{row['id']}", row["t"] - origin, False)
                for row in heads
                if row.get("type") == "request"
                and row["request"]["minimap"].get("blips")
            ]
        capture = cv2.VideoCapture(str(recording / "video.mp4"))
        for name, t, small in samples:
            row = min(play, key=lambda row: abs(row["t"] - t))
            item = frames[row["frame_id"]]
            capture.set(cv2.CAP_PROP_POS_FRAMES, item["i"])
            ok, bgr = capture.read()
            assert ok
            picture = cv2.resize(bgr, (320, 180)) if small else bgr[530:700, 30:290]
            cv2.imwrite(str(OUT / (name + ".png")), picture)
            provenance.append(
                {
                    "file": name + ".png",
                    "recording": session,
                    "t": row["t"],
                    "frame_id": row["frame_id"],
                    "i": item["i"],
                }
            )
        capture.release()
    (OUT / "fixtures.json").write_text(json.dumps(provenance, indent=2) + "\n")


if __name__ == "__main__":
    main()
