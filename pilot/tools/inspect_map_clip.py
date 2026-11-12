"""Label/check the recorded pause map, using capture indices rather than MP4 seconds.

Run from pilot: .venv/bin/python tools/inspect_map_clip.py --output ../lab/waypoint
The recording is read-only. OCR results are cached so checks can be repeated offline.
"""

import argparse
import json
from itertools import pairwise
from pathlib import Path

import cv2
import numpy as np

from pilot.scene import SceneText, TextLine, TextReader
from pilot.waypoint import map_screen, map_shift, read_map

RECORDINGS = Path("/Users/kerim/Documents/ChatGPT/gta/recordings")


def inspect(root, output):
    output.mkdir(parents=True, exist_ok=True)
    cache_path = output / "ocr.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    reader = None
    labels = []
    examples = []
    for recording in ("20261110-091812", "20261110-093238"):
        times = [json.loads(line) for line in (root / recording / "frames.jsonl").read_text().splitlines()]
        wanted = {}
        for t in np.arange(0, times[-1]["t"], 2):
            row = min(times, key=lambda row: abs(row["t"] - t))
            if recording.endswith("093238") and 383 <= row["t"] <= 396:
                continue
            wanted[row["i"]] = "non-map"
        if recording.endswith("093238"):
            wanted.update({i: "map" for i in range(8191, 8316)})
            pad = [json.loads(line) for line in (root / recording / "pad.jsonl").read_text().splitlines()]
            pad = [row for row in pad if 383 <= row["t"] <= 394]
            (output / "pad-clip.json").write_text(json.dumps(pad, indent=2) + "\n")
        by_index = {row["i"]: row for row in times}
        video = cv2.VideoCapture(str(root / recording / "video.mp4"))
        for index, label in sorted(wanted.items()):
            video.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = video.read()
            if not ok:
                raise RuntimeError(f"missing frame {recording}/{index}")
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            key = f"{recording}/{index}"
            if key not in cache:
                reader = reader or TextReader()
                result = reader.read(frame)
                cache[key] = [vars(line) for line in result.lines]
                if len(cache) % 20 == 0:
                    cache_path.write_text(json.dumps(cache, indent=2) + "\n")
                    print(f"OCR {len(cache)}", flush=True)
            text = SceneText(tuple(TextLine(**line) for line in cache[key]))
            screen = map_screen(frame, text)
            category = {
                ("20261110-093238", 10940): "weapon-wheel",
                ("20261110-093238", 856): "failed",
                ("20261110-093238", 886): "failed",
                ("20261110-093238", 7172): "cutscene",
                ("20261110-093238", 7211): "cutscene",
            }.get((recording, index), label)
            labels.append(
                {
                    "recording": recording,
                    **by_index[index],
                    "label": label,
                    "category": category,
                    "screen": screen,
                }
            )
            if label == "map" and index in {8191, 8192, 8216, 8221, 8252, 8286, 8305, 8315}:
                cv2.imwrite(str(output / f"map-{index}.jpg"), cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
                picture = read_map(frame, text)
                print(
                    f"frame {index}: {picture.screen}, cursor={picture.cursor}, player={picture.player}, "
                    f"missions={picture.missions}, waypoint={picture.waypoint}",
                    flush=True,
                )
            tile = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR), (256, 144))
            cv2.putText(
                tile,
                f"{recording[-6:]} i{index} {by_index[index]['t']:.2f}",
                (3, 15),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (0, 0, 255),
                1,
            )
            examples.append((label, tile))
        video.release()
    cache_path.write_text(json.dumps(cache, indent=2) + "\n")
    (output / "labels.json").write_text(json.dumps(labels, indent=2) + "\n")
    for label in ("map", "non-map"):
        tiles = [tile for name, tile in examples if name == label]
        for page, start in enumerate(range(0, len(tiles), 60)):
            chunk = tiles[start : start + 60]
            chunk += [np.zeros_like(chunk[0])] * ((-len(chunk)) % 6)
            montage = np.vstack([np.hstack(chunk[i : i + 6]) for i in range(0, len(chunk), 6)])
            cv2.imwrite(str(output / f"{label}-contact-{page}.jpg"), montage)
    positives = [row for row in labels if row["label"] == "map"]
    negatives = [row for row in labels if row["label"] == "non-map"]
    summary = {
        "map_frames": len(positives),
        "map_missed": [row["i"] for row in positives if not row["screen"]],
        "non_map_frames": len(negatives),
        "false_maps": [row for row in negatives if row["screen"]],
    }
    (output / "classification.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return summary


def measure(root, output):
    """Fit the actual stick integral against road translation, including rejected pairs."""
    recording = root / "20261110-093238"
    times = [json.loads(line) for line in (recording / "frames.jsonl").read_text().splitlines()]
    events = [json.loads(line) for line in (recording / "pad.jsonl").read_text().splitlines()]
    cache = json.loads((output / "ocr.json").read_text())
    rows = [row for row in times if 8191 <= row["i"] <= 8304]
    frames = {}
    video = cv2.VideoCapture(str(recording / "video.mp4"))
    video.set(cv2.CAP_PROP_POS_FRAMES, rows[0]["i"])
    for row in rows:
        ok, frame = video.read()
        if not ok:
            raise RuntimeError(f"missing measurement frame {row['i']}")
        frames[row["i"]] = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    video.release()
    usable = {}
    for row in rows:
        frame = frames[row["i"]]
        text = SceneText(tuple(TextLine(**line) for line in cache[f"20261110-093238/{row['i']}"]))
        picture = read_map(frame, text)
        # Before 8252 the contact sheet shows the entry animation and mixed codec blocks.
        usable[row["i"]] = (
            row["i"] >= 8252
            and picture.screen == "map"
            and picture.cursor is not None
            and map_shift(frame, frame) is not None
        )
    pairs = []
    for a, b in pairwise(rows):
        shift = map_shift(frames[a["i"]], frames[b["i"]]) if usable[a["i"]] and usable[b["i"]] else None
        pairs.append(
            {
                "before": a,
                "after": b,
                "shift": shift,
                "accepted": shift is not None,
                "reason": None
                if shift is not None
                else "transition, damage or unsupported road correspondence",
            }
        )
    accepted = [pair for pair in pairs if pair["accepted"]]

    event_times = np.array([row["t"] for row in events])
    event_sticks = np.array([row["left"] for row in events[:-1]])

    def integral(start, end):
        overlap = np.maximum(0, np.minimum(end, event_times[1:]) - np.maximum(start, event_times[:-1]))
        return np.sum(overlap[:, None] * event_sticks, axis=0)

    fits = []
    observed = np.array([pair["shift"] for pair in accepted])
    variance = float(np.sum((observed - observed.mean(axis=0)) ** 2))
    for delay in np.arange(0, 1.501, 0.01):
        inputs = np.array(
            [-integral(pair["before"]["t"] - delay, pair["after"]["t"] - delay) for pair in accepted]
        )
        square = float(np.sum(inputs**2))
        gain = float(np.sum(inputs * observed) / square) if square else 0.0
        residual = float(np.sum((observed - inputs * gain) ** 2))
        fits.append(
            {
                "delay": round(float(delay), 2),
                "gain_px_per_full_stick_second": gain,
                "r_squared": 1 - residual / variance if variance else 0,
                "rmse_px": float(np.sqrt(residual / max(1, len(accepted)))),
            }
        )
    best = max(fits, key=lambda row: row["r_squared"])
    wifi_fit = max((row for row in fits if 0.6 <= row["delay"] <= 1.1), key=lambda row: row["r_squared"])
    # A <0.05 stick magnitude is neutral; recorded hardware has small centre noise.
    bursts = []
    active = None
    for row in events:
        if not 386.5 <= row["t"] <= 390.7:
            continue
        moving = np.linalg.norm(row["left"]) >= 0.05
        if moving and active is None:
            active = row["t"]
        if not moving and active is not None:
            bursts.append({"start": active, "end": row["t"]})
            active = None
    illustrations = []
    tiles = []
    for number, burst in enumerate(bursts, 1):
        a = min(rows, key=lambda row: abs(row["t"] - burst["start"] - best["delay"]))
        b = min(rows, key=lambda row: abs(row["t"] - burst["end"] - best["delay"]))
        shift = map_shift(frames[a["i"]], frames[b["i"]]) if usable[a["i"]] and usable[b["i"]] else None
        illustration = {
            "push": number,
            **burst,
            "stick_integral": integral(burst["start"], burst["end"]).tolist(),
            "before": a,
            "after": b,
            "shift": shift,
            "attribution": "unproven: fitted delay is not a calibration",
        }
        illustrations.append(illustration)
        pair_tiles = []
        for side, row in (("before", a), ("after", b)):
            tile = cv2.resize(cv2.cvtColor(frames[row["i"]], cv2.COLOR_RGB2BGR), (640, 360))
            label = f"push {number} {side} i{row['i']} {row['t']:.3f}s"
            cv2.rectangle(tile, (0, 0), (640, 55), (0, 0, 0), -1)
            cv2.putText(tile, label, (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            detail = (
                "unverified pair"
                if shift is None
                else f"shift {shift[0]:.1f}, {shift[1]:.1f}px; attribution unproven"
            )
            cv2.putText(tile, detail, (8, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
            pair_tiles.append(tile)
        tiles.append(np.hstack(pair_tiles))
    for page, start in enumerate(range(0, len(tiles), 4)):
        cv2.imwrite(str(output / f"p19b-pushes-{page + 1}.jpg"), np.vstack(tiles[start : start + 4]))
    # A clean movement pair independent of the weak stick-delay fit.
    a, b = next(row for row in rows if row["i"] == 8255), next(row for row in rows if row["i"] == 8259)
    example = {"before": a, "after": b, "shift": map_shift(frames[a["i"]], frames[b["i"]])}
    cv2.imwrite(
        str(output / "p19b-clean-shift.jpg"),
        np.hstack([cv2.cvtColor(frames[row["i"]], cv2.COLOR_RGB2BGR) for row in (a, b)]),
    )
    summary = {
        "accepted_pairs": len(accepted),
        "rejected_pairs": len(pairs) - len(accepted),
        "model": "map shift = -gain * integral(stick(t - delay)); one scalar, zero intercept",
        "best_fit": best,
        "best_fit_within_reported_wifi_delay": wifi_fit,
        "calibrated": best["r_squared"] >= 0.8 and best["gain_px_per_full_stick_second"] > 0,
        "clean_shift_example": example,
        "pushes": illustrations,
        "pairs": pairs,
        "fits": fits,
    }
    (output / "p19b-measurement.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(
        json.dumps(
            {key: value for key, value in summary.items() if key not in {"pairs", "fits", "pushes"}}, indent=2
        )
    )
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recordings", type=Path, default=RECORDINGS)
    parser.add_argument("--output", type=Path, default=Path("../lab/waypoint"))
    parser.add_argument("--measure-only", action="store_true")
    args = parser.parse_args()
    if args.measure_only:
        measure(args.recordings, args.output)
        raise SystemExit(0)
    result = inspect(args.recordings, args.output)
    measure(args.recordings, args.output)
    raise SystemExit(bool(result["map_missed"] or result["false_maps"] or result["non_map_frames"] < 300))
