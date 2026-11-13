"""Offline image-number experiment; never connects to the model or console."""

import json
import sys
import time
import statistics
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "pilot/src"))
from pilot import indoors


ROOT = Path("/Users/kerim/recordings/pilot")


def frame_at(session, seconds):
    directory = ROOT / session
    stamps = [json.loads(line)["t"] for line in (directory / "frames.jsonl").open()]
    index = int(np.argmin(np.abs(np.array(stamps) - stamps[0] - seconds)))
    cap = cv2.VideoCapture(str(directory / "video.mp4"))
    cap.set(cv2.CAP_PROP_POS_FRAMES, index)
    ok, bgr = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError(f"Cannot decode {session} at {seconds}")
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def numbers(frame):
    radar = frame[550:663, 69:239].astype(float)
    high, low = radar.max(axis=2), radar.min(axis=2)
    gray = radar.mean(axis=2)
    return {
        "bright": float(np.mean(low > 100)),
        "dark": float(np.mean(high < 65)),
        "color": float(np.mean(high - low > 25)),
        "white": float(np.mean((low > 90) & (high - low < 20))),
        "contrast": float(gray.std()),
    }


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    source = json.loads((root.parent / "ahead/frames.json").read_text())
    samples = [dict(session="20261113-024118", t=t, indoors=True) for t in range(2, 63)]
    samples += [
        dict(session=row["session"], t=row["t"], indoors=False)
        for row in source
        if row["session"] != "20261113-001124"
    ]
    samples += [
        dict(session="20261113-025632", t=t, indoors=False) for t in range(66, 97)
    ]
    rows = []
    for sample in samples:
        frame = frame_at(sample["session"], sample["t"])
        started = time.perf_counter()
        prediction = indoors.read(frame)
        rows.append(
            {
                **sample,
                "prediction": prediction,
                "milliseconds": 1000 * (time.perf_counter() - started),
                **numbers(frame),
            }
        )
    scores = {}
    for label in (True, False):
        group = [r for r in rows if r["indoors"] == label]
        scores["indoors" if label else "outdoors"] = {
            "count": len(group),
            "correct": sum(r["prediction"] == label for r in group),
            "unknown": sum(r["prediction"] is None for r in group),
        }
    transition = []
    for t in np.arange(60, 67, 0.25):
        frame = frame_at("20261113-025632", float(t))
        transition.append({"t": float(t), "prediction": indoors.read(frame)})
    result = {
        "development_sessions": ["20261113-025032", "20261113-001124"],
        "frozen_color_limit": indoors.COLOR_LIMIT,
        "scores": scores,
        "transition": transition,
        "samples": rows,
    }
    filenames = {(r["session"], r["t"]): r["file"] for r in source}
    labels = {
        r[1]: r[2]
        for r in json.loads((root.parent / "ahead/indoors.json").read_text())
        if r[0] == "outdoors"
    }
    matched = []
    for row in rows:
        name = filenames.get((row["session"], row["t"]))
        if name in labels:
            share = labels[name]
            model = share >= 0.9 if share >= 0.9 or share < 0.5 else None
            matched.append(
                dict(
                    session=row["session"],
                    t=row["t"],
                    file=name,
                    truth=row["indoors"],
                    local=row["prediction"],
                    model=model,
                    share=share,
                )
            )
    disagreements = [
        r
        for r in matched
        if r["model"] is not None
        and r["local"] is not None
        and r["model"] != r["local"]
    ]
    result["model_comparison"] = {
        "matched": len(matched),
        "disagreements": len(disagreements),
        "model_right": sum(r["model"] == r["truth"] for r in disagreements),
        "reader_right": sum(r["local"] == r["truth"] for r in disagreements),
        "frames": matched,
    }
    result["latency_ms"] = {
        "median": statistics.median(r["milliseconds"] for r in rows),
        "max": max(r["milliseconds"] for r in rows),
    }
    (root / "heldout.json").write_text(json.dumps(result, indent=2) + "\n")
    from pilot import minimap
    from pilot.foot import hud_crop

    entry = []
    for seconds in (0.15, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0):
        frame = frame_at("20261113-022849", seconds)
        reading = minimap.read(hud_crop(frame))
        entry.append(
            {
                "session": "20261113-022849",
                "seconds": seconds,
                "raw_prediction": indoors.read(frame),
                "minimap": reading.minimap,
                "corrupt": reading.corrupt,
                "confidence": reading.confidence,
            }
        )
    (root / "entry.json").write_text(json.dumps(entry, indent=2) + "\n")
    print(
        json.dumps({"scores": scores, "transition": transition}, indent=2), flush=True
    )
