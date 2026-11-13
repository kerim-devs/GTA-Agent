"""Measure raw human pedals, GPS and road curvature from two cable drives, at 4 Hz."""

import bisect
import gzip
import json
import sys
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot/src"))
from p98_replay import baseline, limit_terms
from pilot.gps import Speedometer, recognize
from pilot.minimap import read
from pilot.motion import map_motion, map_speed
from pilot.replay import hud_crop
from steady import geometry

cv2.setNumThreads(1)


def extract(name, start, end):
    directory = Path("/Users/kerim/recordings/kerim") / name
    frames = [
        json.loads(x) for x in (directory / "frames.jsonl").read_text().splitlines()
    ]
    pads = [json.loads(x) for x in (directory / "pad.jsonl").read_text().splitlines()]
    pads = [p for p in pads if p.get("src") == "human"]
    times = [p["t"] for p in pads]
    cap = cv2.VideoCapture(str(directory / "video.mp4"))
    first = next(i for i, f in enumerate(frames) if f["t"] >= start)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frames[first]["i"])
    rows = []
    at = -1
    prev = None
    prev_at = None
    meter = Speedometer()
    _, cfg = baseline()
    for f in frames[first:]:
        if f["t"] >= end:
            break
        if not cap.grab():
            raise ValueError(f)
        if f["t"] - at < 0.25:
            continue
        ok, bgr = cap.retrieve()
        assert ok
        crop = hud_crop(bgr)
        r = read(crop)
        fix = recognize(crop) if r.minimap == "tilted" else None
        speed = meter.update(f["t"], fix, sampled_at=f["t"])
        pixels = (
            map_speed(map_motion(prev, crop), f["t"] - prev_at)
            if prev is not None
            else None
        )
        prev, prev_at = crop, f["t"]
        at = f["t"]
        i = bisect.bisect_right(times, at) - 1
        pad = pads[i] if i >= 0 else {}
        g = geometry(asdict(r))
        peak = limit_terms(r.path, 0, speed, cfg)[2]
        scale = (
            0.7
            if speed is None or speed < 6
            else 1
            if speed < 12
            else 2.1
            if speed < 18
            else 3.6
            if speed < 24
            else 3.7
        )
        rows.append(
            {
                "t": at,
                "reading": asdict(r),
                "r2": pad.get("r2", 0),
                "l2": pad.get("l2", 0),
                "speed": speed,
                "flow": pixels,
                "distance": None if fix is None else fix.distance,
                "bend": None if g is None else g[1],
                "radius": None if peak < 0.001 else scale / peak,
            }
        )
    cap.release()
    return rows


def metrics(rows):
    result = {}
    for i, r in enumerate(rows):
        r["dt"] = min(0.4, rows[i + 1]["t"] - r["t"]) if i + 1 < len(rows) else 0.25
        r["before_bend"] = (
            r["bend"] is not None
            and r["bend"] < 20
            and any(
                s["bend"] is not None
                and s["bend"] >= 20
                and 0.5 <= s["t"] - r["t"] <= 3
                for s in rows[i + 1 : i + 14]
            )
        )
    for name, select in [
        ("straight", lambda r: r["bend"] is not None and r["bend"] < 10),
        ("bend", lambda r: r["bend"] is not None and r["bend"] >= 20),
        ("approach", lambda r: r["before_bend"]),
    ]:
        chosen = [r for r in rows if select(r)]
        speeds = [r["speed"] for r in chosen if r["speed"] is not None]
        radii = [r["radius"] for r in chosen if r["radius"] is not None]
        result[name] = {
            "samples": len(chosen),
            "seconds": round(sum(r["dt"] for r in chosen), 2),
            "full_r2": float(
                np.average(
                    [r["r2"] >= 0.95 for r in chosen], weights=[r["dt"] for r in chosen]
                )
            )
            if chosen
            else None,
            "lift": float(
                np.average(
                    [r["r2"] <= 0.01 for r in chosen], weights=[r["dt"] for r in chosen]
                )
            )
            if chosen
            else None,
            "l2": float(
                np.average(
                    [r["l2"] > 0.01 for r in chosen], weights=[r["dt"] for r in chosen]
                )
            )
            if chosen
            else None,
            "speed_samples": len(speeds),
            "speed_p50_p90": np.percentile(speeds, [50, 90]).tolist() if speeds else [],
            "radius_p10_p50_p90": np.percentile(radii, [10, 50, 90]).tolist()
            if radii
            else [],
        }
    ratios = [
        r["speed"] / r["flow"]
        for r in rows
        if r["speed"] is not None
        and r["speed"] >= 3
        and r["flow"]
        and r["flow"] > 2
        and r["bend"] is not None
        and r["bend"] < 10
    ]
    result["gps_over_flow_scale_p10_p50_p90"] = (
        np.percentile(ratios, [10, 50, 90]).tolist() if ratios else []
    )
    return result


if __name__ == "__main__":
    output = {}
    for name, start, end in [("20261113-141634", 90, 210), ("20261113-031159", 0, 35)]:
        dest = ROOT / "lab/drive" / f"p98-human-{name}.json.gz"
        rows = (
            json.loads(gzip.decompress(dest.read_bytes()))
            if dest.exists()
            else extract(name, start, end)
        )
        dest.write_bytes(gzip.compress(json.dumps(rows).encode(), mtime=0))
        output[name] = metrics(rows)
        print(name, output[name], flush=True)
    (ROOT / "lab/drive/p98-human.json").write_text(json.dumps(output, indent=2) + "\n")
